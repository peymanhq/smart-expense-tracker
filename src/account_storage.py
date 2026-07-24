"""Validated, atomic JSON persistence for account data."""

import json
import os
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from threading import local
from typing import Any, Iterator
from uuid import UUID

from account import Account, account_name_key
from id_generator import (
    calculate_next_account_display_id,
    generate_account_display_id,
    parse_account_display_id,
)
from json_storage import StorageError, write_json_atomic

BASE_DIR = Path(__file__).resolve().parent.parent
ACCOUNTS_FILE = BASE_DIR / "data" / "accounts.json"
ACCOUNT_STATE_FILE = BASE_DIR / "data" / "accounts_state.json"

_LOCK_STATE = local()


def _read_json_file(data_file: Path, data_name: str) -> Any | None:
    if not data_file.exists():
        return None

    try:
        content = data_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise StorageError(f"Could not read {data_name}: {error}") from error

    if not content.strip():
        return None

    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise StorageError(
            f"{data_name.title()} contains malformed JSON at line {error.lineno}, "
            f"column {error.colno}."
        ) from error


def _lock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _unlock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def account_file_lock(accounts_file: Path = ACCOUNTS_FILE) -> Iterator[None]:
    """Serialize complete account read-modify-write operations."""
    lock_path = accounts_file.with_name(f".{accounts_file.name}.lock")
    depths = getattr(_LOCK_STATE, "depths", None)
    if depths is None:
        depths = {}
        _LOCK_STATE.depths = depths

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_key = str(lock_path.resolve())
    except OSError as error:
        raise StorageError(f"Could not lock account data: {error}") from error

    if lock_key in depths:
        depths[lock_key] += 1
        try:
            yield
        finally:
            depths[lock_key] -= 1
        return

    try:
        with lock_path.open("a+b") as lock_file:
            _lock_file(lock_file)
            depths[lock_key] = 1
            try:
                yield
            finally:
                del depths[lock_key]
                _unlock_file(lock_file)
    except OSError as error:
        raise StorageError(f"Could not lock account data: {error}") from error


def _validate_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise StorageError(f"{field_name} must be a UUID string.")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as error:
        raise StorageError(f"{field_name} must be a valid UUID.") from error
    if str(parsed) != value:
        raise StorageError(f"{field_name} must use canonical UUID format.")
    return value


def _validate_display_id(value: Any) -> str:
    if not isinstance(value, str):
        raise StorageError("Account display_id must be a string.")
    number = parse_account_display_id(value)
    if number is None or generate_account_display_id(number) != value:
        raise StorageError(
            "Account display_id must use canonical format such as A-0001."
        )
    return value


def _deserialize_accounts(raw_accounts: Any) -> list[Account]:
    if not isinstance(raw_accounts, list):
        raise StorageError("Account data accounts must be a JSON list.")

    accounts: list[Account] = []
    expected_fields = {"id", "display_id", "name", "is_active"}
    for index, item in enumerate(raw_accounts):
        if not isinstance(item, dict):
            raise StorageError("Every account entry must be a JSON object.")
        if set(item) != expected_fields:
            raise StorageError(
                f"Account entry {index} must contain exactly: "
                "id, display_id, name, is_active."
            )

        account_id = _validate_uuid(item["id"], f"Account entry {index} id")
        display_id = _validate_display_id(item["display_id"])
        name = item["name"]
        if not isinstance(name, str) or not name.strip():
            raise StorageError(f"Account entry {index} name must be non-empty text.")
        if name != name.strip():
            raise StorageError(
                f"Account entry {index} name must not contain outer whitespace."
            )
        is_active = item["is_active"]
        if not isinstance(is_active, bool):
            raise StorageError(f"Account entry {index} is_active must be a boolean.")

        accounts.append(
            Account(
                id=account_id,
                display_id=display_id,
                name=name,
                is_active=is_active,
            )
        )

    _validate_account_uniqueness(accounts)
    return accounts


