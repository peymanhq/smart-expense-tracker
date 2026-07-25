from datetime import date, datetime, timezone

import pytest

from account import Account
from category import Category
from json_storage import StorageError
from transaction import Transaction
from transaction_repository import JsonTransactionRepository
from transaction_service import (
    ManagedAccountInactiveError,
    ManagedAccountNotFoundError,
    ManagedCategoryInactiveError,
    ManagedCategoryNotFoundError,
    ManagedCategoryTypeMismatchError,
    ManagedLookupUnavailableError,
    ManagedReferenceClearingError,
    ManagedSnapshotUpdateError,
    TransactionService,
)


TODAY = date(2026, 7, 25)
NOW = datetime(2026, 7, 25, 9, 15, tzinfo=timezone.utc)
LATER = datetime(2026, 7, 25, 10, 30, tzinfo=timezone.utc)

ACCOUNT_ID = "123e4567-e89b-12d3-a456-426614174000"
SECOND_ACCOUNT_ID = "123e4567-e89b-12d3-a456-426614174002"
INACTIVE_ACCOUNT_ID = "123e4567-e89b-12d3-a456-426614174003"
UNKNOWN_ACCOUNT_ID = "123e4567-e89b-12d3-a456-426614174099"

EXPENSE_CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174001"
SECOND_EXPENSE_CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174006"
INCOME_CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174004"
INACTIVE_CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174005"
UNKNOWN_CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174098"

ACTIVE_ACCOUNT = Account(ACCOUNT_ID, "A-0001", "Cash")
SECOND_ACCOUNT = Account(SECOND_ACCOUNT_ID, "A-0002", "Wallet")
INACTIVE_ACCOUNT = Account(
    INACTIVE_ACCOUNT_ID,
    "A-0003",
    "Closed Account",
    is_active=False,
)

EXPENSE_CATEGORY = Category(
    EXPENSE_CATEGORY_ID,
    "C-0001",
    "Food",
    "expense",
)
SECOND_EXPENSE_CATEGORY = Category(
    SECOND_EXPENSE_CATEGORY_ID,
    "C-0002",
    "Travel",
    "expense",
)
INCOME_CATEGORY = Category(
    INCOME_CATEGORY_ID,
    "C-0003",
    "Salary",
    "income",
)
INACTIVE_CATEGORY = Category(
    INACTIVE_CATEGORY_ID,
    "C-0004",
    "Old Expense",
    "expense",
    is_active=False,
)

ACCOUNTS = {
    account.id: account
    for account in (ACTIVE_ACCOUNT, SECOND_ACCOUNT, INACTIVE_ACCOUNT)
}
CATEGORIES = {
    category.id: category
    for category in (
        EXPENSE_CATEGORY,
        SECOND_EXPENSE_CATEGORY,
        INCOME_CATEGORY,
        INACTIVE_CATEGORY,
    )
}


@pytest.fixture
def repository(tmp_path) -> JsonTransactionRepository:
    return JsonTransactionRepository(tmp_path / "data" / "transactions.json")


def make_service(
    repository: JsonTransactionRepository,
    *,
    account_lookup=ACCOUNTS.get,
    category_lookup=CATEGORIES.get,
    now: datetime = NOW,
) -> TransactionService:
    return TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: now,
        account_lookup=account_lookup,
        category_lookup=category_lookup,
    )


def add_values(**overrides) -> dict:
    values = {
        "transaction_date": TODAY,
        "transaction_type": "expense",
        "amount": 10.0,
        "category": "Caller Category",
        "account": "Caller Account",
        "description": "Lunch",
    }
    values.update(overrides)
    return values


def persist_transaction(
    repository: JsonTransactionRepository,
    *,
    transaction_type: str = "expense",
    account_id: str | None = ACCOUNT_ID,
    category_id: str | None = EXPENSE_CATEGORY_ID,
    account: str = "Cash Snapshot",
    category: str = "Food Snapshot",
) -> Transaction:
    return repository.create(
        Transaction(
            id="managed-transaction",
            display_id=None,
            type=transaction_type,
            amount=10.0,
            category=category,
            account=account,
            description="Lunch",
            transaction_date=TODAY,
            created_at=NOW,
            updated_at=NOW,
            account_id=account_id,
            category_id=category_id,
        )
    )


def test_legacy_construction_and_add_need_no_lookup_dependencies(
    repository,
) -> None:
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )

    transaction = service.add_transaction(**add_values())

    assert transaction.account == "Caller Account"
    assert transaction.category == "Caller Category"
    assert transaction.account_id is None
    assert transaction.category_id is None


@pytest.mark.parametrize(
    ("reference", "expected_message"),
    [
        ({"account_id": ACCOUNT_ID}, "account lookup is unavailable"),
        ({"category_id": EXPENSE_CATEGORY_ID}, "category lookup is unavailable"),
    ],
)
def test_managed_add_requires_its_lookup_dependency(
    repository,
    reference,
    expected_message: str,
) -> None:
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )

    with pytest.raises(ManagedLookupUnavailableError, match=expected_message):
        service.add_transaction(**add_values(**reference))


