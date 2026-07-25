import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

import category_storage
from category import Category
from category_storage import (
    get_next_category_display_id,
    load_categories,
    save_categories,
)
from json_storage import StorageError


@pytest.fixture
def category_paths(tmp_path: Path) -> tuple[Path, Path]:
    return (
        tmp_path / "nested" / "categories.json",
        tmp_path / "nested" / "categories_state.json",
    )


def make_category(
    display_id: str = "C-0001",
    *,
    name: str = "Food",
    transaction_type: str = "expense",
    is_active: bool = True,
) -> Category:
    return Category(
        id=str(uuid5(NAMESPACE_URL, display_id)),
        display_id=display_id,
        name=name,
        transaction_type=transaction_type,
        is_active=is_active,
    )


def write_raw_categories(
    category_paths: tuple[Path, Path],
    data,
    state=None,
) -> None:
    category_paths[0].parent.mkdir(parents=True, exist_ok=True)
    category_paths[0].write_text(json.dumps(data), encoding="utf-8")
    if state is not None:
        category_paths[1].write_text(json.dumps(state), encoding="utf-8")


def test_save_and_load_categories_with_separate_state(
    category_paths: tuple[Path, Path],
) -> None:
    categories = [
        make_category(),
        make_category(
            "C-0002",
            name="Salary",
            transaction_type="income",
            is_active=False,
        ),
    ]

    save_categories(categories, *category_paths)

    assert load_categories(*category_paths) == categories
    assert json.loads(category_paths[0].read_text(encoding="utf-8")) == [
        category.__dict__ for category in categories
    ]
    assert json.loads(category_paths[1].read_text(encoding="utf-8")) == {
        "next_display_id": 3
    }


def test_missing_and_empty_category_file_load_as_empty(
    category_paths: tuple[Path, Path],
) -> None:
    assert load_categories(*category_paths) == []

    category_paths[0].parent.mkdir(parents=True)
    category_paths[0].write_text(" \n", encoding="utf-8")
    assert load_categories(*category_paths) == []


def test_missing_state_recovers_from_highest_stored_id(
    category_paths: tuple[Path, Path],
) -> None:
    write_raw_categories(
        category_paths,
        [make_category("C-0003").__dict__],
    )

    assert get_next_category_display_id(*category_paths) == "C-0004"

    save_categories(load_categories(*category_paths), *category_paths)
    assert json.loads(category_paths[1].read_text(encoding="utf-8")) == {
        "next_display_id": 4
    }


def test_persisted_state_prevents_id_reuse_when_records_disappear(
    category_paths: tuple[Path, Path],
) -> None:
    save_categories([make_category("C-0003")], *category_paths)
    save_categories([], *category_paths)

    assert get_next_category_display_id(*category_paths) == "C-0004"


@pytest.mark.parametrize(
    "state",
    [
        [],
        {},
        {"next_display_id": True},
        {"next_display_id": 0},
        {"next_display_id": 1, "extra": 2},
    ],
)
def test_malformed_state_fails_safely(
    state,
    category_paths: tuple[Path, Path],
) -> None:
    write_raw_categories(category_paths, [], state)

    with pytest.raises(StorageError, match="Category display-ID state"):
        load_categories(*category_paths)


def test_state_behind_stored_ids_is_rejected(
    category_paths: tuple[Path, Path],
) -> None:
    write_raw_categories(
        category_paths,
        [make_category("C-0003").__dict__],
        {"next_display_id": 3},
    )

    with pytest.raises(StorageError, match="behind stored category IDs"):
        load_categories(*category_paths)


