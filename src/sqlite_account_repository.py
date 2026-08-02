"""SQLite implementation of the Account repository contract."""

import sqlite3
from dataclasses import replace
from uuid import UUID

from account import Account, account_name_key
from account_repository import (
    AccountRepositoryConflictError,
    AccountRepositoryNotFoundError,
    AccountRepositoryRecordChangedError,
)
from id_generator import (
    generate_account_display_id,
    parse_account_display_id,
)
from persistence_errors import StorageError
from sqlite_database import SQLiteDatabase

_ACCOUNT_COLUMNS = "id, display_id, name, name_key, is_active"


def _comparison_key(name: object) -> str:
    if not isinstance(name, str):
        raise StorageError("SQLite Account name must be text.")
    return account_name_key(name)


def _validate_account(account: Account, name_key: str) -> None:
    try:
        parsed_id = UUID(account.id)
    except (ValueError, AttributeError, TypeError) as error:
        raise StorageError("SQLite Account id must be a canonical UUID.") from error
    if str(parsed_id) != account.id:
        raise StorageError("SQLite Account id must be a canonical UUID.")

    if not isinstance(account.display_id, str):
        raise StorageError("SQLite Account display_id must be text.")
    number = parse_account_display_id(account.display_id)
    if (
        number is None
        or generate_account_display_id(number) != account.display_id
    ):
        raise StorageError(
            "SQLite Account display_id must use canonical A-#### format."
        )

    if (
        not isinstance(account.name, str)
        or not account.name.strip()
        or account.name != account.name.strip()
    ):
        raise StorageError(
            "SQLite Account name must be non-empty text without outer whitespace."
        )
    if name_key != account_name_key(account.name):
        raise StorageError("SQLite Account name_key is inconsistent with name.")
    if not isinstance(account.is_active, bool):
        raise StorageError("SQLite Account is_active must be a boolean.")


def _account_from_row(row: sqlite3.Row) -> Account:
    is_active = row["is_active"]
    if not isinstance(is_active, int) or is_active not in {0, 1}:
        raise StorageError("SQLite Account is_active must be 0 or 1.")
    account = Account(
        id=row["id"],
        display_id=row["display_id"],
        name=row["name"],
        is_active=bool(is_active),
    )
    _validate_account(account, row["name_key"])
    return account


def _counter_value(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        SELECT next_value
        FROM display_id_counters
        WHERE entity_type = 'account'
        """
    ).fetchone()
    if row is None:
        raise StorageError("SQLite Account display-ID counter is missing.")
    value = row["next_value"]
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise StorageError("SQLite Account display-ID counter is invalid.")
    return value


def _is_active_name_integrity_error(error: StorageError) -> bool:
    cause = error.__cause__
    return (
        isinstance(cause, sqlite3.IntegrityError)
        and "accounts.name_key" in str(cause)
    )


class SQLiteAccountRepository:
    """Persist Accounts in an explicitly supplied SQLite database."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def list_all(self) -> list[Account]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_ACCOUNT_COLUMNS}
                FROM accounts
                ORDER BY CAST(substr(display_id, 3) AS INTEGER), display_id
                """
            ).fetchall()
        return [_account_from_row(row) for row in rows]

    def get_by_id(self, account_id: str) -> Account | None:
        if not isinstance(account_id, str):
            return None
        with self._database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT {_ACCOUNT_COLUMNS}
                FROM accounts
                WHERE id = ?
                """,
                (account_id,),
            ).fetchone()
        return None if row is None else _account_from_row(row)

    def get_by_display_id(self, display_id: str) -> Account | None:
        if not isinstance(display_id, str):
            return None
        number = parse_account_display_id(display_id)
        if number is None:
            return None
        normalized = generate_account_display_id(number)
        with self._database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT {_ACCOUNT_COLUMNS}
                FROM accounts
                WHERE display_id = ?
                """,
                (normalized,),
            ).fetchone()
        return None if row is None else _account_from_row(row)

    def create(self, account_id: str, name: str) -> Account:
        try:
            with self._database.transaction() as connection:
                name_key = _comparison_key(name)
                if connection.execute(
                    """
                    SELECT 1
                    FROM accounts
                    WHERE is_active = 1 AND name_key = ?
                    LIMIT 1
                    """,
                    (name_key,),
                ).fetchone() is not None:
                    raise AccountRepositoryConflictError(
                        "An active Account with this name already exists."
                    )

                next_value = _counter_value(connection)
                account = Account(
                    id=account_id,
                    display_id=generate_account_display_id(next_value),
                    name=name,
                )
                _validate_account(account, name_key)

                updated = connection.execute(
                    """
                    UPDATE display_id_counters
                    SET next_value = next_value + 1
                    WHERE entity_type = 'account' AND next_value = ?
                    """,
                    (next_value,),
                )
                if updated.rowcount != 1:
                    raise StorageError(
                        "SQLite Account display-ID allocation conflicted."
                    )
                connection.execute(
                    """
                    INSERT INTO accounts(
                        id, display_id, name, name_key, is_active
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        account.id,
                        account.display_id,
                        account.name,
                        name_key,
                        int(account.is_active),
                    ),
                )
                return account
        except StorageError as error:
            if _is_active_name_integrity_error(error):
                raise AccountRepositoryConflictError(
                    "An active Account with this name already exists."
                ) from error
            raise

    def replace(self, expected: Account, replacement: Account) -> Account:
        try:
            with self._database.transaction() as connection:
                row = connection.execute(
                    f"""
                    SELECT {_ACCOUNT_COLUMNS}
                    FROM accounts
                    WHERE id = ?
                    """,
                    (expected.id,),
                ).fetchone()
                if row is None:
                    raise AccountRepositoryNotFoundError(expected.id)

                current = _account_from_row(row)
                if current != expected:
                    raise AccountRepositoryRecordChangedError(expected.id)

                persisted = replace(
                    replacement,
                    id=current.id,
                    display_id=current.display_id,
                )
                name_key = _comparison_key(persisted.name)
                _validate_account(persisted, name_key)
                if persisted.is_active and connection.execute(
                    """
                    SELECT 1
                    FROM accounts
                    WHERE id <> ? AND is_active = 1 AND name_key = ?
                    LIMIT 1
                    """,
                    (current.id, name_key),
                ).fetchone() is not None:
                    raise AccountRepositoryConflictError(
                        "An active Account with this name already exists."
                    )

                updated = connection.execute(
                    """
                    UPDATE accounts
                    SET name = ?, name_key = ?, is_active = ?
                    WHERE id = ?
                      AND display_id = ?
                      AND name = ?
                      AND is_active = ?
                    """,
                    (
                        persisted.name,
                        name_key,
                        int(persisted.is_active),
                        current.id,
                        current.display_id,
                        current.name,
                        int(current.is_active),
                    ),
                )
                if updated.rowcount != 1:
                    if connection.execute(
                        "SELECT 1 FROM accounts WHERE id = ?",
                        (current.id,),
                    ).fetchone() is None:
                        raise AccountRepositoryNotFoundError(current.id)
                    raise AccountRepositoryRecordChangedError(current.id)
                return persisted
        except StorageError as error:
            if _is_active_name_integrity_error(error):
                raise AccountRepositoryConflictError(
                    "An active Account with this name already exists."
                ) from error
            raise
