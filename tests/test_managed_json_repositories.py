"""Focused contracts for the JSON Account and Category repositories."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from account import Account
from account_repository import JsonAccountRepository
from category import Category
from category_repository import JsonCategoryRepository


@pytest.fixture
def account_repository(
    tmp_path: Path,
) -> tuple[JsonAccountRepository, Path, Path]:
    accounts_file = tmp_path / "data" / "accounts.json"
    state_file = tmp_path / "data" / "accounts_state.json"
    return (
        JsonAccountRepository(accounts_file, state_file),
        accounts_file,
        state_file,
    )


@pytest.fixture
def category_repository(
    tmp_path: Path,
) -> tuple[JsonCategoryRepository, Path, Path]:
    categories_file = tmp_path / "data" / "categories.json"
    state_file = tmp_path / "data" / "categories_state.json"
    return (
        JsonCategoryRepository(categories_file, state_file),
        categories_file,
        state_file,
    )


def test_account_repository_preserves_current_document_contract(
    account_repository: tuple[JsonAccountRepository, Path, Path],
) -> None:
    repository, accounts_file, state_file = account_repository
    created = repository.create(
        str(uuid5(NAMESPACE_URL, "account-1")),
        "Cash",
    )
    replaced = repository.replace(
        created,
        Account(created.id, "A-9999", "Wallet", False),
    )

    assert replaced.id == created.id
    assert replaced.display_id == "A-0001"
    assert repository.get_by_id(created.id) == replaced
    assert repository.get_by_display_id(" a-1 ") == replaced

    document = json.loads(accounts_file.read_text(encoding="utf-8"))
    assert document == {
        "metadata": {"next_display_id": 2},
        "accounts": [replaced.__dict__],
    }
    assert not state_file.exists()


def test_category_repository_preserves_separate_counter_contract(
    category_repository: tuple[JsonCategoryRepository, Path, Path],
) -> None:
    repository, categories_file, state_file = category_repository
    created = repository.create(
        str(uuid5(NAMESPACE_URL, "category-1")),
        "Food",
        "expense",
    )
    replaced = repository.replace(
        created,
        Category(created.id, "C-9999", "Dining", "income", False),
    )

    assert replaced.id == created.id
    assert replaced.display_id == "C-0001"
    assert replaced.transaction_type == "expense"
    assert repository.get_by_id(created.id) == replaced
    assert repository.get_by_display_id(" c-1 ") == replaced
    assert json.loads(categories_file.read_text(encoding="utf-8")) == [
        replaced.__dict__
    ]
    assert json.loads(state_file.read_text(encoding="utf-8")) == {
        "next_display_id": 2
    }


def test_account_repository_preserves_legacy_counter_during_creation(
    account_repository: tuple[JsonAccountRepository, Path, Path],
) -> None:
    repository, accounts_file, state_file = account_repository
    legacy = Account(
        str(uuid5(NAMESPACE_URL, "legacy-account")),
        "A-0003",
        "Cash",
    )
    accounts_file.parent.mkdir(parents=True)
    accounts_file.write_text(
        json.dumps([legacy.__dict__]),
        encoding="utf-8",
    )
    state_file.write_text(
        json.dumps({"next_display_id": 7}),
        encoding="utf-8",
    )

    created = repository.create(
        str(uuid5(NAMESPACE_URL, "new-account")),
        "Bank",
    )

    assert created.display_id == "A-0007"
    document = json.loads(accounts_file.read_text(encoding="utf-8"))
    assert document["metadata"] == {"next_display_id": 8}
    assert [item["display_id"] for item in document["accounts"]] == [
        "A-0003",
        "A-0007",
    ]


def test_category_repository_preserves_counter_gaps(
    category_repository: tuple[JsonCategoryRepository, Path, Path],
) -> None:
    repository, categories_file, state_file = category_repository
    categories_file.parent.mkdir(parents=True)
    categories_file.write_text("[]", encoding="utf-8")
    state_file.write_text(
        json.dumps({"next_display_id": 7}),
        encoding="utf-8",
    )

    created = repository.create(
        str(uuid5(NAMESPACE_URL, "gap-category")),
        "Travel",
        "expense",
    )

    assert created.display_id == "C-0007"
    assert json.loads(state_file.read_text(encoding="utf-8")) == {
        "next_display_id": 8
    }


@pytest.mark.parametrize("record_type", ["account", "category"])
def test_json_repository_allocates_concurrent_display_ids_atomically(
    record_type: str,
    account_repository: tuple[JsonAccountRepository, Path, Path],
    category_repository: tuple[JsonCategoryRepository, Path, Path],
) -> None:
    worker_count = 12
    accounts = account_repository[0]
    categories = category_repository[0]

    def create(number: int) -> str:
        record_id = str(uuid5(NAMESPACE_URL, f"{record_type}-{number}"))
        if record_type == "account":
            return accounts.create(
                record_id,
                f"Account {number}",
            ).display_id
        return categories.create(
            record_id,
            f"Category {number}",
            "expense",
        ).display_id

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        display_ids = list(executor.map(create, range(worker_count)))

    prefix = "A" if record_type == "account" else "C"
    assert set(display_ids) == {
        f"{prefix}-{number:04d}"
        for number in range(1, worker_count + 1)
    }
