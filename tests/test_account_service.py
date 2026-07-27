from pathlib import Path
from threading import Barrier, Thread
from uuid import UUID

import pytest

from account_service import (
    activate_account,
    add_account,
    deactivate_account,
    get_account_by_display_id,
    get_account_by_id,
    list_accounts,
    rename_account,
)
from account_repository import JsonAccountRepository


@pytest.fixture
def repository(tmp_path: Path) -> JsonAccountRepository:
    return JsonAccountRepository(
        tmp_path / "data" / "accounts.json",
        tmp_path / "data" / "accounts_state.json",
    )


def test_create_valid_account(repository: JsonAccountRepository) -> None:
    result = add_account("Cash", repository)

    assert result.success is True
    assert result.account is not None
    assert result.account.name == "Cash"
    assert result.account.display_id == "A-0001"
    assert result.account.is_active is True
    assert str(UUID(result.account.id)) == result.account.id


def test_account_name_is_trimmed(repository: JsonAccountRepository) -> None:
    result = add_account("  Bank Account  ", repository)

    assert result.account is not None
    assert result.account.name == "Bank Account"


def test_account_queries_list_filter_and_order_deterministically(
    repository: JsonAccountRepository,
) -> None:
    first = add_account("Cash", repository).account
    second = add_account("Bank", repository).account
    third = add_account("Savings", repository).account
    assert first is not None
    assert second is not None
    assert third is not None
    deactivate_account(first.display_id, repository)

    all_accounts = list_accounts(repository)
    active_accounts = list_accounts(repository, active_only=True)

    assert [account.display_id for account in all_accounts] == [
        "A-0001",
        "A-0002",
        "A-0003",
    ]
    assert [account.display_id for account in active_accounts] == [
        "A-0002",
        "A-0003",
    ]

    all_accounts.clear()
    assert len(list_accounts(repository)) == 3


def test_account_queries_resolve_active_and_inactive_records(
    repository: JsonAccountRepository,
) -> None:
    active = add_account("Cash", repository).account
    inactive = add_account("Bank", repository).account
    assert active is not None
    assert inactive is not None
    deactivate_account(inactive.display_id, repository)

    resolved_inactive = get_account_by_id(inactive.id, repository)

    assert get_account_by_id(active.id, repository) == active
    assert resolved_inactive is not None
    assert resolved_inactive.id == inactive.id
    assert resolved_inactive.is_active is False
    assert get_account_by_display_id(" a-1 ", repository) == active
    assert get_account_by_id(str(UUID(int=0)), repository) is None
    assert get_account_by_id("not-a-uuid", repository) is None
    assert get_account_by_id(f"{{{active.id}}}", repository) is None
    assert get_account_by_display_id("A-9999", repository) is None
    assert get_account_by_display_id("account-1", repository) is None


def test_empty_account_name_is_rejected(repository: JsonAccountRepository) -> None:
    result = add_account(" \t ", repository)

    assert result.success is False
    assert result.message == "Account name cannot be empty."
    assert repository.list_all() == []


def test_duplicate_active_name_is_case_insensitive(
    repository: JsonAccountRepository,
) -> None:
    assert add_account("Cash", repository).success is True

    result = add_account(" CASH ", repository)

    assert result.success is False
    assert "already exists" in result.message
    assert len(repository.list_all()) == 1


def test_duplicate_active_name_is_unicode_normalized(
    repository: JsonAccountRepository,
) -> None:
    assert add_account("Café", repository).success is True

    result = add_account("Cafe\u0301", repository)

    assert result.success is False
    assert "already exists" in result.message
    assert len(repository.list_all()) == 1


def test_account_display_ids_are_sequential(
    repository: JsonAccountRepository,
) -> None:
    first = add_account("Cash", repository)
    second = add_account("Bank", repository)
    third = add_account("Savings", repository)

    assert [
        result.account.display_id if result.account else None
        for result in (first, second, third)
    ] == ["A-0001", "A-0002", "A-0003"]


def test_rename_account_preserves_identifiers(
    repository: JsonAccountRepository,
) -> None:
    created = add_account("Cash", repository).account
    assert created is not None

    result = rename_account("A-0001", "  Wallet  ", repository)

    assert result.success is True
    assert result.account is not None
    assert result.account.name == "Wallet"
    assert result.account.id == created.id
    assert result.account.display_id == created.display_id
    assert repository.list_all() == [result.account]