def test_malformed_json_and_invalid_utf8_raise_storage_error(
    category_paths: tuple[Path, Path],
) -> None:
    category_paths[0].parent.mkdir(parents=True)
    category_paths[0].write_text('[{"id":', encoding="utf-8")
    with pytest.raises(StorageError, match="malformed JSON"):
        load_categories(*category_paths)

    category_paths[0].write_bytes(b"\xff")
    with pytest.raises(StorageError, match="Could not read category data"):
        load_categories(*category_paths)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "not-a-uuid", "valid UUID"),
        ("display_id", "c-0001", "canonical format"),
        ("display_id", "C-1", "canonical format"),
        ("name", None, "non-empty text"),
        ("name", " Food ", "outer whitespace"),
        ("name", "Cafe\u0301", "canonical Unicode form"),
        ("transaction_type", "Expense", "income or expense"),
        ("transaction_type", "transfer", "income or expense"),
        ("transaction_type", [], "income or expense"),
        ("is_active", 1, "boolean"),
    ],
)
def test_invalid_category_fields_are_rejected(
    field: str,
    value,
    message: str,
    category_paths: tuple[Path, Path],
) -> None:
    raw_category = make_category().__dict__.copy()
    raw_category[field] = value
    write_raw_categories(category_paths, [raw_category])

    with pytest.raises(StorageError, match=message):
        load_categories(*category_paths)


def test_unexpected_fields_and_non_object_records_are_rejected(
    category_paths: tuple[Path, Path],
) -> None:
    raw_category = make_category().__dict__.copy()
    raw_category["extra"] = "bad"
    write_raw_categories(category_paths, [raw_category])
    with pytest.raises(StorageError, match="contain exactly"):
        load_categories(*category_paths)

    write_raw_categories(category_paths, ["bad"])
    with pytest.raises(StorageError, match="JSON object"):
        load_categories(*category_paths)


@pytest.mark.parametrize("duplicate_field", ["id", "display_id"])
def test_duplicate_category_identifiers_are_rejected(
    duplicate_field: str,
    category_paths: tuple[Path, Path],
) -> None:
    first = make_category()
    second = make_category("C-0002", name="Travel")
    setattr(second, duplicate_field, getattr(first, duplicate_field))
    write_raw_categories(category_paths, [first.__dict__, second.__dict__])

    with pytest.raises(StorageError, match=f"Duplicate category {duplicate_field}"):
        load_categories(*category_paths)


def test_duplicate_active_name_is_rejected_only_within_same_type(
    category_paths: tuple[Path, Path],
) -> None:
    first = make_category()
    duplicate = make_category("C-0002", name=" FOOD ")
    duplicate.name = "food"
    write_raw_categories(category_paths, [first.__dict__, duplicate.__dict__])
    with pytest.raises(StorageError, match="Duplicate active category name"):
        load_categories(*category_paths)

    duplicate.transaction_type = "income"
    write_raw_categories(category_paths, [first.__dict__, duplicate.__dict__])
    assert len(load_categories(*category_paths)) == 2


def test_inactive_duplicate_names_are_allowed(
    category_paths: tuple[Path, Path],
) -> None:
    categories = [
        make_category(),
        make_category("C-0002", name="food", is_active=False),
    ]

    save_categories(categories, *category_paths)

    assert load_categories(*category_paths) == categories


def test_lock_and_write_errors_are_controlled(
    category_paths: tuple[Path, Path],
    monkeypatch,
) -> None:
    original_mkdir = Path.mkdir

    def fail_category_directory(path, *args, **kwargs) -> None:
        if path == category_paths[0].parent:
            raise OSError("permission denied")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_category_directory)
    with pytest.raises(StorageError, match="Could not lock category data"):
        save_categories([make_category()], *category_paths)


def test_failed_atomic_replace_preserves_previous_category_file(
    category_paths: tuple[Path, Path],
    monkeypatch,
) -> None:
    save_categories([make_category()], *category_paths)
    previous_content = category_paths[0].read_text(encoding="utf-8")
    original_replace = os.replace

    def fail_category_replace(source, destination) -> None:
        if destination == category_paths[0]:
            raise OSError("simulated replace failure")
        original_replace(source, destination)

    monkeypatch.setattr(category_storage.os, "replace", fail_category_replace)
    with pytest.raises(StorageError, match="simulated replace failure"):
        save_categories(
            [make_category(), make_category("C-0002", name="Travel")],
            *category_paths,
        )

    assert category_paths[0].read_text(encoding="utf-8") == previous_content
    assert list(category_paths[0].parent.glob("*.tmp")) == []
