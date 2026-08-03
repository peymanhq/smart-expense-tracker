"""SQLite implementation of the Transaction repository contract."""

import sqlite3
from dataclasses import replace
from datetime import date
from uuid import UUID

from id_generator import generate_display_id, parse_display_id
from persistence_errors import StorageError
from sqlite_database import SQLiteDatabase
from transaction import Transaction
from transaction_repository import (
    RepositoryTransactionNotFoundError,
    TransactionDateSummary,
    _validate_bulk_conflicts,
)
from validators import (
    parse_utc_datetime,
    serialize_amount,
    validate_amount,
    validate_optional_uuid,
    validate_serialized_amount,
    validate_transaction_date,
)

_TRANSACTION_COLUMNS = (
    "id, display_id, type, amount, category, category_id, account, "
    "account_id, description, transaction_date, created_at, updated_at"
)


def _validate_transaction(transaction: Transaction) -> None:
    try:
        parsed_id = UUID(transaction.id)
    except (ValueError, AttributeError, TypeError) as error:
        raise StorageError(
            "SQLite Transaction id must be a canonical UUID."
        ) from error
    if str(parsed_id) != transaction.id:
        raise StorageError("SQLite Transaction id must be a canonical UUID.")

    if not isinstance(transaction.display_id, str):
        raise StorageError("SQLite Transaction display_id must be text.")
    number = parse_display_id(transaction.display_id)
    if number is None or generate_display_id(number) != transaction.display_id:
        raise StorageError(
            "SQLite Transaction display_id must use canonical T-#### format."
        )
    if transaction.type not in {"income", "expense"}:
        raise StorageError(
            "SQLite Transaction type must be income or expense."
        )
    try:
        validate_amount(transaction.amount)
    except ValueError as error:
        raise StorageError(
            "SQLite Transaction amount must be a positive number."
        ) from error
    for field_name in ("category", "account", "description"):
        if not isinstance(getattr(transaction, field_name), str):
            raise StorageError(
                f"SQLite Transaction {field_name} must be text."
            )
    try:
        if (
            validate_transaction_date(transaction.transaction_date)
            is not transaction.transaction_date
        ):
            raise ValueError
        parse_utc_datetime(transaction.created_at, "created_at")
        parse_utc_datetime(transaction.updated_at, "updated_at")
        validate_optional_uuid(transaction.account_id, "account_id")
        validate_optional_uuid(transaction.category_id, "category_id")
    except ValueError as error:
        raise StorageError(
            f"SQLite Transaction contains invalid typed data: {error}"
        ) from error


def _transaction_from_row(row: sqlite3.Row) -> Transaction:
    try:
        transaction = Transaction(
            id=row["id"],
            display_id=row["display_id"],
            type=row["type"],
            amount=validate_serialized_amount(row["amount"]),
            category=row["category"],
            category_id=validate_optional_uuid(row["category_id"], "category_id"),
            account=row["account"],
            account_id=validate_optional_uuid(row["account_id"], "account_id"),
            description=row["description"],
            transaction_date=validate_transaction_date(row["transaction_date"]),
            created_at=parse_utc_datetime(row["created_at"], "created_at"),
            updated_at=parse_utc_datetime(row["updated_at"], "updated_at"),
        )
    except (TypeError, ValueError) as error:
        raise StorageError(
            f"SQLite Transaction record is invalid: {error}"
        ) from error
    _validate_transaction(transaction)
    return transaction


def _counter_value(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        SELECT next_value
        FROM display_id_counters
        WHERE entity_type = 'transaction'
        """
    ).fetchone()
    if row is None:
        raise StorageError("SQLite Transaction display-ID counter is missing.")
    value = row["next_value"]
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise StorageError("SQLite Transaction display-ID counter is invalid.")
    return value


def _insert(connection: sqlite3.Connection, transaction: Transaction) -> None:
    _validate_transaction(transaction)
    connection.execute(
        """
        INSERT INTO transactions(
            id, display_id, type, amount, category, category_id,
            account, account_id, description, transaction_date,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction.id,
            transaction.display_id,
            transaction.type,
            serialize_amount(transaction.amount),
            transaction.category,
            transaction.category_id,
            transaction.account,
            transaction.account_id,
            transaction.description,
            transaction.transaction_date.isoformat(),
            transaction.created_at.isoformat()
            if transaction.created_at is not None
            else None,
            transaction.updated_at.isoformat()
            if transaction.updated_at is not None
            else None,
        ),
    )


