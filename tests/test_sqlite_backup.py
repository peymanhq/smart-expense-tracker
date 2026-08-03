"""Validated SQLite backup and offline restore contracts."""

from pathlib import Path

import pytest

from application import build_sqlite_application
from sqlite_backup import (
    SQLiteBackupError,
    create_sqlite_backup,
    main,
    restore_sqlite_backup,
)
from sqlite_database import SQLiteDatabase


def _workspace_with_account(workspace: Path):
    application = build_sqlite_application(workspace)
    account = application.account_service.add_account("Cash").account
    assert account is not None
    return application, account


def test_backup_and_confirmed_restore_preserve_complete_database(
    tmp_path: Path,
) -> None:
    application, original_account = _workspace_with_account(tmp_path)
    database = SQLiteDatabase.for_workspace(tmp_path)
    backup_path = tmp_path / "backups" / "before-change.sqlite3"

    created = create_sqlite_backup(database, backup_path)
    application.account_service.add_account("Bank")
    restored = restore_sqlite_backup(
        backup_path,
        database,
        confirm_overwrite=True,
    )

    assert created == backup_path
    assert restored == database.path
    assert application.account_list() == [original_account]
    next_account = application.account_service.add_account("Wallet").account
    assert next_account is not None
    assert next_account.display_id == "A-0002"


def test_backup_does_not_modify_source_and_refuses_existing_destination(
    tmp_path: Path,
) -> None:
    _workspace_with_account(tmp_path)
    database = SQLiteDatabase.for_workspace(tmp_path)
    source_before = database.path.read_bytes()
    backup_path = tmp_path / "backup.sqlite3"
    backup_path.write_bytes(b"keep-me")

    with pytest.raises(SQLiteBackupError, match="already exists"):
        create_sqlite_backup(database, backup_path)

    assert database.path.read_bytes() == source_before
    assert backup_path.read_bytes() == b"keep-me"


def test_restore_requires_confirmation_and_rejects_invalid_backup(
    tmp_path: Path,
) -> None:
    application, original_account = _workspace_with_account(tmp_path)
    database = SQLiteDatabase.for_workspace(tmp_path)
    valid_backup = tmp_path / "valid.sqlite3"
    create_sqlite_backup(database, valid_backup)

    with pytest.raises(SQLiteBackupError, match="explicit confirmation"):
        restore_sqlite_backup(valid_backup, database)

    invalid_backup = tmp_path / "invalid.sqlite3"
    invalid_backup.write_bytes(b"not a database")
    with pytest.raises(SQLiteBackupError):
        restore_sqlite_backup(
            invalid_backup,
            database,
            confirm_overwrite=True,
        )
    assert application.account_list() == [original_account]


def test_failed_atomic_replace_preserves_existing_backup_and_cleans_temp(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _workspace_with_account(tmp_path)
    database = SQLiteDatabase.for_workspace(tmp_path)
    backup_path = tmp_path / "backup.sqlite3"
    backup_path.write_bytes(b"previous backup")

    def fail_replace(_source, _destination) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("sqlite_backup.os.replace", fail_replace)
    with pytest.raises(SQLiteBackupError, match="Could not write"):
        create_sqlite_backup(database, backup_path, overwrite=True)

    assert backup_path.read_bytes() == b"previous backup"
    assert not list(tmp_path.glob(".backup.sqlite3.*.tmp"))


def test_maintenance_cli_backup_and_restore_flow(
    tmp_path: Path,
    capsys,
) -> None:
    application, original_account = _workspace_with_account(tmp_path)
    backup_path = tmp_path / "backup.sqlite3"

    assert main(["--workspace", str(tmp_path), "backup", str(backup_path)]) == 0
    assert "SQLite backup created" in capsys.readouterr().out
    application.account_service.add_account("Bank")

    assert main(["--workspace", str(tmp_path), "restore", str(backup_path)]) == 1
    assert "explicit confirmation" in capsys.readouterr().err
    assert main(
        [
            "--workspace",
            str(tmp_path),
            "restore",
            str(backup_path),
            "--confirm-overwrite",
        ]
    ) == 0
    assert application.account_list() == [original_account]


def test_missing_source_backup_fails_without_creating_database(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase.for_workspace(tmp_path)

    with pytest.raises(SQLiteBackupError, match="does not exist"):
        create_sqlite_backup(database, tmp_path / "backup.sqlite3")

    assert not database.path.exists()
    assert not (tmp_path / "backup.sqlite3").exists()
