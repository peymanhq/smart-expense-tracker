from pathlib import Path
from threading import Barrier, Thread
from uuid import UUID

import pytest

from account_service import (
    activate_account,
    add_account,
    deactivate_account,
    rename_account,
)
from account_storage import load_accounts


@pytest.fixture
def account_paths(tmp_path: Path) -> tuple[Path, Path]:
    return (
        tmp_path / "data" / "accounts.json",
        tmp_path / "data" / "accounts_state.json",
    )


def test_create_valid_account(account_paths: tuple[Path, Path]) -> None:
    result = add_account("Cash", *account_paths)

    assert result.success is True
    assert result.account is not None
    assert result.account.name == "Cash"
    assert result.account.display_id == "A-0001"
    assert result.account.is_active is True
    assert str(UUID(result.account.id)) == result.account.id


def test_account_name_is_trimmed(account_paths: tuple[Path, Path]) -> None:
    result = add_account("  Bank Account  ", *account_paths)

    assert result.account is not None
    assert result.account.name == "Bank Account"


def test_empty_account_name_is_rejected(account_paths: tuple[Path, Path]) -> None:
    result = add_account(" \t ", *account_paths)

    assert result.success is False
    assert result.message == "Account name cannot be empty."
    assert load_accounts(account_paths[0]) == []


def test_duplicate_active_name_is_case_insensitive(
    account_paths: tuple[Path, Path],
) -> None:
    assert add_account("Cash", *account_paths).success is True

    result = add_account(" CASH ", *account_paths)

    assert result.success is False
    assert "already exists" in result.message
    assert len(load_accounts(account_paths[0])) == 1


def test_duplicate_active_name_is_unicode_normalized(
    account_paths: tuple[Path, Path],
) -> None:
    assert add_account("Café", *account_paths).success is True

    result = add_account("Cafe\u0301", *account_paths)

    assert result.success is False
    assert "already exists" in result.message
    assert len(load_accounts(account_paths[0])) == 1


def test_account_display_ids_are_sequential(
    account_paths: tuple[Path, Path],
) -> None:
    first = add_account("Cash", *account_paths)
    second = add_account("Bank", *account_paths)
    third = add_account("Savings", *account_paths)

    assert [
        result.account.display_id if result.account else None
        for result in (first, second, third)
    ] == ["A-0001", "A-0002", "A-0003"]


def test_rename_account_preserves_identifiers(
    account_paths: tuple[Path, Path],
) -> None:
    created = add_account("Cash", *account_paths).account
    assert created is not None

    result = rename_account("A-0001", "  Wallet  ", *account_paths)

    assert result.success is True
    assert result.account is not None
    assert result.account.name == "Wallet"
    assert result.account.id == created.id
    assert result.account.display_id == created.display_id
    assert load_accounts(account_paths[0]) == [result.account]


def test_rename_rejects_duplicate_active_name(
    account_paths: tuple[Path, Path],
) -> None:
    add_account("Cash", *account_paths)
    add_account("Bank", *account_paths)

    result = rename_account("A-0002", " cash ", *account_paths)

    assert result.success is False
    assert "already exists" in result.message
    assert [account.name for account in load_accounts(account_paths[0])] == [
        "Cash",
        "Bank",
    ]


def test_rename_inactive_account_can_match_active_name(
    account_paths: tuple[Path, Path],
) -> None:
    add_account("Cash", *account_paths)
    add_account("Bank", *account_paths)
    deactivate_account("A-0002", *account_paths)

    result = rename_account("A-0002", " cash ", *account_paths)

    assert result.success is True
    assert result.account is not None
    assert result.account.name == "cash"
    assert result.account.is_active is False


def test_deactivate_account_keeps_record_in_storage(
    account_paths: tuple[Path, Path],
) -> None:
    created = add_account("Cash", *account_paths).account
    assert created is not None

    result = deactivate_account("A-0001", *account_paths)

    assert result.success is True
    stored = load_accounts(account_paths[0])
    assert len(stored) == 1
    assert stored[0].id == created.id
    assert stored[0].display_id == created.display_id
    assert stored[0].is_active is False


