"""Versioned SQLite schema initialization and validation."""

import re
import sqlite3
from dataclasses import dataclass

from persistence_errors import StorageError, UnsupportedSchemaVersionError
from sqlite_database import SQLiteDatabase
from validators import serialize_amount, validate_amount

SCHEMA_VERSION = 2

_UUID_GLOB = (
    "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]"
    "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]-"
    "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]-"
    "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]-"
    "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]-"
    "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]"
    "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]"
    "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]"
)


def _uuid_check(column: str) -> str:
    return (
        f"length({column}) = 36 "
        f"AND {column} = lower({column}) "
        f"AND {column} GLOB '{_UUID_GLOB}'"
    )


def _display_id_check(column: str, prefix: str) -> str:
    return f"""
        substr({column}, 3) <> ''
        AND substr({column}, 3) NOT GLOB '*[^0-9]*'
        AND CAST(substr({column}, 3) AS INTEGER) > 0
        AND {column} = '{prefix}-' ||
            printf('%04d', CAST(substr({column}, 3) AS INTEGER))
    """


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE schema_metadata (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        schema_version INTEGER NOT NULL CHECK (schema_version >= 1)
    )
    """,
    """
    CREATE TABLE display_id_counters (
        entity_type TEXT PRIMARY KEY
            CHECK (entity_type IN ('account', 'category', 'transaction')),
        next_value INTEGER NOT NULL CHECK (next_value >= 1)
    )
    """,
    f"""
    CREATE TABLE accounts (
        id TEXT PRIMARY KEY CHECK ({_uuid_check("id")}),
        display_id TEXT NOT NULL CHECK (
            {_display_id_check("display_id", "A")}
        ),
        name TEXT NOT NULL CHECK (length(name) > 0 AND name = trim(name)),
        name_key TEXT NOT NULL
            CHECK (length(name_key) > 0 AND name_key = trim(name_key)),
        is_active INTEGER NOT NULL CHECK (is_active IN (0, 1))
    )
    """,
    f"""
    CREATE TABLE categories (
        id TEXT PRIMARY KEY CHECK ({_uuid_check("id")}),
        display_id TEXT NOT NULL CHECK (
            {_display_id_check("display_id", "C")}
        ),
        name TEXT NOT NULL CHECK (length(name) > 0 AND name = trim(name)),
        name_key TEXT NOT NULL
            CHECK (length(name_key) > 0 AND name_key = trim(name_key)),
        transaction_type TEXT NOT NULL
            CHECK (transaction_type IN ('income', 'expense')),
        is_active INTEGER NOT NULL CHECK (is_active IN (0, 1))
    )
    """,
    f"""
    CREATE TABLE transactions (
        id TEXT PRIMARY KEY CHECK ({_uuid_check("id")}),
        display_id TEXT NOT NULL CHECK (
            {_display_id_check("display_id", "T")}
        ),
        type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
        amount TEXT NOT NULL CHECK (
            typeof(amount) = 'text'
            AND length(amount) > 0
            AND amount = trim(amount)
            AND amount NOT GLOB '*[^0-9.]*'
            AND length(amount) - length(replace(amount, '.', '')) <= 1
            AND substr(amount, 1, 1) <> '.'
            AND substr(amount, -1, 1) <> '.'
            AND amount GLOB '*[1-9]*'
            AND (
                substr(amount, 1, 1) <> '0'
                OR substr(amount, 2, 1) = '.'
            )
            AND (
                instr(amount, '.') = 0
                OR substr(amount, -1, 1) <> '0'
            )
        ),
        category TEXT NOT NULL,
        category_id TEXT
            CHECK (category_id IS NULL OR ({_uuid_check("category_id")}))
            REFERENCES categories(id)
            ON UPDATE RESTRICT
            ON DELETE RESTRICT,
        account TEXT NOT NULL,
        account_id TEXT
            CHECK (account_id IS NULL OR ({_uuid_check("account_id")}))
            REFERENCES accounts(id)
            ON UPDATE RESTRICT
            ON DELETE RESTRICT,
        description TEXT NOT NULL,
        transaction_date TEXT NOT NULL,
        created_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE UNIQUE INDEX accounts_display_id_uq
        ON accounts(display_id)
    """,
    """
    CREATE UNIQUE INDEX accounts_active_name_uq
        ON accounts(name_key)
        WHERE is_active = 1
    """,
    """
    CREATE INDEX accounts_active_idx
        ON accounts(is_active)
    """,
    """
    CREATE UNIQUE INDEX categories_display_id_uq
        ON categories(display_id)
    """,
    """
    CREATE UNIQUE INDEX categories_active_type_name_uq
        ON categories(transaction_type, name_key)
        WHERE is_active = 1
    """,
    """
    CREATE INDEX categories_type_active_idx
        ON categories(transaction_type, is_active)
    """,
    """
    CREATE UNIQUE INDEX transactions_display_id_uq
        ON transactions(display_id)
    """,
    """
    CREATE INDEX transactions_date_idx
        ON transactions(transaction_date)
    """,
    """
    CREATE INDEX transactions_type_idx
        ON transactions(type)
    """,
    """
    CREATE INDEX transactions_account_id_idx
        ON transactions(account_id)
    """,
    """
    CREATE INDEX transactions_category_id_idx
        ON transactions(category_id)
    """,
    """
    CREATE TRIGGER display_id_counters_no_regression
    BEFORE UPDATE OF next_value ON display_id_counters
    FOR EACH ROW
    WHEN NEW.next_value < OLD.next_value
    BEGIN
        SELECT RAISE(ABORT, 'display-ID counter cannot regress');
    END
    """,
    """
    CREATE TRIGGER display_id_counters_no_delete
    BEFORE DELETE ON display_id_counters
    FOR EACH ROW
    BEGIN
        SELECT RAISE(ABORT, 'display-ID counter cannot be deleted');
    END
    """,
    """
    INSERT INTO schema_metadata(singleton, schema_version)
    VALUES (1, 2)
    """,
    """
    INSERT INTO display_id_counters(entity_type, next_value)
    VALUES
        ('account', 1),
        ('category', 1),
        ('transaction', 1)
    """,
)

_REQUIRED_TABLES = {
    "schema_metadata",
    "display_id_counters",
    "accounts",
    "categories",
    "transactions",
}

_REQUIRED_COLUMNS = {
    "schema_metadata": {
        "singleton",
        "schema_version",
    },
    "display_id_counters": {
        "entity_type",
        "next_value",
    },
    "accounts": {
        "id",
        "display_id",
        "name",
        "name_key",
        "is_active",
    },
    "categories": {
        "id",
        "display_id",
        "name",
        "name_key",
        "transaction_type",
        "is_active",
    },
    "transactions": {
        "id",
        "display_id",
        "type",
        "amount",
        "category",
        "category_id",
        "account",
        "account_id",
        "description",
        "transaction_date",
        "created_at",
        "updated_at",
    },
}


@dataclass(frozen=True)
class _IndexContract:
    table: str
    columns: tuple[str, ...]
    unique: bool = False
    partial: bool = False


_REQUIRED_INDEXES = {
    "accounts_display_id_uq": _IndexContract(
        "accounts", ("display_id",), unique=True
    ),
    "accounts_active_name_uq": _IndexContract(
        "accounts", ("name_key",), unique=True, partial=True
    ),
    "accounts_active_idx": _IndexContract("accounts", ("is_active",)),
    "categories_display_id_uq": _IndexContract(
        "categories", ("display_id",), unique=True
    ),
    "categories_active_type_name_uq": _IndexContract(
        "categories",
        ("transaction_type", "name_key"),
        unique=True,
        partial=True,
    ),
    "categories_type_active_idx": _IndexContract(
        "categories", ("transaction_type", "is_active")
    ),
    "transactions_display_id_uq": _IndexContract(
        "transactions", ("display_id",), unique=True
    ),
    "transactions_date_idx": _IndexContract(
        "transactions", ("transaction_date",)
    ),
    "transactions_type_idx": _IndexContract("transactions", ("type",)),
    "transactions_account_id_idx": _IndexContract(
        "transactions", ("account_id",)
    ),
    "transactions_category_id_idx": _IndexContract(
        "transactions", ("category_id",)
    ),
}

_REQUIRED_TRIGGERS = {
    "display_id_counters_no_regression",
    "display_id_counters_no_delete",
}


def _normalize_sql(statement: str) -> str:
    return " ".join(statement.split()).casefold()


def _created_object_name(statement: str) -> str | None:
    match = re.match(
        r"\s*CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|TRIGGER)\s+([a-z_]+)",
        statement,
        flags=re.IGNORECASE,
    )
    return None if match is None else match.group(1)


_REQUIRED_OBJECT_SQL = {
    name: _normalize_sql(statement)
    for statement in _SCHEMA_STATEMENTS
    if (name := _created_object_name(statement)) is not None
}


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }


def _read_schema_version(connection: sqlite3.Connection) -> int:
    try:
        rows = connection.execute(
            "SELECT singleton, schema_version FROM schema_metadata"
        ).fetchall()
    except sqlite3.Error as error:
        raise StorageError("SQLite schema metadata is missing or malformed.") from error

    if len(rows) != 1 or rows[0]["singleton"] != 1:
        raise StorageError(
            "SQLite schema metadata must contain exactly one version row."
        )
    version = rows[0]["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise StorageError(
            "SQLite schema version must be a non-negative integer."
        )
    return version


def _validate_columns(connection: sqlite3.Connection) -> None:
    for table, expected_columns in _REQUIRED_COLUMNS.items():
        actual_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if actual_columns != expected_columns:
            raise StorageError(
                f"SQLite table {table} does not match schema version "
                f"{SCHEMA_VERSION}."
            )


def _validate_indexes(connection: sqlite3.Connection) -> None:
    for name, contract in _REQUIRED_INDEXES.items():
        rows = {
            row["name"]: row
            for row in connection.execute(
                f"PRAGMA index_list({contract.table})"
            )
        }
        index = rows.get(name)
        if (
            index is None
            or bool(index["unique"]) is not contract.unique
            or bool(index["partial"]) is not contract.partial
        ):
            raise StorageError(
                f"SQLite index {name} does not match schema version "
                f"{SCHEMA_VERSION}."
            )
        columns = tuple(
            row["name"]
            for row in connection.execute(f"PRAGMA index_info({name})")
        )
        if columns != contract.columns:
            raise StorageError(
                f"SQLite index {name} does not match schema version "
                f"{SCHEMA_VERSION}."
            )


def _validate_foreign_keys(connection: sqlite3.Connection) -> None:
    foreign_keys = {
        (
            row["from"],
            row["table"],
            row["to"],
            row["on_update"],
            row["on_delete"],
        )
        for row in connection.execute("PRAGMA foreign_key_list(transactions)")
    }
    expected = {
        ("account_id", "accounts", "id", "RESTRICT", "RESTRICT"),
        ("category_id", "categories", "id", "RESTRICT", "RESTRICT"),
    }
    if foreign_keys != expected:
        raise StorageError(
            "SQLite transaction foreign keys do not match schema version "
            f"{SCHEMA_VERSION}."
        )


def _validate_triggers(connection: sqlite3.Connection) -> None:
    triggers = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    if not _REQUIRED_TRIGGERS.issubset(triggers):
        raise StorageError(
            "SQLite display-ID counter protections are missing."
        )


def _validate_object_definitions(connection: sqlite3.Connection) -> None:
    definitions = {
        row["name"]: _normalize_sql(row["sql"])
        for row in connection.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type IN ('table', 'index', 'trigger') AND sql IS NOT NULL
            """
        )
    }
    for name, expected_sql in _REQUIRED_OBJECT_SQL.items():
        if definitions.get(name) != expected_sql:
            raise StorageError(
                f"SQLite object {name} does not match schema version "
                f"{SCHEMA_VERSION}."
            )