def _validate_account_uniqueness(accounts: list[Account]) -> None:
    ids: set[str] = set()
    display_ids: set[str] = set()
    active_names: set[str] = set()

    for account in accounts:
        if account.id in ids:
            raise StorageError(f"Duplicate account id: {account.id}.")
        if account.display_id in display_ids:
            raise StorageError(
                f"Duplicate account display_id: {account.display_id}."
            )
        name_key = account_name_key(account.name)
        if account.is_active and name_key in active_names:
            raise StorageError(
                f"Duplicate active account name: {account.name}."
            )

        ids.add(account.id)
        display_ids.add(account.display_id)
        if account.is_active:
            active_names.add(name_key)


def _validate_next_account_number(value: Any, data_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise StorageError(f"{data_name} next_display_id must be a positive integer.")
    return value


def _load_account_document(accounts_file: Path) -> tuple[dict[str, Any], bool]:
    raw_data = _read_json_file(accounts_file, "account data")
    if raw_data is None:
        return {"metadata": {"next_display_id": 1}, "accounts": []}, False

    if isinstance(raw_data, list):
        accounts = _deserialize_accounts(raw_data)
        next_number = calculate_next_account_display_id(
            [account.display_id for account in accounts]
        )
        return {
            "metadata": {"next_display_id": next_number},
            "accounts": accounts,
        }, False

    if not isinstance(raw_data, dict):
        raise StorageError(
            "Account data must be a JSON object or a legacy JSON list."
        )
    if set(raw_data) != {"metadata", "accounts"}:
        raise StorageError(
            "Account data must contain exactly metadata and accounts sections."
        )

    metadata = raw_data["metadata"]
    if not isinstance(metadata, dict) or set(metadata) != {"next_display_id"}:
        raise StorageError(
            "Account data metadata must contain exactly next_display_id."
        )
    next_number = _validate_next_account_number(
        metadata["next_display_id"],
        "Account data metadata",
    )
    accounts = _deserialize_accounts(raw_data["accounts"])
    derived_next_number = calculate_next_account_display_id(
        [account.display_id for account in accounts]
    )
    if next_number < derived_next_number:
        raise StorageError(
            "Account data metadata next_display_id is behind stored account IDs."
        )

    return {
        "metadata": {"next_display_id": next_number},
        "accounts": accounts,
    }, True


def _load_legacy_next_account_number(state_file: Path) -> int:
    raw_state = _read_json_file(state_file, "legacy account display-ID state")
    if raw_state is None:
        return 1
    if not isinstance(raw_state, dict) or set(raw_state) != {"next_display_id"}:
        raise StorageError(
            "Legacy account display-ID state must contain exactly next_display_id."
        )
    return _validate_next_account_number(
        raw_state["next_display_id"],
        "Legacy account display-ID state",
    )


def load_accounts(accounts_file: Path = ACCOUNTS_FILE) -> list[Account]:
    """Load and validate accounts from current or legacy JSON."""
    document, _ = _load_account_document(accounts_file)
    return document["accounts"]


def get_next_account_display_id(
    accounts_file: Path = ACCOUNTS_FILE,
    state_file: Path = ACCOUNT_STATE_FILE,
) -> str:
    """Return the next safe account display ID without consuming it."""
    with account_file_lock(accounts_file):
        document, is_current = _load_account_document(accounts_file)
        next_number = document["metadata"]["next_display_id"]
        if not is_current:
            next_number = max(
                next_number,
                _load_legacy_next_account_number(state_file),
            )
        return generate_account_display_id(next_number)


def save_accounts(
    accounts: list[Account],
    accounts_file: Path = ACCOUNTS_FILE,
    state_file: Path = ACCOUNT_STATE_FILE,
) -> None:
    """Validate and atomically persist accounts and display-ID metadata."""
    with account_file_lock(accounts_file):
        # Validate field types and formats through the same path used by loading.
        validated_accounts = _deserialize_accounts(
            [asdict(account) for account in accounts]
        )
        previous_document, is_current = _load_account_document(accounts_file)
        next_number = max(
            previous_document["metadata"]["next_display_id"],
            calculate_next_account_display_id(
                [account.display_id for account in validated_accounts]
            ),
        )
        if not is_current:
            next_number = max(
                next_number,
                _load_legacy_next_account_number(state_file),
            )

        write_json_atomic(
            accounts_file,
            {
                "metadata": {"next_display_id": next_number},
                "accounts": [asdict(account) for account in validated_accounts],
            },
            data_name="account data",
        )
