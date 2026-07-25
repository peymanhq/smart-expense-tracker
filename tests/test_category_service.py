from pathlib import Path
from threading import Barrier, Thread
from uuid import UUID

import pytest

from category_service import (
    activate_category,
    add_category,
    deactivate_category,
    list_categories,
    rename_category,
)
from category_storage import load_categories


@pytest.fixture
def category_paths(tmp_path: Path) -> tuple[Path, Path]:
    return (
        tmp_path / "nested" / "categories.json",
        tmp_path / "nested" / "categories_state.json",
    )


def test_add_category_normalizes_and_persists_valid_category(
    category_paths: tuple[Path, Path],
) -> None:
    result = add_category("  Café  ", " ExPENSE ", *category_paths)

    assert result.success is True
    assert result.category is not None
    assert result.category.name == "Café"
    assert result.category.transaction_type == "expense"
    assert result.category.display_id == "C-0001"
    assert result.category.is_active is True
    assert str(UUID(result.category.id)) == result.category.id
    assert load_categories(*category_paths) == [result.category]


@pytest.mark.parametrize(
    ("name", "transaction_type", "message"),
    [
        (" \t ", "expense", "Category name cannot be empty."),
        (None, "expense", "Category name must be text."),
        ("Food", "transfer", "Invalid transaction type."),
        ("Food", None, "Invalid transaction type."),
    ],
)
def test_add_category_rejects_invalid_input(
    name,
    transaction_type,
    message: str,
    category_paths: tuple[Path, Path],
) -> None:
    result = add_category(name, transaction_type, *category_paths)

    assert result.success is False
    assert result.message == message
    assert load_categories(*category_paths) == []


def test_duplicate_active_name_is_scoped_to_transaction_type(
    category_paths: tuple[Path, Path],
) -> None:
    assert add_category("Food", "expense", *category_paths).success

    duplicate = add_category(" FOOD ", "EXPENSE", *category_paths)
    other_type = add_category("food", "income", *category_paths)

    assert duplicate.success is False
    assert "already exists" in duplicate.message
    assert other_type.success is True
    assert len(load_categories(*category_paths)) == 2


def test_unicode_equivalent_active_name_is_duplicate(
    category_paths: tuple[Path, Path],
) -> None:
    assert add_category("Café", "expense", *category_paths).success

    result = add_category("Cafe\u0301", "expense", *category_paths)

    assert result.success is False
    assert "already exists" in result.message


def test_inactive_name_can_be_reused_and_blocks_reactivation(
    category_paths: tuple[Path, Path],
) -> None:
    add_category("Food", "expense", *category_paths)
    deactivate_category("C-0001", *category_paths)
    replacement = add_category(" food ", "expense", *category_paths)

    activation = activate_category("C-0001", *category_paths)

    assert replacement.success is True
    assert replacement.category is not None
    assert replacement.category.display_id == "C-0002"
    assert activation.success is False
    assert "already exists" in activation.message
    assert load_categories(*category_paths)[0].is_active is False


def test_display_ids_are_sequential_and_not_reused_after_deactivation(
    category_paths: tuple[Path, Path],
) -> None:
    first = add_category("Food", "expense", *category_paths)
    deactivate_category("C-0001", *category_paths)
    second = add_category("Travel", "expense", *category_paths)

    assert first.category is not None
    assert second.category is not None
    assert [first.category.display_id, second.category.display_id] == [
        "C-0001",
        "C-0002",
    ]


def test_rename_preserves_all_fields_except_trimmed_name(
    category_paths: tuple[Path, Path],
) -> None:
    created = add_category("Food", "expense", *category_paths).category
    assert created is not None
    deactivate_category("C-0001", *category_paths)

    result = rename_category(" c-1 ", "  Dining  ", *category_paths)

    assert result.success is True
    assert result.category is not None
    assert result.category.id == created.id
    assert result.category.display_id == created.display_id
    assert result.category.transaction_type == "expense"
    assert result.category.is_active is False
    assert result.category.name == "Dining"