def test_add_manages_only_account_independently(repository) -> None:
    transaction = make_service(repository).add_transaction(
        **add_values(account_id=ACCOUNT_ID)
    )

    assert transaction.account_id == ACCOUNT_ID
    assert transaction.account == ACTIVE_ACCOUNT.name
    assert transaction.category_id is None
    assert transaction.category == "Caller Category"


def test_add_manages_only_category_independently(repository) -> None:
    transaction = make_service(repository).add_transaction(
        **add_values(category_id=EXPENSE_CATEGORY_ID)
    )

    assert transaction.category_id == EXPENSE_CATEGORY_ID
    assert transaction.category == EXPENSE_CATEGORY.name
    assert transaction.account_id is None
    assert transaction.account == "Caller Account"


def test_add_resolves_both_references_and_authoritative_snapshots(
    repository,
) -> None:
    transaction = make_service(repository).add_transaction(
        **add_values(
            account_id=ACCOUNT_ID,
            category_id=EXPENSE_CATEGORY_ID,
        )
    )

    assert transaction.account_id == ACCOUNT_ID
    assert transaction.account == ACTIVE_ACCOUNT.name
    assert transaction.category_id == EXPENSE_CATEGORY_ID
    assert transaction.category == EXPENSE_CATEGORY.name
    assert transaction.display_id == "T-0001"
    assert transaction.created_at == NOW
    assert transaction.updated_at == NOW


@pytest.mark.parametrize(
    ("reference", "error_type"),
    [
        ({"account_id": UNKNOWN_ACCOUNT_ID}, ManagedAccountNotFoundError),
        ({"account_id": INACTIVE_ACCOUNT_ID}, ManagedAccountInactiveError),
        ({"category_id": UNKNOWN_CATEGORY_ID}, ManagedCategoryNotFoundError),
        ({"category_id": INACTIVE_CATEGORY_ID}, ManagedCategoryInactiveError),
        ({"category_id": INCOME_CATEGORY_ID}, ManagedCategoryTypeMismatchError),
    ],
)
def test_add_rejects_invalid_managed_references(
    repository,
    reference,
    error_type,
) -> None:
    with pytest.raises(error_type):
        make_service(repository).add_transaction(**add_values(**reference))

    assert repository.list_all() == []


def test_lookup_storage_errors_propagate(repository) -> None:
    def fail_lookup(account_id: str):
        raise StorageError("account data is corrupt")

    service = make_service(repository, account_lookup=fail_lookup)

    with pytest.raises(StorageError, match="account data is corrupt"):
        service.add_transaction(**add_values(account_id=ACCOUNT_ID))


def test_unrelated_update_preserves_historical_inactive_references(
    repository,
) -> None:
    original = persist_transaction(
        repository,
        account_id=INACTIVE_ACCOUNT_ID,
        category_id=INACTIVE_CATEGORY_ID,
        account="Closed Account Snapshot",
        category="Old Expense Snapshot",
    )
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: LATER,
    )

    updated = service.update_transaction(
        original.display_id,
        active_date=TODAY,
        amount=12.0,
    )

    assert updated.account_id == INACTIVE_ACCOUNT_ID
    assert updated.account == "Closed Account Snapshot"
    assert updated.category_id == INACTIVE_CATEGORY_ID
    assert updated.category == "Old Expense Snapshot"
    assert updated.amount == 12.0


def test_new_account_reference_replaces_uuid_and_snapshot(repository) -> None:
    original = persist_transaction(repository)

    updated = make_service(repository, now=LATER).update_transaction(
        original.display_id,
        active_date=TODAY,
        account_id=SECOND_ACCOUNT_ID,
        account="Ignored Caller Text",
    )

    assert updated.account_id == SECOND_ACCOUNT_ID
    assert updated.account == SECOND_ACCOUNT.name
    assert updated.id == original.id
    assert updated.display_id == original.display_id
    assert updated.created_at == NOW
    assert updated.updated_at == LATER


def test_new_category_reference_replaces_uuid_and_snapshot(repository) -> None:
    original = persist_transaction(repository)

    updated = make_service(repository, now=LATER).update_transaction(
        original.display_id,
        active_date=TODAY,
        category_id=SECOND_EXPENSE_CATEGORY_ID,
        category="Ignored Caller Text",
    )

    assert updated.category_id == SECOND_EXPENSE_CATEGORY_ID
    assert updated.category == SECOND_EXPENSE_CATEGORY.name


