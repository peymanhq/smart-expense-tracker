"""Backend-neutral Account and Category repository contract tests."""

from dataclasses import replace
from pathlib import Path
from typing import Callable
from uuid import NAMESPACE_URL, uuid5

import pytest

from account import Account
from account_repository import (
    AccountRepository,
    AccountRepositoryConflictError,
    AccountRepositoryNotFoundError,
    AccountRepositoryRecordChangedError,
    JsonAccountRepository,
)
from account_service import AccountService
from category import Category
from category_repository import (
    CategoryRepository,
    CategoryRepositoryConflictError,
    CategoryRepositoryNotFoundError,
    CategoryRepositoryRecordChangedError,
    JsonCategoryRepository,
)
from category_service import CategoryService
from persistence_errors import StorageError
from sqlite_account_repository import SQLiteAccountRepository
from sqlite_category_repository import SQLiteCategoryRepository
from sqlite_database import SQLiteDatabase
from sqlite_schema import initialize_schema


def record_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, name))


@pytest.fixture(params=["json", "sqlite"])
def account_backend(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> tuple[AccountRepository, Callable[[], AccountRepository]]:
    if request.param == "json":
        accounts_file = tmp_path / "json" / "accounts.json"
        state_file = tmp_path / "json" / "accounts_state.json"

        def build() -> AccountRepository:
            return JsonAccountRepository(accounts_file, state_file)

    else:
        database = SQLiteDatabase(tmp_path / "sqlite" / "database.sqlite3")
        initialize_schema(database)

        def build() -> AccountRepository:
            return SQLiteAccountRepository(database)

    return build(), build


@pytest.fixture(params=["json", "sqlite"])
def category_backend(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> tuple[CategoryRepository, Callable[[], CategoryRepository]]:
    if request.param == "json":
        categories_file = tmp_path / "json" / "categories.json"
        state_file = tmp_path / "json" / "categories_state.json"

        def build() -> CategoryRepository:
            return JsonCategoryRepository(categories_file, state_file)

    else:
        database = SQLiteDatabase(tmp_path / "sqlite" / "database.sqlite3")
        initialize_schema(database)

        def build() -> CategoryRepository:
            return SQLiteCategoryRepository(database)

    return build(), build


def test_account_empty_reads_creation_lookup_order_and_persistence(
    account_backend: tuple[AccountRepository, Callable[[], AccountRepository]],
) -> None:
    repository, restart = account_backend
    assert repository.list_all() == []

    first = repository.create(record_id("account-1"), "Cash")
    second = repository.create(record_id("account-2"), "Bank")

    assert [first.display_id, second.display_id] == ["A-0001", "A-0002"]
    assert [account.id for account in repository.list_all()] == [
        first.id,
        second.id,
    ]
    detached = repository.list_all()
    detached.clear()
    assert len(repository.list_all()) == 2

    restarted = restart()
    assert restarted.get_by_id(first.id) == first
    assert restarted.get_by_display_id(" a-1 ") == first
    assert restarted.get_by_display_id("A-9999") is None
    assert restarted.get_by_display_id("account-1") is None
    assert restarted.get_by_id(record_id("missing-account")) is None


def test_account_replace_preserves_identity_and_detects_stale_or_missing(
    account_backend: tuple[AccountRepository, Callable[[], AccountRepository]],
) -> None:
    repository, restart = account_backend
    created = repository.create(record_id("account-replace"), "Cash")
    stale = created

    replaced = repository.replace(
        created,
        Account(
            id=record_id("ignored-account-id"),
            display_id="A-9999",
            name="Wallet",
            is_active=False,
        ),
    )

    assert replaced == Account(
        id=created.id,
        display_id=created.display_id,
        name="Wallet",
        is_active=False,
    )
    assert restart().get_by_id(created.id) == replaced
    with pytest.raises(AccountRepositoryRecordChangedError):
        repository.replace(stale, replace(stale, name="Stale"))
    missing = Account(
        record_id("missing-replacement-account"),
        "A-9998",
        "Missing",
    )
    with pytest.raises(AccountRepositoryNotFoundError):
        repository.replace(missing, replace(missing, name="Still missing"))


def test_account_active_unicode_uniqueness_inactive_reuse_and_counter_safety(
    account_backend: tuple[AccountRepository, Callable[[], AccountRepository]],
) -> None:
    repository, _ = account_backend
    original = repository.create(record_id("account-cafe-1"), "Café")

    with pytest.raises(AccountRepositoryConflictError):
        repository.create(record_id("account-cafe-2"), "Cafe\u0301")

    deactivated = repository.replace(
        original,
        replace(original, is_active=False),
    )
    replacement = repository.create(record_id("account-cafe-3"), "CAFÉ")

    assert replacement.display_id == "A-0002"
    with pytest.raises(AccountRepositoryConflictError):
        repository.replace(
            deactivated,
            replace(deactivated, is_active=True),
        )
    assert repository.get_by_id(deactivated.id) == deactivated


def test_account_failed_duplicate_uuid_does_not_advance_counter(
    account_backend: tuple[AccountRepository, Callable[[], AccountRepository]],
) -> None:
    repository, _ = account_backend
    first = repository.create(record_id("duplicate-account-id"), "Cash")

    with pytest.raises(StorageError):
        repository.create(first.id, "Bank")

    second = repository.create(record_id("next-account-id"), "Savings")
    assert second.display_id == "A-0002"


def test_account_service_filters_and_orders_both_backends(
    account_backend: tuple[AccountRepository, Callable[[], AccountRepository]],
) -> None:
    repository, _ = account_backend
    service = AccountService(repository)
    first = service.add_account("Cash").account
    second = service.add_account("Bank").account
    assert first is not None
    assert second is not None
    service.deactivate_account(first.display_id)

    assert [item.display_id for item in service.list_accounts()] == [
        "A-0001",
        "A-0002",
    ]
    assert service.list_accounts(active_only=True) == [second]


def test_category_empty_reads_creation_lookup_order_and_persistence(
    category_backend: tuple[
        CategoryRepository,
        Callable[[], CategoryRepository],
    ],
) -> None:
    repository, restart = category_backend
    assert repository.list_all() == []

    first = repository.create(
        record_id("category-1"),
        "Food",
        "expense",
    )
    second = repository.create(
        record_id("category-2"),
        "Salary",
        "income",
    )

    assert [first.display_id, second.display_id] == ["C-0001", "C-0002"]
    assert [category.id for category in repository.list_all()] == [
        first.id,
        second.id,
    ]
    detached = repository.list_all()
    detached.clear()
    assert len(repository.list_all()) == 2

    restarted = restart()
    assert restarted.get_by_id(first.id) == first
    assert restarted.get_by_display_id(" c-1 ") == first
    assert restarted.get_by_display_id("C-9999") is None
    assert restarted.get_by_display_id("category-1") is None
    assert restarted.get_by_id(record_id("missing-category")) is None


def test_category_replace_preserves_identity_type_and_detects_stale_or_missing(
    category_backend: tuple[
        CategoryRepository,
        Callable[[], CategoryRepository],
    ],
) -> None:
    repository, restart = category_backend
    created = repository.create(
        record_id("category-replace"),
        "Food",
        "expense",
    )
    stale = created

    replaced = repository.replace(
        created,
        Category(
            id=record_id("ignored-category-id"),
            display_id="C-9999",
            name="Dining",
            transaction_type="income",
            is_active=False,
        ),
    )

    assert replaced == Category(
        id=created.id,
        display_id=created.display_id,
        name="Dining",
        transaction_type="expense",
        is_active=False,
    )
    assert restart().get_by_id(created.id) == replaced
    with pytest.raises(CategoryRepositoryRecordChangedError):
        repository.replace(stale, replace(stale, name="Stale"))
    missing = Category(
        record_id("missing-replacement-category"),
        "C-9998",
        "Missing",
        "expense",
    )
    with pytest.raises(CategoryRepositoryNotFoundError):
        repository.replace(missing, replace(missing, name="Still missing"))


def test_category_scoped_unicode_uniqueness_inactive_reuse_and_counter_safety(
    category_backend: tuple[
        CategoryRepository,
        Callable[[], CategoryRepository],
    ],
) -> None:
    repository, _ = category_backend
    original = repository.create(
        record_id("category-cafe-1"),
        "Café",
        "expense",
    )

    with pytest.raises(CategoryRepositoryConflictError):
        repository.create(
            record_id("category-cafe-2"),
            "Cafe\u0301",
            "expense",
        )
    income = repository.create(
        record_id("category-cafe-income"),
        "CAFÉ",
        "income",
    )
    deactivated = repository.replace(
        original,
        replace(original, is_active=False),
    )
    replacement = repository.create(
        record_id("category-cafe-3"),
        "café",
        "expense",
    )

    assert income.display_id == "C-0002"
    assert replacement.display_id == "C-0003"
    with pytest.raises(CategoryRepositoryConflictError):
        repository.replace(
            deactivated,
            replace(deactivated, is_active=True),
        )
    assert repository.get_by_id(deactivated.id) == deactivated


def test_category_failed_duplicate_uuid_does_not_advance_counter(
    category_backend: tuple[
        CategoryRepository,
        Callable[[], CategoryRepository],
    ],
) -> None:
    repository, _ = category_backend
    first = repository.create(
        record_id("duplicate-category-id"),
        "Food",
        "expense",
    )

    with pytest.raises(StorageError):
        repository.create(first.id, "Travel", "expense")

    second = repository.create(
        record_id("next-category-id"),
        "Salary",
        "income",
    )
    assert second.display_id == "C-0002"


def test_category_service_filters_and_orders_both_backends(
    category_backend: tuple[
        CategoryRepository,
        Callable[[], CategoryRepository],
    ],
) -> None:
    repository, _ = category_backend
    service = CategoryService(repository)
    income = service.add_category("Salary", "income").category
    inactive_expense = service.add_category("Food", "expense").category
    active_expense = service.add_category("Travel", "expense").category
    assert income is not None
    assert inactive_expense is not None
    assert active_expense is not None
    service.deactivate_category(inactive_expense.display_id)

    assert [item.display_id for item in service.list_categories()] == [
        "C-0002",
        "C-0003",
        "C-0001",
    ]
    assert service.list_categories(
        active_only=True,
        transaction_type="expense",
    ) == [active_expense]