def test_active_rename_duplicate_rules_are_scoped_to_type(
    category_paths: tuple[Path, Path],
) -> None:
    add_category("Food", "expense", *category_paths)
    add_category("Travel", "expense", *category_paths)
    add_category("Food", "income", *category_paths)

    duplicate = rename_category("C-0002", " food ", *category_paths)
    other_type = rename_category("C-0003", "Travel", *category_paths)

    assert duplicate.success is False
    assert "already exists" in duplicate.message
    assert other_type.success is True


def test_inactive_category_can_be_renamed_to_active_duplicate(
    category_paths: tuple[Path, Path],
) -> None:
    add_category("Food", "expense", *category_paths)
    add_category("Travel", "expense", *category_paths)
    deactivate_category("C-0002", *category_paths)

    result = rename_category("C-0002", " food ", *category_paths)

    assert result.success is True
    assert result.category is not None
    assert result.category.name == "food"
    assert result.category.is_active is False


def test_deactivate_and_activate_preserve_record_identity(
    category_paths: tuple[Path, Path],
) -> None:
    created = add_category("Salary", "income", *category_paths).category
    assert created is not None

    deactivated = deactivate_category("C-0001", *category_paths)
    activated = activate_category("C-0001", *category_paths)

    assert deactivated.success is True
    assert deactivated.category is not None
    assert deactivated.category.id == created.id
    assert deactivated.category.display_id == created.display_id
    assert deactivated.category.name == created.name
    assert deactivated.category.transaction_type == created.transaction_type
    assert deactivated.category.is_active is False
    assert activated.success is True
    assert activated.category is not None
    assert activated.category.id == created.id
    assert activated.category.is_active is True
    assert load_categories(*category_paths) == [activated.category]


def test_already_active_and_inactive_return_explicit_results(
    category_paths: tuple[Path, Path],
) -> None:
    add_category("Food", "expense", *category_paths)

    active = activate_category("C-0001", *category_paths)
    deactivate_category("C-0001", *category_paths)
    inactive = deactivate_category("C-0001", *category_paths)

    assert active.success is False
    assert active.message == "Category is already active."
    assert inactive.success is False
    assert inactive.message == "Category is already inactive."


@pytest.mark.parametrize(
    "operation",
    [rename_category, activate_category, deactivate_category],
)
def test_missing_category_returns_explicit_result(
    operation,
    category_paths: tuple[Path, Path],
) -> None:
    if operation is rename_category:
        result = operation("C-9999", "Dining", *category_paths)
    else:
        result = operation("C-9999", *category_paths)

    assert result.success is False
    assert result.message == "Category not found."


def test_rename_rejects_empty_name(
    category_paths: tuple[Path, Path],
) -> None:
    add_category("Food", "expense", *category_paths)

    result = rename_category("C-0001", " ", *category_paths)

    assert result.success is False
    assert result.message == "Category name cannot be empty."
    assert load_categories(*category_paths)[0].name == "Food"


def test_rename_rejects_non_text_name(
    category_paths: tuple[Path, Path],
) -> None:
    add_category("Food", "expense", *category_paths)

    result = rename_category("C-0001", None, *category_paths)

    assert result.success is False
    assert result.message == "Category name must be text."
    assert load_categories(*category_paths)[0].name == "Food"


def test_list_categories_orders_by_type_then_display_id(
    category_paths: tuple[Path, Path],
) -> None:
    add_category("Salary", "income", *category_paths)
    add_category("Food", "expense", *category_paths)
    add_category("Travel", "expense", *category_paths)

    assert [category.display_id for category in list_categories(*category_paths)] == [
        "C-0002",
        "C-0003",
        "C-0001",
    ]


def test_concurrent_category_additions_are_not_lost(
    category_paths: tuple[Path, Path],
) -> None:
    worker_count = 12
    start = Barrier(worker_count)
    results = []

    def add_from_worker(number: int) -> None:
        start.wait()
        results.append(
            add_category(f"Category {number}", "expense", *category_paths)
        )

    threads = [
        Thread(target=add_from_worker, args=(number,))
        for number in range(worker_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    categories = load_categories(*category_paths)
    assert len(results) == worker_count
    assert all(result.success for result in results)
    assert len(categories) == worker_count
    assert len({category.id for category in categories}) == worker_count
    assert {category.display_id for category in categories} == {
        f"C-{number:04d}" for number in range(1, worker_count + 1)
    }
