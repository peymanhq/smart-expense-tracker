from pathlib import Path
from threading import Barrier, Thread
from uuid import UUID

import pytest

from category_service import (
    activate_category,
    add_category,
    deactivate_category,
    get_category_by_display_id,
    get_category_by_id,
    list_categories,
    rename_category,
)
from category_repository import JsonCategoryRepository


@pytest.fixture
def repository(tmp_path: Path) -> JsonCategoryRepository:
    return JsonCategoryRepository(
        tmp_path / "nested" / "categories.json",
        tmp_path / "nested" / "categories_state.json",
    )


def test_add_category_normalizes_and_persists_valid_category(
    repository: JsonCategoryRepository,
) -> None:
    result = add_category("  Café  ", " ExPENSE ", repository)

    assert result.success is True
    assert result.category is not None
    assert result.category.name == "Café"
    assert result.category.transaction_type == "expense"
    assert result.category.display_id == "C-0001"
    assert result.category.is_active is True
    assert str(UUID(result.category.id)) == result.category.id
    assert repository.list_all() == [result.category]


def test_category_queries_list_filter_and_order_deterministically(
    repository: JsonCategoryRepository,
) -> None:
    income = add_category("Salary", "income", repository).category
    inactive_expense = add_category(
        "Food",
        "expense",
        repository,
    ).category
    active_expense = add_category(
        "Travel",
        "expense",
        repository,
    ).category
    assert income is not None
    assert inactive_expense is not None
    assert active_expense is not None
    deactivate_category(inactive_expense.display_id, repository)

    all_categories = list_categories(repository)
    active_categories = list_categories(
        repository,
        active_only=True,
    )

    assert [category.display_id for category in all_categories] == [
        "C-0002",
        "C-0003",
        "C-0001",
    ]
    assert [category.display_id for category in active_categories] == [
        "C-0003",
        "C-0001",
    ]
    assert list_categories(
        repository,
        active_only=True,
        transaction_type=" EXPENSE ",
    ) == [active_expense]
    assert list_categories(
        repository,
        active_only=True,
        transaction_type="Income",
    ) == [income]

    all_categories.clear()
    assert len(list_categories(repository)) == 3


def test_category_queries_resolve_active_and_inactive_records(
    repository: JsonCategoryRepository,
) -> None:
    active = add_category("Salary", "income", repository).category
    inactive = add_category("Food", "expense", repository).category
    assert active is not None
    assert inactive is not None
    deactivate_category(inactive.display_id, repository)

    resolved_inactive = get_category_by_id(inactive.id, repository)

    assert get_category_by_id(active.id, repository) == active
    assert resolved_inactive is not None
    assert resolved_inactive.id == inactive.id
    assert resolved_inactive.is_active is False
    assert get_category_by_display_id(" c-1 ", repository) == active
    assert get_category_by_id(str(UUID(int=0)), repository) is None
    assert get_category_by_id("not-a-uuid", repository) is None
    assert get_category_by_id(f"{{{active.id}}}", repository) is None
    assert get_category_by_display_id("C-9999", repository) is None
    assert get_category_by_display_id("category-1", repository) is None


@pytest.mark.parametrize("transaction_type", ["transfer", "", 42])
def test_category_query_rejects_invalid_transaction_type(
    transaction_type,
    repository: JsonCategoryRepository,
) -> None:
    with pytest.raises(ValueError, match="Invalid transaction type"):
        list_categories(
            repository,
            transaction_type=transaction_type,
        )


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
    repository: JsonCategoryRepository,
) -> None:
    result = add_category(name, transaction_type, repository)

    assert result.success is False
    assert result.message == message
    assert repository.list_all() == []


def test_duplicate_active_name_is_scoped_to_transaction_type(
    repository: JsonCategoryRepository,
) -> None:
    assert add_category("Food", "expense", repository).success

    duplicate = add_category(" FOOD ", "EXPENSE", repository)
    other_type = add_category("food", "income", repository)

    assert duplicate.success is False
    assert "already exists" in duplicate.message
    assert other_type.success is True
    assert len(repository.list_all()) == 2


def test_unicode_equivalent_active_name_is_duplicate(
    repository: JsonCategoryRepository,
) -> None:
    assert add_category("Café", "expense", repository).success

    result = add_category("Cafe\u0301", "expense", repository)

    assert result.success is False
    assert "already exists" in result.message


def test_inactive_name_can_be_reused_and_blocks_reactivation(
    repository: JsonCategoryRepository,
) -> None:
    add_category("Food", "expense", repository)
    deactivate_category("C-0001", repository)
    replacement = add_category(" food ", "expense", repository)

    activation = activate_category("C-0001", repository)

    assert replacement.success is True
    assert replacement.category is not None
    assert replacement.category.display_id == "C-0002"
    assert activation.success is False
    assert "already exists" in activation.message
    assert repository.list_all()[0].is_active is False


