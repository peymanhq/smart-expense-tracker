"""SQLite implementation of the Category repository contract."""

import sqlite3
from dataclasses import replace
from uuid import UUID

from category import (
    Category,
    canonicalize_category_name,
    category_name_key,
)
from category_repository import (
    CategoryRepositoryConflictError,
    CategoryRepositoryNotFoundError,
    CategoryRepositoryRecordChangedError,
)
from id_generator import (
    generate_category_display_id,
    parse_category_display_id,
)
from persistence_errors import StorageError
from sqlite_database import SQLiteDatabase

_CATEGORY_COLUMNS = (
    "id, display_id, name, name_key, transaction_type, is_active"
)


def _comparison_key(name: object) -> str:
    if not isinstance(name, str):
        raise StorageError("SQLite Category name must be text.")
    return category_name_key(name)


def _validate_category(category: Category, name_key: str) -> None:
    try:
        parsed_id = UUID(category.id)
    except (ValueError, AttributeError, TypeError) as error:
        raise StorageError("SQLite Category id must be a canonical UUID.") from error
    if str(parsed_id) != category.id:
        raise StorageError("SQLite Category id must be a canonical UUID.")

    if not isinstance(category.display_id, str):
        raise StorageError("SQLite Category display_id must be text.")
    number = parse_category_display_id(category.display_id)
    if (
        number is None
        or generate_category_display_id(number) != category.display_id
    ):
        raise StorageError(
            "SQLite Category display_id must use canonical C-#### format."
        )

    if (
        not isinstance(category.name, str)
        or not category.name.strip()
        or category.name != category.name.strip()
    ):
        raise StorageError(
            "SQLite Category name must be non-empty text without outer whitespace."
        )
    if category.name != canonicalize_category_name(category.name):
        raise StorageError("SQLite Category name must use canonical Unicode form.")
    if name_key != category_name_key(category.name):
        raise StorageError("SQLite Category name_key is inconsistent with name.")
    if category.transaction_type not in {"income", "expense"}:
        raise StorageError(
            "SQLite Category transaction_type must be income or expense."
        )
    if not isinstance(category.is_active, bool):
        raise StorageError("SQLite Category is_active must be a boolean.")


def _category_from_row(row: sqlite3.Row) -> Category:
    is_active = row["is_active"]
    if not isinstance(is_active, int) or is_active not in {0, 1}:
        raise StorageError("SQLite Category is_active must be 0 or 1.")
    category = Category(
        id=row["id"],
        display_id=row["display_id"],
        name=row["name"],
        transaction_type=row["transaction_type"],
        is_active=bool(is_active),
    )
    _validate_category(category, row["name_key"])
    return category