@pytest.mark.parametrize(
    ("updates", "error_type"),
    [
        ({"account_id": INACTIVE_ACCOUNT_ID}, ManagedAccountInactiveError),
        ({"account_id": UNKNOWN_ACCOUNT_ID}, ManagedAccountNotFoundError),
        ({"category_id": INACTIVE_CATEGORY_ID}, ManagedCategoryInactiveError),
        ({"category_id": UNKNOWN_CATEGORY_ID}, ManagedCategoryNotFoundError),
        ({"category_id": INCOME_CATEGORY_ID}, ManagedCategoryTypeMismatchError),
    ],
)
def test_update_rejects_invalid_new_references_without_replacing(
    repository,
    monkeypatch,
    updates,
    error_type,
) -> None:
    original = persist_transaction(repository)

    def fail_replace(transaction):
        raise AssertionError("replace must not be called")

    monkeypatch.setattr(repository, "replace", fail_replace)

    with pytest.raises(error_type):
        make_service(repository, now=LATER).update_transaction(
            original.display_id,
            active_date=TODAY,
            **updates,
        )


@pytest.mark.parametrize(
    "category_id",
    [EXPENSE_CATEGORY_ID, INACTIVE_CATEGORY_ID],
)
def test_type_change_with_compatible_existing_category_succeeds(
    repository,
    category_id: str,
) -> None:
    # Schema v3 could contain this mismatch before Milestone 3. Changing the
    # transaction to the category's type repairs it, even when history points
    # to an inactive category.
    original = persist_transaction(
        repository,
        transaction_type="income",
        category_id=category_id,
    )

    updated = make_service(repository, now=LATER).update_transaction(
        original.display_id,
        active_date=TODAY,
        transaction_type="expense",
    )

    assert updated.type == "expense"
    assert updated.category_id == category_id
    assert updated.category == original.category


def test_type_change_with_incompatible_existing_category_fails(
    repository,
    monkeypatch,
) -> None:
    original = persist_transaction(repository)

    def fail_replace(transaction):
        raise AssertionError("replace must not be called")

    monkeypatch.setattr(repository, "replace", fail_replace)

    with pytest.raises(ManagedCategoryTypeMismatchError):
        make_service(repository, now=LATER).update_transaction(
            original.display_id,
            active_date=TODAY,
            transaction_type="income",
        )


@pytest.mark.parametrize(
    ("category_id", "category_lookup", "error_type"),
    [
        (
            EXPENSE_CATEGORY_ID,
            None,
            ManagedLookupUnavailableError,
        ),
        (
            UNKNOWN_CATEGORY_ID,
            CATEGORIES.get,
            ManagedCategoryNotFoundError,
        ),
    ],
)
def test_type_change_fails_when_existing_category_cannot_be_resolved(
    repository,
    monkeypatch,
    category_id,
    category_lookup,
    error_type,
) -> None:
    original = persist_transaction(
        repository,
        category_id=category_id,
    )

    def fail_replace(transaction):
        raise AssertionError("replace must not be called")

    monkeypatch.setattr(repository, "replace", fail_replace)

    with pytest.raises(error_type):
        make_service(
            repository,
            category_lookup=category_lookup,
            now=LATER,
        ).update_transaction(
            original.display_id,
            active_date=TODAY,
            transaction_type="income",
        )


def test_type_change_with_new_compatible_category_succeeds(repository) -> None:
    original = persist_transaction(repository)

    updated = make_service(repository, now=LATER).update_transaction(
        original.display_id,
        active_date=TODAY,
        transaction_type="income",
        category_id=INCOME_CATEGORY_ID,
    )

    assert updated.type == "income"
    assert updated.category_id == INCOME_CATEGORY_ID
    assert updated.category == INCOME_CATEGORY.name


def test_legacy_unlinked_type_and_snapshot_updates_remain_supported(
    repository,
) -> None:
    original = persist_transaction(
        repository,
        account_id=None,
        category_id=None,
    )

    updated = make_service(repository, now=LATER).update_transaction(
        original.display_id,
        active_date=TODAY,
        transaction_type="income",
        account="Legacy Wallet",
        category="Legacy Income",
    )

    assert updated.type == "income"
    assert updated.account == "Legacy Wallet"
    assert updated.category == "Legacy Income"
    assert updated.account_id is None
    assert updated.category_id is None


@pytest.mark.parametrize(
    ("updates", "record_type"),
    [
        ({"account": "Renamed Account"}, "Account"),
        ({"category": "Renamed Category"}, "Category"),
    ],
)
def test_direct_managed_snapshot_updates_are_rejected(
    repository,
    monkeypatch,
    updates,
    record_type: str,
) -> None:
    original = persist_transaction(repository)

    def fail_replace(transaction):
        raise AssertionError("replace must not be called")

    monkeypatch.setattr(repository, "replace", fail_replace)

    with pytest.raises(ManagedSnapshotUpdateError, match=record_type):
        make_service(repository, now=LATER).update_transaction(
            original.display_id,
            active_date=TODAY,
            **updates,
        )


@pytest.mark.parametrize(
    ("reference", "record_type"),
    [
        ({"account_id": None}, "account"),
        ({"category_id": None}, "category"),
    ],
)
def test_explicit_reference_clearing_is_rejected(
    repository,
    reference,
    record_type: str,
) -> None:
    original = persist_transaction(repository)

    with pytest.raises(ManagedReferenceClearingError, match=record_type):
        make_service(repository).update_transaction(
            original.display_id,
            active_date=TODAY,
            **reference,
        )
