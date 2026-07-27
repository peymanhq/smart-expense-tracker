"""SQLite schema version and data-integrity contracts."""

import sqlite3
from pathlib import Path

import pytest

import sqlite_schema
from persistence_errors import StorageError, UnsupportedSchemaVersionError
from sqlite_database import SQLiteDatabase
from sqlite_schema import SCHEMA_VERSION, initialize_schema, validate_schema

ACCOUNT_ID = "00000000-0000-4000-8000-000000000001"
SECOND_ACCOUNT_ID = "00000000-0000-4000-8000-000000000002"
CATEGORY_ID = "00000000-0000-4000-8000-000000000003"
SECOND_CATEGORY_ID = "00000000-0000-4000-8000-000000000004"
TRANSACTION_ID = "00000000-0000-4000-8000-000000000005"


@pytest.fixture
def database(tmp_path: Path) -> SQLiteDatabase:
    result = SQLiteDatabase(tmp_path / "database.sqlite3")
    initialize_schema(result)
    return result


def insert_account(
    connection: sqlite3.Connection,
    *,
    account_id: str = ACCOUNT_ID,
    display_id: str = "A-0001",
    name: str = "Cash",
    name_key: str = "cash",
    is_active: int = 1,
) -> None:
    connection.execute(
        """
        INSERT INTO accounts(id, display_id, name, name_key, is_active)
        VALUES (?, ?, ?, ?, ?)
        """,
        (account_id, display_id, name, name_key, is_active),
    )