class SQLiteTransactionRepository:
    """Persist Transactions in an explicitly supplied SQLite database."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def create(self, transaction: Transaction) -> Transaction:
        with self._database.transaction() as connection:
            next_value = _counter_value(connection)
            created = replace(
                transaction,
                display_id=generate_display_id(next_value),
            )
            updated = connection.execute(
                """
                UPDATE display_id_counters
                SET next_value = next_value + 1
                WHERE entity_type = 'transaction' AND next_value = ?
                """,
                (next_value,),
            )
            if updated.rowcount != 1:
                raise StorageError(
                    "SQLite Transaction display-ID allocation conflicted."
                )
            _insert(connection, created)
            return created

    def create_many(
        self,
        transactions: list[Transaction],
    ) -> list[Transaction]:
        if not transactions:
            return []
        with self._database.transaction() as connection:
            rows = connection.execute(
                f"SELECT {_TRANSACTION_COLUMNS} FROM transactions"
            ).fetchall()
            _validate_bulk_conflicts(
                transactions,
                [_transaction_from_row(row) for row in rows],
            )

            next_value = _counter_value(connection)
            created = [
                replace(
                    transaction,
                    display_id=generate_display_id(next_value + index),
                )
                for index, transaction in enumerate(transactions)
            ]
            updated = connection.execute(
                """
                UPDATE display_id_counters
                SET next_value = next_value + ?
                WHERE entity_type = 'transaction' AND next_value = ?
                """,
                (len(created), next_value),
            )
            if updated.rowcount != 1:
                raise StorageError(
                    "SQLite Transaction display-ID allocation conflicted."
                )
            for transaction in created:
                _insert(connection, transaction)
            return created

    def get_by_id(self, transaction_id: str) -> Transaction | None:
        if not isinstance(transaction_id, str):
            return None
        with self._database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT {_TRANSACTION_COLUMNS}
                FROM transactions
                WHERE id = ?
                """,
                (transaction_id,),
            ).fetchone()
        return None if row is None else _transaction_from_row(row)

    def get_by_display_id(self, display_id: str) -> Transaction | None:
        if not isinstance(display_id, str):
            return None
        normalized = display_id.strip().casefold()
        if not normalized:
            return None
        with self._database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT {_TRANSACTION_COLUMNS}
                FROM transactions
                WHERE lower(trim(display_id)) = ?
                """,
                (normalized,),
            ).fetchone()
        return None if row is None else _transaction_from_row(row)

    def list_all(self) -> list[Transaction]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_TRANSACTION_COLUMNS}
                FROM transactions
                ORDER BY CAST(substr(display_id, 3) AS INTEGER), display_id
                """
            ).fetchall()
        return [_transaction_from_row(row) for row in rows]

    def list_by_date(self, transaction_date: date) -> list[Transaction]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_TRANSACTION_COLUMNS}
                FROM transactions
                WHERE transaction_date = ?
                ORDER BY CAST(substr(display_id, 3) AS INTEGER), display_id
                """,
                (transaction_date.isoformat(),),
            ).fetchall()
        return [_transaction_from_row(row) for row in rows]

    def list_date_summaries(self) -> list[TransactionDateSummary]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT transaction_date, COUNT(*) AS transaction_count
                FROM transactions
                GROUP BY transaction_date
                ORDER BY transaction_date DESC
                """
            ).fetchall()
        try:
            return [
                TransactionDateSummary(
                    transaction_date=validate_transaction_date(
                        row["transaction_date"]
                    ),
                    transaction_count=row["transaction_count"],
                )
                for row in rows
            ]
        except (TypeError, ValueError) as error:
            raise StorageError(
                f"SQLite Transaction date summary is invalid: {error}"
            ) from error

    def replace(self, transaction: Transaction) -> Transaction:
        with self._database.transaction() as connection:
            row = connection.execute(
                f"""
                SELECT {_TRANSACTION_COLUMNS}
                FROM transactions
                WHERE id = ?
                """,
                (transaction.id,),
            ).fetchone()
            if row is None:
                raise RepositoryTransactionNotFoundError(
                    f"Transaction id {transaction.id} no longer exists."
                )
            existing = _transaction_from_row(row)
            persisted = replace(
                transaction,
                id=existing.id,
                display_id=existing.display_id,
                created_at=existing.created_at,
            )
            _validate_transaction(persisted)
            connection.execute(
                """
                UPDATE transactions
                SET type = ?, amount = ?, category = ?, category_id = ?,
                    account = ?, account_id = ?, description = ?,
                    transaction_date = ?, created_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    persisted.type,
                    serialize_amount(persisted.amount),
                    persisted.category,
                    persisted.category_id,
                    persisted.account,
                    persisted.account_id,
                    persisted.description,
                    persisted.transaction_date.isoformat(),
                    persisted.created_at.isoformat()
                    if persisted.created_at is not None
                    else None,
                    persisted.updated_at.isoformat()
                    if persisted.updated_at is not None
                    else None,
                    persisted.id,
                ),
            )
            return persisted

    def delete_by_id(self, transaction_id: str) -> bool:
        with self._database.transaction() as connection:
            deleted = connection.execute(
                "DELETE FROM transactions WHERE id = ?",
                (transaction_id,),
            )
            return deleted.rowcount == 1