def _validate_counters(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT entity_type, next_value FROM display_id_counters"
    ).fetchall()
    counters = {row["entity_type"]: row["next_value"] for row in rows}
    if set(counters) != {"account", "category", "transaction"}:
        raise StorageError(
            "SQLite display-ID counters must contain exactly one row per "
            "entity type."
        )
    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
        for value in counters.values()
    ):
        raise StorageError("SQLite display-ID counters must be positive integers.")


def _validate_schema(connection: sqlite3.Connection) -> None:
    tables = _user_tables(connection)
    if tables != _REQUIRED_TABLES:
        raise StorageError(
            f"SQLite database does not match schema version {SCHEMA_VERSION}."
        )

    version = _read_schema_version(connection)
    if version != SCHEMA_VERSION:
        direction = "newer" if version > SCHEMA_VERSION else "older"
        raise UnsupportedSchemaVersionError(
            f"SQLite schema version {version} is {direction} than supported "
            f"version {SCHEMA_VERSION}; migrations are not implemented."
        )

    _validate_columns(connection)
    _validate_indexes(connection)
    _validate_foreign_keys(connection)
    _validate_triggers(connection)
    _validate_object_definitions(connection)
    _validate_counters(connection)

    foreign_key_errors = connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()
    if foreign_key_errors:
        raise StorageError("SQLite database contains foreign-key violations.")


