"""Validated, atomic JSON persistence for standalone category data."""

import json
import os
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from threading import local
from typing import Any, Iterator
from uuid import UUID

from category import (
    Category,
    canonicalize_category_name,
    category_name_key,
)
from id_generator import (
    calculate_next_category_display_id,
    generate_category_display_id,
    parse_category_display_id,
)
from json_storage import StorageError, write_json_atomic

CATEGORIES_FILE = Path("data") / "categories.json"
CATEGORY_STATE_FILE = Path("data") / "categories_state.json"

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
        msvcrt.locking(  # type: ignore[attr-defined]
            lock_file.fileno(), msvcrt.LK_LOCK, 1  # type: ignore[attr-defined]
        )
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _unlock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        msvcrt.locking(  # type: ignore[attr-defined]
            lock_file.fileno(), msvcrt.LK_UNLCK, 1  # type: ignore[attr-defined]
        )
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def category_file_lock(
    categories_file: Path = CATEGORIES_FILE,
) -> Iterator[None]:
    """Serialize complete category read-modify-write operations."""
    lock_path = categories_file.with_name(f".{categories_file.name}.lock")
    depths = getattr(_LOCK_STATE, "depths", None)
    if depths is None:
        depths = {}
        _LOCK_STATE.depths = depths

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_key = str(lock_path.resolve())
    except OSError as error:
        raise StorageError(f"Could not lock category data: {error}") from error

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
        raise StorageError(f"Could not lock category data: {error}") from error


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
        raise StorageError("Category display_id must be a string.")
    number = parse_category_display_id(value)
    if number is None or generate_category_display_id(number) != value:
        raise StorageError(
            "Category display_id must use canonical format such as C-0001."
        )
    return value


def _deserialize_categories(raw_categories: Any) -> list[Category]:
    if not isinstance(raw_categories, list):
        raise StorageError("Category data must be a JSON list.")

    categories: list[Category] = []
    expected_fields = {
        "id",
        "display_id",
        "name",
        "transaction_type",
        "is_active",
    }
    for index, item in enumerate(raw_categories):
        if not isinstance(item, dict):
            raise StorageError("Every category entry must be a JSON object.")
        if set(item) != expected_fields:
            raise StorageError(
                f"Category entry {index} must contain exactly: id, display_id, "
                "name, transaction_type, is_active."
            )

        category_id = _validate_uuid(item["id"], f"Category entry {index} id")
        display_id = _validate_display_id(item["display_id"])
        name = item["name"]
        if not isinstance(name, str) or not name.strip():
            raise StorageError(
                f"Category entry {index} name must be non-empty text."
            )
        if name != name.strip():
            raise StorageError(
                f"Category entry {index} name must not contain outer whitespace."
            )
        if name != canonicalize_category_name(name):
            raise StorageError(
                f"Category entry {index} name must use canonical Unicode form."
            )
        transaction_type = item["transaction_type"]
        if (
            not isinstance(transaction_type, str)
            or transaction_type not in {"income", "expense"}
        ):
            raise StorageError(
                f"Category entry {index} transaction_type must be "
                "income or expense."
            )
        is_active = item["is_active"]
        if not isinstance(is_active, bool):
            raise StorageError(
                f"Category entry {index} is_active must be a boolean."
            )

        categories.append(
            Category(
                id=category_id,
                display_id=display_id,
                name=name,
                transaction_type=transaction_type,
                is_active=is_active,
            )
        )

    _validate_category_uniqueness(categories)
    return categories


def _validate_category_uniqueness(categories: list[Category]) -> None:
    ids: set[str] = set()
    display_ids: set[str] = set()
    active_names: set[tuple[str, str]] = set()

    for category in categories:
        if category.id in ids:
            raise StorageError(f"Duplicate category id: {category.id}.")
        if category.display_id in display_ids:
            raise StorageError(
                f"Duplicate category display_id: {category.display_id}."
            )
        name_key = (category.transaction_type, category_name_key(category.name))
        if category.is_active and name_key in active_names:
            raise StorageError(
                "Duplicate active category name "
                f"for {category.transaction_type}: {category.name}."
            )

        ids.add(category.id)
        display_ids.add(category.display_id)
        if category.is_active:
            active_names.add(name_key)


def _load_next_category_number(state_file: Path) -> int | None:
    raw_state = _read_json_file(state_file, "category display-ID state")
    if raw_state is None:
        return None
    if not isinstance(raw_state, dict) or set(raw_state) != {"next_display_id"}:
        raise StorageError(
            "Category display-ID state must contain exactly next_display_id."
        )
    value = raw_state["next_display_id"]
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise StorageError(
            "Category display-ID state next_display_id must be a positive integer."
        )
    return value


def _load_validated_data(
    categories_file: Path,
    state_file: Path,
) -> tuple[list[Category], int]:
    raw_categories = _read_json_file(categories_file, "category data")
    categories = (
        [] if raw_categories is None else _deserialize_categories(raw_categories)
    )
    derived_next = calculate_next_category_display_id(
        [category.display_id for category in categories]
    )
    stored_next = _load_next_category_number(state_file)
    if stored_next is not None and stored_next < derived_next:
        raise StorageError(
            "Category display-ID state next_display_id is behind stored "
            "category IDs."
        )
    return categories, max(derived_next, stored_next or 1)


def load_categories(
    categories_file: Path = CATEGORIES_FILE,
    state_file: Path = CATEGORY_STATE_FILE,
) -> list[Category]:
    """Load and validate the current category list and counter state."""
    categories, _ = _load_validated_data(categories_file, state_file)
    return categories


def get_next_category_display_id(
    categories_file: Path = CATEGORIES_FILE,
    state_file: Path = CATEGORY_STATE_FILE,
) -> str:
    """Return the next safe category display ID without consuming it."""
    with category_file_lock(categories_file):
        _, next_number = _load_validated_data(categories_file, state_file)
        return generate_category_display_id(next_number)


def save_categories(
    categories: list[Category],
    categories_file: Path = CATEGORIES_FILE,
    state_file: Path = CATEGORY_STATE_FILE,
) -> None:
    """Validate and atomically persist categories and monotonic ID state."""
    with category_file_lock(categories_file):
        validated_categories = _deserialize_categories(
            [asdict(category) for category in categories]
        )
        _, previous_next = _load_validated_data(categories_file, state_file)
        next_number = max(
            previous_next,
            calculate_next_category_display_id(
                [category.display_id for category in validated_categories]
            ),
        )

        if _load_next_category_number(state_file) != next_number:
            write_json_atomic(
                state_file,
                {"next_display_id": next_number},
                data_name="category display-ID state",
            )
        write_json_atomic(
            categories_file,
            [asdict(category) for category in validated_categories],
            data_name="category data",
        )