def test_rename_rejects_duplicate_active_name(
    repository: JsonAccountRepository,
) -> None:
    add_account("Cash", repository)
    add_account("Bank", repository)

    result = rename_account("A-0002", " cash ", repository)

    assert result.success is False
    assert "already exists" in result.message
    assert [account.name for account in repository.list_all()] == [
        "Cash",
        "Bank",
    ]


def test_rename_inactive_account_can_match_active_name(
    repository: JsonAccountRepository,
) -> None:
    add_account("Cash", repository)
    add_account("Bank", repository)
    deactivate_account("A-0002", repository)

    result = rename_account("A-0002", " cash ", repository)

    assert result.success is True
    assert result.account is not None
    assert result.account.name == "cash"
    assert result.account.is_active is False


def test_deactivate_account_keeps_record_in_storage(
    repository: JsonAccountRepository,
) -> None:
    created = add_account("Cash", repository).account
    assert created is not None

    result = deactivate_account("A-0001", repository)

    assert result.success is True
    stored = repository.list_all()
    assert len(stored) == 1
    assert stored[0].id == created.id
    assert stored[0].display_id == created.display_id
    assert stored[0].is_active is False


def test_display_id_is_not_reused_after_deactivation(
    repository: JsonAccountRepository,
) -> None:
    add_account("Cash", repository)
    deactivate_account("A-0001", repository)

    result = add_account("Bank", repository)

    assert result.account is not None
    assert result.account.display_id == "A-0002"


def test_activate_account_preserves_identifiers(
    repository: JsonAccountRepository,
) -> None:
    created = add_account("Cash", repository).account
    assert created is not None
    deactivate_account("A-0001", repository)

    result = activate_account("A-0001", repository)

    assert result.success is True
    assert result.account is not None
    assert result.account.id == created.id
    assert result.account.display_id == created.display_id
    assert result.account.is_active is True
    assert repository.list_all() == [result.account]


def test_activate_rejects_duplicate_active_name(
    repository: JsonAccountRepository,
) -> None:
    add_account("Cash", repository)
    deactivate_account("A-0001", repository)
    add_account(" CASH ", repository)

    result = activate_account("A-0001", repository)

    assert result.success is False
    assert result.message == "An active account with this name already exists."
    accounts = repository.list_all()
    assert accounts[0].is_active is False
    assert accounts[1].is_active is True


@pytest.mark.parametrize(
    "operation",
    [rename_account, deactivate_account, activate_account],
)
def test_missing_account_returns_clear_result(
    operation,
    repository: JsonAccountRepository,
) -> None:
    if operation is rename_account:
        result = operation("A-9999", "Wallet", repository)
    else:
        result = operation("A-9999", repository)

    assert result.success is False
    assert result.message == "Account not found."


def test_non_text_display_id_returns_not_found(
    repository: JsonAccountRepository,
) -> None:
    add_account("Cash", repository)

    result = activate_account(None, repository)

    assert result.success is False
    assert result.message == "Account not found."


def test_deactivating_inactive_account_returns_clear_result(
    repository: JsonAccountRepository,
) -> None:
    add_account("Cash", repository)
    deactivate_account("A-0001", repository)

    result = deactivate_account("A-0001", repository)

    assert result.success is False
    assert result.message == "Account is already inactive."


def test_activating_active_account_returns_clear_result(
    repository: JsonAccountRepository,
) -> None:
    add_account("Cash", repository)

    result = activate_account("A-0001", repository)

    assert result.success is False
    assert result.message == "Account is already active."


def test_display_id_lookup_normalizes_case_whitespace_and_padding(
    repository: JsonAccountRepository,
) -> None:
    add_account("Cash", repository)

    deactivated = deactivate_account(" a-0001 ", repository)
    activated = activate_account("A-1", repository)
    renamed = rename_account(" a-1 ", "Wallet", repository)

    assert deactivated.success is True
    assert activated.success is True
    assert renamed.success is True
    assert renamed.account is not None
    assert renamed.account.display_id == "A-0001"


def test_concurrent_account_additions_are_not_lost(
    repository: JsonAccountRepository,
) -> None:
    worker_count = 12
    start = Barrier(worker_count)
    results = []

    def add_from_worker(number: int) -> None:
        start.wait()
        results.append(add_account(f"Account {number}", repository))

    threads = [
        Thread(target=add_from_worker, args=(number,))
        for number in range(worker_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    accounts = repository.list_all()
    assert len(results) == worker_count
    assert all(result.success for result in results)
    assert len(accounts) == worker_count
    assert len({account.id for account in accounts}) == worker_count
    assert {account.display_id for account in accounts} == {
        f"A-{number:04d}" for number in range(1, worker_count + 1)
    }