def insert_category(
    connection: sqlite3.Connection,
    *,
    category_id: str = CATEGORY_ID,
    display_id: str = "C-0001",
    name: str = "Food",
    name_key: str = "food",
    transaction_type: str = "expense",
    is_active: int = 1,
) -> None:
    connection.execute(
        """
        INSERT INTO categories(
            id, display_id, name, name_key, transaction_type, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            category_id,
            display_id,
            name,
            name_key,
            transaction_type,
            is_active,
        ),
    )


def insert_transaction(
    connection: sqlite3.Connection,
    *,
    transaction_id: str = TRANSACTION_ID,
    display_id: str = "T-0001",
    transaction_type: str = "expense",
    amount: float = 12.5,
    account_id: str | None = ACCOUNT_ID,
    category_id: str | None = CATEGORY_ID,
) -> None:
    connection.execute(
        """
        INSERT INTO transactions(
            id, display_id, type, amount, category, category_id,
            account, account_id, description, transaction_date,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'Food', ?, 'Cash', ?, 'Lunch', '2026-07-27',
                '2026-07-27T10:30:00+00:00', NULL)
        """,
        (
            transaction_id,
            display_id,
            transaction_type,
            amount,
            category_id,
            account_id,
        ),
    )


def test_empty_database_initializes_to_version_one(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")

    initialize_schema(database)

    with database.connection() as connection:
        version = connection.execute(
            "SELECT schema_version FROM schema_metadata"
        ).fetchone()["schema_version"]
        counters = {
            row["entity_type"]: row["next_value"]
            for row in connection.execute(
                "SELECT entity_type, next_value FROM display_id_counters"
            )
        }
    assert version == SCHEMA_VERSION == 1
    assert counters == {"account": 1, "category": 1, "transaction": 1}


def test_repeated_initialization_is_idempotent(database: SQLiteDatabase) -> None:
    with database.transaction() as connection:
        insert_account(connection)

    initialize_schema(database)

    with database.connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM accounts"
        ).fetchone()["count"] == 1


def test_valid_version_one_schema_is_accepted(
    database: SQLiteDatabase,
) -> None:
    validate_schema(database)


@pytest.mark.parametrize("version", [2, 7])
def test_newer_schema_is_rejected(
    database: SQLiteDatabase,
    version: int,
) -> None:
    with database.connection() as connection:
        connection.execute(
            "UPDATE schema_metadata SET schema_version = ?",
            (version,),
        )

    with pytest.raises(UnsupportedSchemaVersionError, match="newer"):
        initialize_schema(database)


def test_older_schema_is_rejected_until_migrations_exist(
    database: SQLiteDatabase,
) -> None:
    with database.connection() as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE schema_metadata SET schema_version = 0"
        )

    with pytest.raises(UnsupportedSchemaVersionError, match="older"):
        validate_schema(database)


def test_malformed_schema_metadata_is_rejected(
    database: SQLiteDatabase,
) -> None:
    with database.connection() as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE schema_metadata SET schema_version = 'invalid'"
        )

    with pytest.raises(StorageError, match="non-negative integer"):
        validate_schema(database)


def test_partially_created_schema_is_rejected(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")
    with database.connection() as connection:
        connection.execute("CREATE TABLE accounts(id TEXT PRIMARY KEY)")

    with pytest.raises(StorageError, match="does not match"):
        initialize_schema(database)


def test_missing_required_table_is_detected(
    database: SQLiteDatabase,
) -> None:
    with database.connection() as connection:
        connection.execute("DROP TABLE transactions")

    with pytest.raises(StorageError, match="does not match"):
        validate_schema(database)


def test_missing_required_column_is_detected(
    database: SQLiteDatabase,
) -> None:
    with database.connection() as connection:
        connection.execute(
            "ALTER TABLE transactions DROP COLUMN updated_at"
        )

    with pytest.raises(StorageError, match="transactions"):
        validate_schema(database)


def test_missing_required_index_is_detected(
    database: SQLiteDatabase,
) -> None:
    with database.connection() as connection:
        connection.execute("DROP INDEX transactions_date_idx")

    with pytest.raises(StorageError, match="transactions_date_idx"):
        validate_schema(database)


def test_weakened_partial_unique_index_is_detected(
    database: SQLiteDatabase,
) -> None:
    with database.connection() as connection:
        connection.execute("DROP INDEX accounts_active_name_uq")
        connection.execute(
            """
            CREATE UNIQUE INDEX accounts_active_name_uq
            ON accounts(name_key)
            WHERE is_active = 0
            """
        )

    with pytest.raises(StorageError, match="accounts_active_name_uq"):
        validate_schema(database)


def test_required_columns_foreign_keys_indexes_and_triggers_exist(
    database: SQLiteDatabase,
) -> None:
    expected_columns = {
        "accounts": {
            "id", "display_id", "name", "name_key", "is_active",
        },
        "categories": {
            "id", "display_id", "name", "name_key",
            "transaction_type", "is_active",
        },
        "transactions": {
            "id", "display_id", "type", "amount", "category",
            "category_id", "account", "account_id", "description",
            "transaction_date", "created_at", "updated_at",
        },
    }
    with database.connection() as connection:
        for table, columns in expected_columns.items():
            assert {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})")
            } == columns
        foreign_keys = {
            (row["from"], row["table"], row["on_delete"])
            for row in connection.execute(
                "PRAGMA foreign_key_list(transactions)"
            )
        }
        index_names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        trigger_names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }

    assert foreign_keys == {
        ("account_id", "accounts", "RESTRICT"),
        ("category_id", "categories", "RESTRICT"),
    }
    assert set(sqlite_schema._REQUIRED_INDEXES).issubset(index_names)
    assert {
        "display_id_counters_no_regression",
        "display_id_counters_no_delete",
    }.issubset(trigger_names)


def test_schema_initialization_is_atomic_on_statement_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")
    monkeypatch.setattr(
        sqlite_schema,
        "_SCHEMA_STATEMENTS",
        (*sqlite_schema._SCHEMA_STATEMENTS[:-2], "INVALID SQL"),
    )

    with pytest.raises(StorageError):
        initialize_schema(database)

    with database.connection() as connection:
        tables = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
    assert tables == []


def test_duplicate_account_uuid_and_display_id_are_rejected(
    database: SQLiteDatabase,
) -> None:
    with database.transaction() as connection:
        insert_account(connection)

    with pytest.raises(StorageError) as duplicate_uuid:
        with database.transaction() as connection:
            insert_account(
                connection,
                display_id="A-0002",
                name="Savings",
                name_key="savings",
                is_active=0,
            )
    with pytest.raises(StorageError) as duplicate_display:
        with database.transaction() as connection:
            insert_account(
                connection,
                account_id=SECOND_ACCOUNT_ID,
                name="Savings",
                name_key="savings",
                is_active=0,
            )

    assert isinstance(duplicate_uuid.value.__cause__, sqlite3.IntegrityError)
    assert isinstance(duplicate_display.value.__cause__, sqlite3.IntegrityError)


@pytest.mark.parametrize(
    ("table", "statement"),
    [
        (
            "accounts",
            """
            INSERT INTO accounts(id, display_id, name, name_key, is_active)
            VALUES ('not-a-uuid', 'A-0001', 'Cash', 'cash', 1)
            """,
        ),
        (
            "accounts",
            f"""
            INSERT INTO accounts(id, display_id, name, name_key, is_active)
            VALUES ('{ACCOUNT_ID}', 'A-1', 'Cash', 'cash', 1)
            """,
        ),
        (
            "accounts",
            f"""
            INSERT INTO accounts(id, display_id, name, name_key, is_active)
            VALUES ('{ACCOUNT_ID}', 'A-0001', 'Cash', 'cash', 2)
            """,
        ),
        (
            "categories",
            f"""
            INSERT INTO categories(
                id, display_id, name, name_key, transaction_type, is_active
            )
            VALUES ('{CATEGORY_ID}', 'C-0001', 'Food', 'food', 'transfer', 1)
            """,
        ),
    ],
)
def test_invalid_identity_type_and_active_values_are_rejected(
    database: SQLiteDatabase,
    table: str,
    statement: str,
) -> None:
    with pytest.raises(StorageError) as caught:
        with database.transaction() as connection:
            connection.execute(statement)

    assert table in {"accounts", "categories"}
    assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)


def test_account_active_unicode_name_key_uniqueness_and_inactive_reuse(
    database: SQLiteDatabase,
) -> None:
    with database.transaction() as connection:
        insert_account(
            connection,
            name="Café",
            name_key="café",
        )
        insert_account(
            connection,
            account_id=SECOND_ACCOUNT_ID,
            display_id="A-0002",
            name="CAFE\u0301",
            name_key="café",
            is_active=0,
        )

    with pytest.raises(StorageError):
        with database.transaction() as connection:
            connection.execute(
                "UPDATE accounts SET is_active = 1 WHERE id = ?",
                (SECOND_ACCOUNT_ID,),
            )


def test_category_active_uniqueness_is_scoped_by_type_and_allows_inactive(
    database: SQLiteDatabase,
) -> None:
    with database.transaction() as connection:
        insert_category(connection, name="Café", name_key="café")
        insert_category(
            connection,
            category_id=SECOND_CATEGORY_ID,
            display_id="C-0002",
            name="CAFE\u0301",
            name_key="café",
            transaction_type="income",
        )
        insert_category(
            connection,
            category_id="00000000-0000-4000-8000-000000000006",
            display_id="C-0003",
            name="CAFÉ",
            name_key="café",
            is_active=0,
        )

    with pytest.raises(StorageError):
        with database.transaction() as connection:
            insert_category(
                connection,
                category_id="00000000-0000-4000-8000-000000000007",
                display_id="C-0004",
                name="café",
                name_key="café",
            )


def test_transaction_constraints_reject_duplicate_display_type_and_amount(
    database: SQLiteDatabase,
) -> None:
    with database.transaction() as connection:
        insert_account(connection)
        insert_category(connection)
        insert_transaction(connection)

    for transaction_id, display_id, transaction_type, amount in (
        (
            "00000000-0000-4000-8000-000000000006",
            "T-0001",
            "expense",
            1.0,
        ),
        (
            "00000000-0000-4000-8000-000000000007",
            "T-0002",
            "transfer",
            1.0,
        ),
        (
            "00000000-0000-4000-8000-000000000008",
            "T-0003",
            "expense",
            0.0,
        ),
    ):
        with pytest.raises(StorageError):
            with database.transaction() as connection:
                insert_transaction(
                    connection,
                    transaction_id=transaction_id,
                    display_id=display_id,
                    transaction_type=transaction_type,
                    amount=amount,
                )


def test_invalid_foreign_keys_are_rejected(database: SQLiteDatabase) -> None:
    with pytest.raises(StorageError) as caught:
        with database.transaction() as connection:
            insert_transaction(
                connection,
                account_id=SECOND_ACCOUNT_ID,
                category_id=SECOND_CATEGORY_ID,
            )

    assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)


def test_referenced_managed_records_cannot_be_deleted(
    database: SQLiteDatabase,
) -> None:
    with database.transaction() as connection:
        insert_account(connection)
        insert_category(connection)
        insert_transaction(connection)

    for table, record_id in (
        ("accounts", ACCOUNT_ID),
        ("categories", CATEGORY_ID),
    ):
        with pytest.raises(StorageError):
            with database.transaction() as connection:
                connection.execute(
                    f"DELETE FROM {table} WHERE id = ?",
                    (record_id,),
                )


def test_counter_keys_values_regression_and_deletion_are_protected(
    database: SQLiteDatabase,
) -> None:
    invalid_operations = (
        """
        INSERT INTO display_id_counters(entity_type, next_value)
        VALUES ('account', 2)
        """,
        """
        INSERT INTO display_id_counters(entity_type, next_value)
        VALUES ('other', 1)
        """,
        """
        UPDATE display_id_counters SET next_value = 0
        WHERE entity_type = 'account'
        """,
        """
        UPDATE display_id_counters SET next_value = 0
        WHERE entity_type = 'category'
        """,
        """
        DELETE FROM display_id_counters WHERE entity_type = 'transaction'
        """,
    )
    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE display_id_counters SET next_value = 8
            WHERE entity_type = 'category'
            """
        )

    for statement in invalid_operations:
        with pytest.raises(StorageError):
            with database.transaction() as connection:
                connection.execute(statement)

    with database.connection() as connection:
        value = connection.execute(
            """
            SELECT next_value FROM display_id_counters
            WHERE entity_type = 'category'
            """
        ).fetchone()["next_value"]
    assert value == 8