def test_display_ids_are_sequential_and_not_reused_after_deactivation(
    repository: JsonCategoryRepository,
) -> None:
    first = add_category("Food", "expense", repository)
    deactivate_category("C-0001", repository)
    second = add_category("Travel", "expense", repository)

    assert first.category is not None
    assert second.category is not None
    assert [first.category.display_id, second.category.display_id] == [
        "C-0001",
        "C-0002",
    ]


def test_rename_preserves_all_fields_except_trimmed_name(
    repository: JsonCategoryRepository,
) -> None:
    created = add_category("Food", "expense", repository).category
    assert created is not None
    deactivate_category("C-0001", repository)

    result = rename_category(" c-1 ", "  Dining  ", repository)

    assert result.success is True
    assert result.category is not None
    assert result.category.id == created.id
    assert result.category.display_id == created.display_id
    assert result.category.transaction_type == "expense"
    assert result.category.is_active is False
    assert result.category.name == "Dining"


def test_active_rename_duplicate_rules_are_scoped_to_type(
    repository: JsonCategoryRepository,
) -> None:
    add_category("Food", "expense", repository)
    add_category("Travel", "expense", repository)
    add_category("Food", "income", repository)

    duplicate = rename_category("C-0002", " food ", repository)
    other_type = rename_category("C-0003", "Travel", repository)

    assert duplicate.success is False
    assert "already exists" in duplicate.message
    assert other_type.success is True


def test_inactive_category_can_be_renamed_to_active_duplicate(
    repository: JsonCategoryRepository,
) -> None:
    add_category("Food", "expense", repository)
    add_category("Travel", "expense", repository)
    deactivate_category("C-0002", repository)

    result = rename_category("C-0002", " food ", repository)

    assert result.success is True
    assert result.category is not None
    assert result.category.name == "food"
    assert result.category.is_active is False


def test_deactivate_and_activate_preserve_record_identity(
    repository: JsonCategoryRepository,
) -> None:
    created = add_category("Salary", "income", repository).category
    assert created is not None

    deactivated = deactivate_category("C-0001", repository)
    activated = activate_category("C-0001", repository)

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
    assert repository.list_all() == [activated.category]


def test_already_active_and_inactive_return_explicit_results(
    repository: JsonCategoryRepository,
) -> None:
    add_category("Food", "expense", repository)

    active = activate_category("C-0001", repository)
    deactivate_category("C-0001", repository)
    inactive = deactivate_category("C-0001", repository)

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
    repository: JsonCategoryRepository,
) -> None:
    if operation is rename_category:
        result = operation("C-9999", "Dining", repository)
    else:
        result = operation("C-9999", repository)

    assert result.success is False
    assert result.message == "Category not found."


def test_rename_rejects_empty_name(
    repository: JsonCategoryRepository,
) -> None:
    add_category("Food", "expense", repository)

    result = rename_category("C-0001", " ", repository)

    assert result.success is False
    assert result.message == "Category name cannot be empty."
    assert repository.list_all()[0].name == "Food"


def test_rename_rejects_non_text_name(
    repository: JsonCategoryRepository,
) -> None:
    add_category("Food", "expense", repository)

    result = rename_category("C-0001", None, repository)

    assert result.success is False
    assert result.message == "Category name must be text."
    assert repository.list_all()[0].name == "Food"


def test_list_categories_orders_by_type_then_display_id(
    repository: JsonCategoryRepository,
) -> None:
    add_category("Salary", "income", repository)
    add_category("Food", "expense", repository)
    add_category("Travel", "expense", repository)

    assert [category.display_id for category in list_categories(repository)] == [
        "C-0002",
        "C-0003",
        "C-0001",
    ]


def test_concurrent_category_additions_are_not_lost(
    repository: JsonCategoryRepository,
) -> None:
    worker_count = 12
    start = Barrier(worker_count)
    results = []

    def add_from_worker(number: int) -> None:
        start.wait()
        results.append(
            add_category(f"Category {number}", "expense", repository)
        )

    threads = [
        Thread(target=add_from_worker, args=(number,))
        for number in range(worker_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    categories = repository.list_all()
    assert len(results) == worker_count
    assert all(result.success for result in results)
    assert len(categories) == worker_count
    assert len({category.id for category in categories}) == worker_count
    assert {category.display_id for category in categories} == {
        f"C-{number:04d}" for number in range(1, worker_count + 1)
    }