def _counter_value(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        SELECT next_value
        FROM display_id_counters
        WHERE entity_type = 'category'
        """
    ).fetchone()
    if row is None:
        raise StorageError("SQLite Category display-ID counter is missing.")
    value = row["next_value"]
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise StorageError("SQLite Category display-ID counter is invalid.")
    return value


def _is_active_name_integrity_error(error: StorageError) -> bool:
    cause = error.__cause__
    return (
        isinstance(cause, sqlite3.IntegrityError)
        and "categories.transaction_type, categories.name_key" in str(cause)
    )


class SQLiteCategoryRepository:
    """Persist Categories in an explicitly supplied SQLite database."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def list_all(self) -> list[Category]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_CATEGORY_COLUMNS}
                FROM categories
                ORDER BY CAST(substr(display_id, 3) AS INTEGER), display_id
                """
            ).fetchall()
        return [_category_from_row(row) for row in rows]

    def get_by_id(self, category_id: str) -> Category | None:
        if not isinstance(category_id, str):
            return None
        with self._database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT {_CATEGORY_COLUMNS}
                FROM categories
                WHERE id = ?
                """,
                (category_id,),
            ).fetchone()
        return None if row is None else _category_from_row(row)

    def get_by_display_id(self, display_id: str) -> Category | None:
        if not isinstance(display_id, str):
            return None
        number = parse_category_display_id(display_id)
        if number is None:
            return None
        normalized = generate_category_display_id(number)
        with self._database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT {_CATEGORY_COLUMNS}
                FROM categories
                WHERE display_id = ?
                """,
                (normalized,),
            ).fetchone()
        return None if row is None else _category_from_row(row)

    def create(
        self,
        category_id: str,
        name: str,
        transaction_type: str,
    ) -> Category:
        try:
            with self._database.transaction() as connection:
                name_key = _comparison_key(name)
                if connection.execute(
                    """
                    SELECT 1
                    FROM categories
                    WHERE is_active = 1
                      AND transaction_type = ?
                      AND name_key = ?
                    LIMIT 1
                    """,
                    (transaction_type, name_key),
                ).fetchone() is not None:
                    raise CategoryRepositoryConflictError(
                        "An active Category with this name and transaction type "
                        "already exists."
                    )

                next_value = _counter_value(connection)
                category = Category(
                    id=category_id,
                    display_id=generate_category_display_id(next_value),
                    name=name,
                    transaction_type=transaction_type,
                )
                _validate_category(category, name_key)

                updated = connection.execute(
                    """
                    UPDATE display_id_counters
                    SET next_value = next_value + 1
                    WHERE entity_type = 'category' AND next_value = ?
                    """,
                    (next_value,),
                )
                if updated.rowcount != 1:
                    raise StorageError(
                        "SQLite Category display-ID allocation conflicted."
                    )
                connection.execute(
                    """
                    INSERT INTO categories(
                        id, display_id, name, name_key,
                        transaction_type, is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        category.id,
                        category.display_id,
                        category.name,
                        name_key,
                        category.transaction_type,
                        int(category.is_active),
                    ),
                )
                return category
        except StorageError as error:
            if _is_active_name_integrity_error(error):
                raise CategoryRepositoryConflictError(
                    "An active Category with this name and transaction type "
                    "already exists."
                ) from error
            raise

    def replace(
        self,
        expected: Category,
        replacement: Category,
    ) -> Category:
        try:
            with self._database.transaction() as connection:
                row = connection.execute(
                    f"""
                    SELECT {_CATEGORY_COLUMNS}
                    FROM categories
                    WHERE id = ?
                    """,
                    (expected.id,),
                ).fetchone()
                if row is None:
                    raise CategoryRepositoryNotFoundError(expected.id)

                current = _category_from_row(row)
                if current != expected:
                    raise CategoryRepositoryRecordChangedError(expected.id)

                persisted = replace(
                    replacement,
                    id=current.id,
                    display_id=current.display_id,
                    transaction_type=current.transaction_type,
                )
                name_key = _comparison_key(persisted.name)
                _validate_category(persisted, name_key)
                if persisted.is_active and connection.execute(
                    """
                    SELECT 1
                    FROM categories
                    WHERE id <> ?
                      AND is_active = 1
                      AND transaction_type = ?
                      AND name_key = ?
                    LIMIT 1
                    """,
                    (
                        current.id,
                        current.transaction_type,
                        name_key,
                    ),
                ).fetchone() is not None:
                    raise CategoryRepositoryConflictError(
                        "An active Category with this name and transaction type "
                        "already exists."
                    )

                updated = connection.execute(
                    """
                    UPDATE categories
                    SET name = ?, name_key = ?, is_active = ?
                    WHERE id = ?
                      AND display_id = ?
                      AND name = ?
                      AND transaction_type = ?
                      AND is_active = ?
                    """,
                    (
                        persisted.name,
                        name_key,
                        int(persisted.is_active),
                        current.id,
                        current.display_id,
                        current.name,
                        current.transaction_type,
                        int(current.is_active),
                    ),
                )
                if updated.rowcount != 1:
                    if connection.execute(
                        "SELECT 1 FROM categories WHERE id = ?",
                        (current.id,),
                    ).fetchone() is None:
                        raise CategoryRepositoryNotFoundError(current.id)
                    raise CategoryRepositoryRecordChangedError(current.id)
                return persisted
        except StorageError as error:
            if _is_active_name_integrity_error(error):
                raise CategoryRepositoryConflictError(
                    "An active Category with this name and transaction type "
                    "already exists."
                ) from error
            raise
