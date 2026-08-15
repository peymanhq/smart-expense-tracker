"""Validated SQLite backup and offline restore contracts."""

import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from application import build_sqlite_application
from sqlite_backup import (
    SQLiteBackupError,
    create_rotating_sqlite_backup,
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
    assert stat.S_IMODE(backup_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(backup_path.stat().st_mode) == 0o600
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


def test_maintenance_cli_runs_full_and_quick_integrity_checks(
    tmp_path: Path,
    capsys,
) -> None:
    _workspace_with_account(tmp_path)

    assert main(["--workspace", str(tmp_path), "check"]) == 0
    assert "integrity check passed" in capsys.readouterr().out
    assert main(["--workspace", str(tmp_path), "check", "--quick"]) == 0
    assert "integrity check passed" in capsys.readouterr().out


def test_rotating_backup_keeps_newest_managed_files_only(tmp_path: Path) -> None:
    _workspace_with_account(tmp_path)
    database = SQLiteDatabase.for_workspace(tmp_path)
    destination = tmp_path / "rotating"
    unrelated = destination / "manual.sqlite3"
    destination.mkdir()
    unrelated.write_bytes(b"keep")

    for second in range(4):
        create_rotating_sqlite_backup(
            database,
            destination,
            keep=2,
            utc_now_provider=lambda second=second: datetime(
                2026, 8, 15, 10, 0, second, tzinfo=timezone.utc
            ),
        )

    assert [path.name for path in sorted(destination.glob("smart-expense-*"))] == [
        "smart-expense-tracker-20260815T100002000000Z.sqlite3",
        "smart-expense-tracker-20260815T100003000000Z.sqlite3",
    ]
    assert unrelated.read_bytes() == b"keep"


@pytest.mark.parametrize("keep", [0, -1, True])
def test_rotating_backup_rejects_invalid_retention(
    tmp_path: Path,
    keep: int,
) -> None:
    _workspace_with_account(tmp_path)

    with pytest.raises(ValueError, match="positive integer"):
        create_rotating_sqlite_backup(
            SQLiteDatabase.for_workspace(tmp_path),
            tmp_path / "rotating",
            keep=keep,
        )


def test_maintenance_cli_creates_rotating_backup(
    tmp_path: Path,
    capsys,
) -> None:
    _workspace_with_account(tmp_path)
    destination = tmp_path / "rotating"

    assert main(
        ["--workspace", str(tmp_path), "rotate", str(destination), "--keep", "2"]
    ) == 0

    assert "rotating backup created" in capsys.readouterr().out
    assert len(list(destination.glob("smart-expense-tracker-*.sqlite3"))) == 1