def test_display_id_is_not_reused_after_deactivation(
    account_paths: tuple[Path, Path],
) -> None:
    add_account("Cash", *account_paths)
    deactivate_account("A-0001", *account_paths)

    result = add_account("Bank", *account_paths)

    assert result.account is not None
    assert result.account.display_id == "A-0002"


def test_activate_account_preserves_identifiers(
    account_paths: tuple[Path, Path],
) -> None:
    created = add_account("Cash", *account_paths).account
    assert created is not None
    deactivate_account("A-0001", *account_paths)

    result = activate_account("A-0001", *account_paths)

    assert result.success is True
    assert result.account is not None
    assert result.account.id == created.id
    assert result.account.display_id == created.display_id
    assert result.account.is_active is True
    assert load_accounts(account_paths[0]) == [result.account]


def test_activate_rejects_duplicate_active_name(
    account_paths: tuple[Path, Path],
) -> None:
    add_account("Cash", *account_paths)
    deactivate_account("A-0001", *account_paths)
    add_account(" CASH ", *account_paths)

    result = activate_account("A-0001", *account_paths)

    assert result.success is False
    assert result.message == "An active account with this name already exists."
    accounts = load_accounts(account_paths[0])
    assert accounts[0].is_active is False
    assert accounts[1].is_active is True


@pytest.mark.parametrize(
    "operation",
    [rename_account, deactivate_account, activate_account],
)
def test_missing_account_returns_clear_result(
    operation,
    account_paths: tuple[Path, Path],
) -> None:
    if operation is rename_account:
        result = operation("A-9999", "Wallet", *account_paths)
    else:
        result = operation("A-9999", *account_paths)

    assert result.success is False
    assert result.message == "Account not found."


def test_non_text_display_id_returns_not_found(
    account_paths: tuple[Path, Path],
) -> None:
    add_account("Cash", *account_paths)

    result = activate_account(None, *account_paths)

    assert result.success is False
    assert result.message == "Account not found."


def test_deactivating_inactive_account_returns_clear_result(
    account_paths: tuple[Path, Path],
) -> None:
    add_account("Cash", *account_paths)
    deactivate_account("A-0001", *account_paths)

    result = deactivate_account("A-0001", *account_paths)

    assert result.success is False
    assert result.message == "Account is already inactive."


def test_activating_active_account_returns_clear_result(
    account_paths: tuple[Path, Path],
) -> None:
    add_account("Cash", *account_paths)

    result = activate_account("A-0001", *account_paths)

    assert result.success is False
    assert result.message == "Account is already active."


def test_display_id_lookup_normalizes_case_whitespace_and_padding(
    account_paths: tuple[Path, Path],
) -> None:
    add_account("Cash", *account_paths)

    deactivated = deactivate_account(" a-0001 ", *account_paths)
    activated = activate_account("A-1", *account_paths)
    renamed = rename_account(" a-1 ", "Wallet", *account_paths)

    assert deactivated.success is True
    assert activated.success is True
    assert renamed.success is True
    assert renamed.account is not None
    assert renamed.account.display_id == "A-0001"


def test_concurrent_account_additions_are_not_lost(
    account_paths: tuple[Path, Path],
) -> None:
    worker_count = 12
    start = Barrier(worker_count)
    results = []

    def add_from_worker(number: int) -> None:
        start.wait()
        results.append(add_account(f"Account {number}", *account_paths))

    threads = [
        Thread(target=add_from_worker, args=(number,))
        for number in range(worker_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    accounts = load_accounts(account_paths[0])
    assert len(results) == worker_count
    assert all(result.success for result in results)
    assert len(accounts) == worker_count
    assert len({account.id for account in accounts}) == worker_count
    assert {account.display_id for account in accounts} == {
        f"A-{number:04d}" for number in range(1, worker_count + 1)
    }