def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    """Replace REAL amounts with canonical decimal TEXT atomically."""
    if _user_tables(connection) != _REQUIRED_TABLES:
        raise StorageError("SQLite schema version 1 is incomplete.")
    actual_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(transactions)")
    }
    if actual_columns != _REQUIRED_COLUMNS["transactions"]:
        raise StorageError("SQLite schema version 1 transactions are malformed.")
    amount_column = next(
        row
        for row in connection.execute("PRAGMA table_info(transactions)")
        if row["name"] == "amount"
    )
    if str(amount_column["type"]).upper() != "REAL":
        raise StorageError("SQLite schema version 1 amount must use REAL.")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise StorageError("SQLite database contains foreign-key violations.")

    rows = connection.execute(
        """SELECT id, display_id, type, amount, category, category_id,
                  account, account_id, description, transaction_date,
                  created_at, updated_at
           FROM transactions"""
    ).fetchall()
    try:
        migrated_rows = [
            (
                row["id"],
                row["display_id"],
                row["type"],
                serialize_amount(validate_amount(row["amount"])),
                row["category"],
                row["category_id"],
                row["account"],
                row["account_id"],
                row["description"],
                row["transaction_date"],
                row["created_at"],
                row["updated_at"],
            )
            for row in rows
        ]
    except ValueError as error:
        raise StorageError(
            "SQLite schema version 1 contains an invalid amount."
        ) from error

    for index_name in _REQUIRED_INDEXES:
        if _REQUIRED_INDEXES[index_name].table == "transactions":
            connection.execute(f"DROP INDEX {index_name}")
    connection.execute("ALTER TABLE transactions RENAME TO transactions_v1")
    connection.execute(_SCHEMA_STATEMENTS[4])
    connection.executemany(
        """INSERT INTO transactions(
               id, display_id, type, amount, category, category_id,
               account, account_id, description, transaction_date,
               created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        migrated_rows,
    )
    connection.execute("DROP TABLE transactions_v1")
    for statement in _SCHEMA_STATEMENTS:
        object_name = _created_object_name(statement)
        if (
            object_name in _REQUIRED_INDEXES
            and _REQUIRED_INDEXES[object_name].table == "transactions"
        ):
            connection.execute(statement)
    connection.execute(
        "UPDATE schema_metadata SET schema_version = 2 WHERE singleton = 1"
    )


def initialize_schema(database: SQLiteDatabase) -> None:
    """Atomically initialize or migrate and validate the current schema."""
    with database.transaction() as connection:
        tables = _user_tables(connection)
        if not tables:
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
        elif tables != _REQUIRED_TABLES:
            raise StorageError(
                f"SQLite database does not match schema version {SCHEMA_VERSION}."
            )
        else:
            version = _read_schema_version(connection)
            if version == 1:
                _migrate_v1_to_v2(connection)
        _validate_schema(connection)


def validate_schema(database: SQLiteDatabase) -> None:
    """Validate an existing schema without modifying it."""
    with database.connection() as connection:
        _validate_schema(connection)
