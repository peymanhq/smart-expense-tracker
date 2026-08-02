"""SQLite connection and transaction infrastructure."""

import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from persistence_errors import StorageError

DEFAULT_SQLITE_FILENAME = "smart_expense_tracker.sqlite3"
DEFAULT_BUSY_TIMEOUT_MS = 5_000


def sqlite_database_path(workspace_root: Path | str | None = None) -> Path:
    """Return the SQLite path for one workspace without creating it."""
    data_directory = (
        Path("data")
        if workspace_root is None
        else Path(workspace_root) / "data"
    )
    return data_directory / DEFAULT_SQLITE_FILENAME


class SQLiteDatabase:
    """Create configured, short-lived SQLite connections for one database."""

    def __init__(
        self,
        path: Path | str,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if (
            not isinstance(busy_timeout_ms, int)
            or isinstance(busy_timeout_ms, bool)
            or busy_timeout_ms < 0
        ):
            raise ValueError("busy_timeout_ms must be a non-negative integer.")
        self.path = Path(path)
        self.busy_timeout_ms = busy_timeout_ms

    @classmethod
    def for_workspace(
        cls,
        workspace_root: Path | str | None = None,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> "SQLiteDatabase":
        """Create a database handle using the application workspace policy."""
        return cls(
            sqlite_database_path(workspace_root),
            busy_timeout_ms=busy_timeout_ms,
        )

    def _prepare_parent_directory(self) -> None:
        if str(self.path) == ":memory:":
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise StorageError(
                f"Could not create SQLite database directory for {self.path}."
            ) from error

    def _open_connection(self) -> sqlite3.Connection:
        self._prepare_parent_directory()
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.path,
                isolation_level=None,
                timeout=self.busy_timeout_ms / 1_000,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                f"PRAGMA busy_timeout = {self.busy_timeout_ms}"
            )
            foreign_keys = connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()
            if foreign_keys is None or foreign_keys[0] != 1:
                connection.close()
                raise StorageError(
                    "Could not enable SQLite foreign-key enforcement."
                )
            return connection
        except StorageError:
            raise
        except (OSError, ValueError, sqlite3.Error) as error:
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass
            raise StorageError(
                f"Could not open or configure SQLite database {self.path}."
            ) from error

    @staticmethod
    def _close_connection(connection: sqlite3.Connection) -> None:
        try:
            connection.close()
        except sqlite3.Error as error:
            if sys.exc_info()[0] is None:
                raise StorageError("Could not close SQLite database.") from error

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield one configured connection and always close it."""
        connection = self._open_connection()
        try:
            yield connection
        except sqlite3.Error as error:
            raise StorageError("SQLite database operation failed.") from error
        finally:
            self._close_connection(connection)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run one atomic write transaction using ``BEGIN IMMEDIATE``."""
        connection = self._open_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            raise StorageError("SQLite transaction failed.") from error
        except BaseException:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            self._close_connection(connection)
