"""Validated atomic backup and offline restore operations for SQLite."""

import argparse
import os
import sqlite3
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from persistence_errors import StorageError
from sqlite_database import SQLiteDatabase
from sqlite_schema import validate_database_integrity, validate_schema


class SQLiteBackupError(StorageError):
    """Raised when a SQLite backup or restore cannot complete safely."""


_ROTATING_BACKUP_PREFIX = "smart-expense-tracker-"
_ROTATING_BACKUP_SUFFIX = ".sqlite3"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _existing_database(path: Path, data_name: str) -> SQLiteDatabase:
    if not path.is_file():
        raise SQLiteBackupError(f"{data_name} does not exist: {path}.")
    database = SQLiteDatabase(path)
    try:
        validate_schema(database)
    except StorageError as error:
        raise SQLiteBackupError(f"{data_name} is invalid: {path}.") from error
    return database


def _same_path(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except OSError as error:
        raise SQLiteBackupError("Could not resolve SQLite paths.") from error


def _copy_database_atomically(
    source: SQLiteDatabase,
    destination: Path,
    *,
    overwrite: bool,
) -> Path:
    if _same_path(source.path, destination):
        raise SQLiteBackupError(
            "SQLite source and destination must be different files."
        )
    if destination.exists() and not overwrite:
        raise SQLiteBackupError(
            f"SQLite destination already exists: {destination}."
        )
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(destination.parent, 0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        os.close(descriptor)
    except OSError as error:
        raise SQLiteBackupError(
            f"Could not prepare SQLite destination {destination}."
        ) from error

    temporary_path = Path(temporary_name)
    target_connection: sqlite3.Connection | None = None
    try:
        with source.connection() as source_connection:
            target_connection = sqlite3.connect(temporary_path)
            source_connection.backup(target_connection)
            target_connection.close()
            target_connection = None

        validate_schema(SQLiteDatabase(temporary_path))
        with temporary_path.open("rb") as temporary_file:
            os.fsync(temporary_file.fileno())
        if destination.exists() and not overwrite:
            raise SQLiteBackupError(
                f"SQLite destination already exists: {destination}."
            )
        os.replace(temporary_path, destination)
        return destination
    except SQLiteBackupError:
        raise
    except (OSError, sqlite3.Error) as error:
        raise SQLiteBackupError(
            f"Could not write SQLite destination {destination}."
        ) from error
    finally:
        if target_connection is not None:
            try:
                target_connection.close()
            except sqlite3.Error:
                pass
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def create_sqlite_backup(
    database: SQLiteDatabase,
    destination: Path | str,
    *,
    overwrite: bool = False,
) -> Path:
    """Create a validated backup without modifying the live database."""
    source = _existing_database(database.path, "SQLite database")
    return _copy_database_atomically(
        source,
        Path(destination),
        overwrite=overwrite,
    )


def create_rotating_sqlite_backup(
    database: SQLiteDatabase,
    destination_directory: Path | str,
    *,
    keep: int = 7,
    utc_now_provider: Callable[[], datetime] = _utc_now,
) -> Path:
    """Create one timestamped backup and retain only the newest ``keep`` files."""
    if not isinstance(keep, int) or isinstance(keep, bool) or keep < 1:
        raise ValueError("keep must be a positive integer.")
    timestamp = utc_now_provider()
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Backup clock must return a timezone-aware datetime.")
    timestamp = timestamp.astimezone(timezone.utc)
    directory = Path(destination_directory)
    filename = (
        f"{_ROTATING_BACKUP_PREFIX}"
        f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}"
        f"{_ROTATING_BACKUP_SUFFIX}"
    )
    created = create_sqlite_backup(database, directory / filename)

    candidates = sorted(
        (
            path
            for path in directory.glob(
                f"{_ROTATING_BACKUP_PREFIX}*{_ROTATING_BACKUP_SUFFIX}"
            )
            if path.is_file()
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    try:
        for expired in candidates[keep:]:
            expired.unlink()
    except OSError as error:
        raise SQLiteBackupError(
            f"Backup was created but retention cleanup failed in {directory}."
        ) from error
    return created


def restore_sqlite_backup(
    backup_path: Path | str,
    database: SQLiteDatabase,
    *,
    confirm_overwrite: bool = False,
) -> Path:
    """Restore a validated backup while the application is offline."""
    backup = _existing_database(Path(backup_path), "SQLite backup")
    if database.path.exists() and not confirm_overwrite:
        raise SQLiteBackupError(
            "Restoring over an existing SQLite database requires explicit "
            "confirmation."
        )
    return _copy_database_atomically(
        backup,
        database.path,
        overwrite=confirm_overwrite,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="expense-tracker-storage",
        description="Back up or restore one Smart Expense Tracker SQLite workspace.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root; defaults to the current directory.",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("destination", type=Path)
    backup_parser.add_argument("--overwrite", action="store_true")
    rotate_parser = subparsers.add_parser("rotate")
    rotate_parser.add_argument("directory", type=Path)
    rotate_parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="Number of newest managed backups to retain (default: 7).",
    )
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument(
        "--quick",
        action="store_true",
        help="Use SQLite quick_check instead of the full integrity_check.",
    )
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("backup", type=Path)
    restore_parser.add_argument(
        "--confirm-overwrite",
        action="store_true",
        help="Required when the workspace database already exists.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the storage-maintenance command without starting the main CLI."""
    arguments = _parser().parse_args(argv)
    database = SQLiteDatabase.for_workspace(arguments.workspace)
    try:
        if arguments.operation == "check":
            database = _existing_database(database.path, "SQLite database")
            validate_database_integrity(database, full=not arguments.quick)
            print(f"SQLite integrity check passed: {database.path}")
        elif arguments.operation == "backup":
            output = create_sqlite_backup(
                database,
                arguments.destination,
                overwrite=arguments.overwrite,
            )
            print(f"SQLite backup created: {output}")
        elif arguments.operation == "rotate":
            output = create_rotating_sqlite_backup(
                database,
                arguments.directory,
                keep=arguments.keep,
            )
            print(f"SQLite rotating backup created: {output}")
        else:
            output = restore_sqlite_backup(
                arguments.backup,
                database,
                confirm_overwrite=arguments.confirm_overwrite,
            )
            print(f"SQLite backup restored: {output}")
        return 0
    except StorageError as error:
        print(f"Storage maintenance error: {error}", file=sys.stderr)
        return 1
