"""JSON-to-SQLite migration contracts."""

from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from application import build_json_application, build_sqlite_application
from persistence_errors import StorageError
from sqlite_account_repository import SQLiteAccountRepository
from sqlite_category_repository import SQLiteCategoryRepository
from sqlite_database import SQLiteDatabase
from sqlite_migration import migrate_json_to_sqlite
from sqlite_schema import initialize_schema
from sqlite_transaction_repository import SQLiteTransactionRepository
from transaction import Transaction
from transaction_repository import JsonTransactionRepository

TODAY = date(2026, 8, 3)
NOW = datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc)


def _populate_json_workspace(workspace: Path) -> tuple:
    application = build_json_application(
        workspace,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )
    account = application.account_service.add_account("Cash").account
    category = application.category_service.add_category(
        "Food",
        "expense",
    ).category
    assert account is not None
    assert category is not None
    first = application.transaction_service.add_transaction(
        transaction_date=TODAY,
        transaction_type="expense",
        amount=12.5,
        category=category.name,
        account=account.name,
        description="Lunch",
        account_id=account.id,
        category_id=category.id,
    )
    second = application.transaction_service.add_transaction(
        transaction_date=TODAY,
        transaction_type="expense",
        amount=4.25,
        category=category.name,
        account=account.name,
        description="Coffee",
        account_id=account.id,
        category_id=category.id,
    )
    application.transaction_service.delete_transaction(
        second.display_id,
        active_date=TODAY,
    )
    return account, category, first


def _json_bytes(workspace: Path) -> dict[str, bytes]:
    data_directory = workspace / "data"
    return {
        path.name: path.read_bytes()
        for path in data_directory.iterdir()
        if path.suffix == ".json"
    }


def test_migration_preserves_records_counters_and_json_files(tmp_path: Path) -> None:
    account, category, transaction = _populate_json_workspace(tmp_path)
    original_json = _json_bytes(tmp_path)

    result = migrate_json_to_sqlite(tmp_path)

    assert result.account_count == 1
    assert result.category_count == 1
    assert result.transaction_count == 1
    assert result.already_migrated is False
    assert _json_bytes(tmp_path) == original_json

    application = build_sqlite_application(
        tmp_path,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )
    assert application.account_list() == [account]
    assert application.category_list() == [category]
    assert application.transaction_service.list_transactions() == [transaction]
    assert (
        application.account_service.add_account("Bank").account.display_id
        == "A-0002"
    )
    assert (
        application.category_service.add_category(
            "Travel",
            "expense",
        ).category.display_id
        == "C-0002"
    )
    created = application.transaction_service.add_transaction(
        transaction_date=TODAY,
        transaction_type="expense",
        amount=7,
        category=category.name,
        account=account.name,
        description="Snack",
        account_id=account.id,
        category_id=category.id,
    )
    assert created.display_id == "T-0003"


def test_identical_migration_is_idempotent(tmp_path: Path) -> None:
    _populate_json_workspace(tmp_path)
    migrate_json_to_sqlite(tmp_path)

    repeated = migrate_json_to_sqlite(tmp_path)

    assert repeated.already_migrated is True
    assert repeated.transaction_count == 1


def test_migration_rejects_different_nonempty_destination(tmp_path: Path) -> None:
    _populate_json_workspace(tmp_path)
    migrate_json_to_sqlite(tmp_path)
    sqlite_application = build_sqlite_application(tmp_path)
    sqlite_application.account_service.add_account("Bank")

    with pytest.raises(StorageError, match="different data"):
        migrate_json_to_sqlite(tmp_path)


def test_migration_rejects_empty_destination_with_consumed_counter(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase.for_workspace(tmp_path)
    initialize_schema(database)
    with database.transaction() as connection:
        connection.execute(
            """UPDATE display_id_counters SET next_value = 2
               WHERE entity_type = 'account'"""
        )

    with pytest.raises(StorageError, match="different data"):
        migrate_json_to_sqlite(tmp_path)


def test_foreign_key_failure_rolls_back_every_imported_record(
    tmp_path: Path,
) -> None:
    transaction_file = tmp_path / "data" / "transactions.json"
    JsonTransactionRepository(transaction_file).create(
        Transaction(
            id=str(uuid4()),
            display_id="ignored",
            type="expense",
            amount=10,
            category="Missing category",
            account="Missing account",
            description="Orphan",
            transaction_date=TODAY,
            created_at=NOW,
            updated_at=NOW,
            account_id=str(uuid4()),
            category_id=str(uuid4()),
        )
    )

    with pytest.raises(StorageError, match="SQLite constraints"):
        migrate_json_to_sqlite(tmp_path)

    database = SQLiteDatabase.for_workspace(tmp_path)
    initialize_schema(database)
    assert SQLiteAccountRepository(database).list_all() == []
    assert SQLiteCategoryRepository(database).list_all() == []
    assert SQLiteTransactionRepository(database).list_all() == []
    with database.connection() as connection:
        counters = dict(
            connection.execute(
                "SELECT entity_type, next_value FROM display_id_counters"
            ).fetchall()
        )
    assert counters == {"account": 1, "category": 1, "transaction": 1}


def test_invalid_json_fails_before_database_creation(tmp_path: Path) -> None:
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    (data_directory / "accounts.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(StorageError, match="malformed JSON"):
        migrate_json_to_sqlite(tmp_path)

    assert not (data_directory / "smart_expense_tracker.sqlite3").exists()
