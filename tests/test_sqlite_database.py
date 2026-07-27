"""SQLite path, connection, and transaction foundation contracts."""

import sqlite3
from pathlib import Path

import pytest

from persistence_errors import StorageError
from sqlite_database import SQLiteDatabase, sqlite_database_path
from sqlite_schema import initialize_schema


def test_explicit_workspace_path_is_isolated_without_file_creation(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"

    path = sqlite_database_path(workspace)

    assert path == workspace / "data" / "smart_expense_tracker.sqlite3"
    assert not workspace.exists()


def test_default_path_remains_relative_to_current_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    path = sqlite_database_path()

    assert path == Path("data/smart_expense_tracker.sqlite3")
    assert not path.is_absolute()
    assert not (tmp_path / "data").exists()


def test_connection_creates_parent_and_configures_rows_and_pragmas(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase.for_workspace(tmp_path)

    with database.connection() as connection:
        row = connection.execute("SELECT 7 AS value").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()

    assert isinstance(row, sqlite3.Row)
    assert row["value"] == 7
    assert foreign_keys[0] == 1
    assert busy_timeout[0] == 5_000
    assert database.path.exists()


def test_connections_are_not_shared(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")

    with database.connection() as first:
        with database.connection() as second:
            assert first is not second


def test_connection_is_closed_after_context_exit(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")

    with database.connection() as connection:
        connection.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_memory_database_does_not_create_a_filesystem_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    database = SQLiteDatabase(":memory:")

    with database.connection() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1

    assert list(tmp_path.iterdir()) == []


def test_parent_directory_failure_is_translated(tmp_path: Path) -> None:
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("blocking")
    database = SQLiteDatabase(blocking_file / "database.sqlite3")

    with pytest.raises(StorageError) as caught:
        with database.connection():
            pass

    assert isinstance(caught.value.__cause__, OSError)


def test_raw_sqlite_operation_failure_is_translated(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")

    with pytest.raises(StorageError) as caught:
        with database.connection() as connection:
            connection.execute("SELECT * FROM missing_table")

    assert isinstance(caught.value.__cause__, sqlite3.Error)


def test_transaction_commits_once_on_success(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")
    with database.connection() as connection:
        connection.execute("CREATE TABLE records(value TEXT NOT NULL)")

    with database.transaction() as connection:
        connection.execute("INSERT INTO records(value) VALUES ('committed')")

    with database.connection() as connection:
        values = [
            row["value"]
            for row in connection.execute("SELECT value FROM records")
        ]
    assert values == ["committed"]


def test_transaction_rolls_back_and_preserves_application_exception(
    tmp_path: Path,
) -> None:
    class ApplicationFailure(RuntimeError):
        pass

    database = SQLiteDatabase(tmp_path / "database.sqlite3")
    with database.connection() as connection:
        connection.execute("CREATE TABLE records(value TEXT NOT NULL)")

    with pytest.raises(ApplicationFailure, match="business failure"):
        with database.transaction() as connection:
            connection.execute("INSERT INTO records(value) VALUES ('partial')")
            raise ApplicationFailure("business failure")

    with database.connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM records"
        ).fetchone()["count"]
    assert count == 0


def test_transaction_rolls_back_and_translates_sqlite_failure(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")
    with database.connection() as connection:
        connection.execute(
            "CREATE TABLE records(value TEXT NOT NULL UNIQUE)"
        )

    with pytest.raises(StorageError) as caught:
        with database.transaction() as connection:
            connection.execute("INSERT INTO records(value) VALUES ('same')")
            connection.execute("INSERT INTO records(value) VALUES ('same')")

    assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)
    with database.connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM records"
        ).fetchone()["count"]
    assert count == 0


def test_foreign_keys_are_enforced_inside_transactions(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")
    initialize_schema(database)

    with pytest.raises(StorageError) as caught:
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO transactions(
                    id, display_id, type, amount, category, category_id,
                    account, account_id, description, transaction_date
                )
                VALUES (?, 'T-0001', 'expense', 1.0, 'Food', ?, 'Cash', ?,
                        '', '2026-07-27')
                """,
                (
                    "00000000-0000-4000-8000-000000000001",
                    "00000000-0000-4000-8000-000000000002",
                    "00000000-0000-4000-8000-000000000003",
                ),
            )

    assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)
    with database.connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM transactions"
        ).fetchone()["count"]
    assert count == 0


def test_concurrent_write_failure_leaves_no_partial_second_write(
    tmp_path: Path,
) -> None:
    path = tmp_path / "database.sqlite3"
    first_database = SQLiteDatabase(path, busy_timeout_ms=0)
    second_database = SQLiteDatabase(path, busy_timeout_ms=0)
    with first_database.connection() as connection:
        connection.execute(
            "CREATE TABLE records(value TEXT NOT NULL UNIQUE)"
        )

    with first_database.transaction() as first:
        first.execute("INSERT INTO records(value) VALUES ('first')")
        with pytest.raises(StorageError) as caught:
            with second_database.transaction() as second:
                second.execute(
                    "INSERT INTO records(value) VALUES ('second')"
                )

    assert isinstance(caught.value.__cause__, sqlite3.OperationalError)
    with first_database.connection() as connection:
        values = [
            row["value"]
            for row in connection.execute("SELECT value FROM records")
        ]
    assert values == ["first"]
