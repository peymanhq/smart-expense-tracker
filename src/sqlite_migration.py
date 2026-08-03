"""Non-destructive, all-or-nothing migration from workspace JSON to SQLite."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3

from account import Account, account_name_key
from account_storage import (
    _load_account_document,
    _load_legacy_next_account_number,
    account_file_lock,
)
from category import Category, category_name_key
from category_storage import _load_validated_data, category_file_lock
from persistence_errors import StorageError
from sqlite_database import SQLiteDatabase
from sqlite_schema import initialize_schema
from storage import (
    _deserialize_transactions,
    _read_document,
    transaction_file_lock,
)
from transaction import Transaction
from validators import serialize_amount

JSON_WORKSPACE_FILENAMES = (
    "accounts.json",
    "accounts_state.json",
    "categories.json",
    "categories_state.json",
    "transactions.json",
)


@dataclass(frozen=True)
class SQLiteMigrationResult:
    """Counts imported from one consistent JSON snapshot."""

    account_count: int
    category_count: int
    transaction_count: int
    already_migrated: bool = False


@dataclass(frozen=True)
class _JsonSnapshot:
    accounts: list[Account]
    categories: list[Category]
    transactions: list[Transaction]
    counters: dict[str, int]


def _data_path(workspace_root: Path | str | None, filename: str) -> Path:
    directory = (
        Path("data")
        if workspace_root is None
        else Path(workspace_root) / "data"
    )
    return directory / filename


def json_workspace_exists(workspace_root: Path | str | None = None) -> bool:
    """Return whether any persisted JSON compatibility file exists."""
    return any(
        _data_path(workspace_root, filename).exists()
        for filename in JSON_WORKSPACE_FILENAMES
    )


@contextmanager
def _locked_json_snapshot(
    workspace_root: Path | str | None,
) -> Iterator[_JsonSnapshot]:
    accounts_file = _data_path(workspace_root, "accounts.json")
    account_state_file = _data_path(workspace_root, "accounts_state.json")
    categories_file = _data_path(workspace_root, "categories.json")
    category_state_file = _data_path(workspace_root, "categories_state.json")
    transactions_file = _data_path(workspace_root, "transactions.json")

    with ExitStack() as locks:
        locks.enter_context(account_file_lock(accounts_file))
        locks.enter_context(category_file_lock(categories_file))
        locks.enter_context(transaction_file_lock(transactions_file))

        account_document, account_is_current = _load_account_document(accounts_file)
        account_next = account_document["metadata"]["next_display_id"]
        if not account_is_current:
            account_next = max(
                account_next,
                _load_legacy_next_account_number(account_state_file),
            )
        categories, category_next = _load_validated_data(
            categories_file,
            category_state_file,
        )
        transaction_document = _read_document(transactions_file)
        transactions = _deserialize_transactions(transaction_document)

        yield _JsonSnapshot(
            accounts=list(account_document["accounts"]),
            categories=list(categories),
            transactions=list(transactions),
            counters={
                "account": account_next,
                "category": category_next,
                "transaction": transaction_document["metadata"]["next_display_id"],
            },
        )


def _row_count(connection: sqlite3.Connection, table: str) -> int:
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _destination_is_pristine(connection: sqlite3.Connection) -> bool:
    records_are_empty = all(
        _row_count(connection, table) == 0
        for table in ("accounts", "categories", "transactions")
    )
    counters = {
        row["entity_type"]: row["next_value"]
        for row in connection.execute(
            "SELECT entity_type, next_value FROM display_id_counters"
        )
    }
    return records_are_empty and counters == {
        "account": 1,
        "category": 1,
        "transaction": 1,
    }


def _destination_matches(
    connection: sqlite3.Connection,
    snapshot: _JsonSnapshot,
) -> bool:
    account_rows = connection.execute(
        "SELECT id, display_id, name, is_active FROM accounts"
    ).fetchall()
    category_rows = connection.execute(
        """SELECT id, display_id, name, transaction_type, is_active
           FROM categories"""
    ).fetchall()
    transaction_rows = connection.execute(
        """SELECT id, display_id, type, amount, category, category_id,
                  account, account_id, description, transaction_date,
                  created_at, updated_at
           FROM transactions"""
    ).fetchall()
    counters = {
        row["entity_type"]: row["next_value"]
        for row in connection.execute(
            "SELECT entity_type, next_value FROM display_id_counters"
        )
    }
    expected_accounts = {
        (item.id, item.display_id, item.name, int(item.is_active))
        for item in snapshot.accounts
    }
    expected_categories = {
        (
            item.id,
            item.display_id,
            item.name,
            item.transaction_type,
            int(item.is_active),
        )
        for item in snapshot.categories
    }
    expected_transactions = {
        (
            item.id,
            item.display_id,
            item.type,
            serialize_amount(item.amount),
            item.category,
            item.category_id,
            item.account,
            item.account_id,
            item.description,
            item.transaction_date.isoformat(),
            item.created_at.isoformat() if item.created_at is not None else None,
            item.updated_at.isoformat() if item.updated_at is not None else None,
        )
        for item in snapshot.transactions
    }
    return (
        {tuple(row) for row in account_rows} == expected_accounts
        and {tuple(row) for row in category_rows} == expected_categories
        and {tuple(row) for row in transaction_rows} == expected_transactions
        and counters == snapshot.counters
    )


def _insert_snapshot(
    connection: sqlite3.Connection,
    snapshot: _JsonSnapshot,
) -> None:
    connection.executemany(
        """INSERT INTO accounts(id, display_id, name, name_key, is_active)
           VALUES (?, ?, ?, ?, ?)""",
        [
            (
                item.id,
                item.display_id,
                item.name,
                account_name_key(item.name),
                int(item.is_active),
            )
            for item in snapshot.accounts
        ],
    )
    connection.executemany(
        """INSERT INTO categories(
               id, display_id, name, name_key, transaction_type, is_active
           ) VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (
                item.id,
                item.display_id,
                item.name,
                category_name_key(item.name),
                item.transaction_type,
                int(item.is_active),
            )
            for item in snapshot.categories
        ],
    )
    connection.executemany(
        """INSERT INTO transactions(
               id, display_id, type, amount, category, category_id,
               account, account_id, description, transaction_date,
               created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                item.id,
                item.display_id,
                item.type,
                serialize_amount(item.amount),
                item.category,
                item.category_id,
                item.account,
                item.account_id,
                item.description,
                item.transaction_date.isoformat(),
                item.created_at.isoformat() if item.created_at is not None else None,
                item.updated_at.isoformat() if item.updated_at is not None else None,
            )
            for item in snapshot.transactions
        ],
    )
    connection.executemany(
        """UPDATE display_id_counters
           SET next_value = ? WHERE entity_type = ?""",
        [(value, entity_type) for entity_type, value in snapshot.counters.items()],
    )


def migrate_json_to_sqlite(
    workspace_root: Path | str | None = None,
    *,
    database: SQLiteDatabase | None = None,
) -> SQLiteMigrationResult:
    """Import a validated JSON snapshot without modifying its source files."""
    target = database or SQLiteDatabase.for_workspace(workspace_root)
    with _locked_json_snapshot(workspace_root) as snapshot:
        initialize_schema(target)
        with target.transaction() as connection:
            if not _destination_is_pristine(connection):
                if _destination_matches(connection, snapshot):
                    return SQLiteMigrationResult(
                        len(snapshot.accounts),
                        len(snapshot.categories),
                        len(snapshot.transactions),
                        already_migrated=True,
                    )
                raise StorageError(
                    "SQLite migration destination already contains different "
                    "data."
                )
            try:
                _insert_snapshot(connection, snapshot)
            except sqlite3.IntegrityError as error:
                raise StorageError(
                    "JSON data cannot be represented by the SQLite constraints."
                ) from error

        return SQLiteMigrationResult(
            len(snapshot.accounts),
            len(snapshot.categories),
            len(snapshot.transactions),
        )
