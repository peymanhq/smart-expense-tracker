"""Shared helpers for safe JSON persistence."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class StorageError(Exception):
    """Raised when application data cannot be safely loaded or saved."""


def write_json_atomic(
    data_file: Path,
    data: Any,
    *,
    data_name: str,
) -> None:
    """Write JSON through a flushed same-directory file and atomic replace."""
    temporary_path: Path | None = None

    try:
        data_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=data_file.parent,
            prefix=f".{data_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(data, temporary_file, indent=4)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, data_file)
    except (OSError, TypeError, ValueError) as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise StorageError(f"Could not save {data_name}: {error}") from error
