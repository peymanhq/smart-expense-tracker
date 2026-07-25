import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

import storage
from json_storage import StorageError
from transaction import Transaction
from transaction_repository import JsonTransactionRepository
from transaction_service import (
    FutureTransactionDateError,
    InvalidUtcClockError,
    TransactionActiveDateMismatchError,
    TransactionNotFoundError,
    TransactionService,
)


TODAY = date(2026, 7, 25)
PAST_DATE = date(2026, 7, 21)
NOW = datetime(2026, 7, 25, 9, 15, tzinfo=timezone.utc)
LATER = datetime(2026, 7, 25, 10, 30, tzinfo=timezone.utc)
ACCOUNT_ID = "123e4567-e89b-12d3-a456-426614174000"
CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174001"


@pytest.fixture
def repository(tmp_path) -> JsonTransactionRepository:
    return JsonTransactionRepository(tmp_path / "data" / "transactions.json")


@pytest.fixture
def service(repository) -> TransactionService:
    return TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )


def add_expense(
    service: TransactionService,
    transaction_date: date = TODAY,
    *,
    description: str = "Lunch",
) -> Transaction:
    return service.add_transaction(
        transaction_date=transaction_date,
        transaction_type="expense",
        amount=10.0,
        category="Food",
        account="Cash",
        description=description,
    )


def test_injected_today_accepts_today_and_past(
    service: TransactionService,
) -> None:
    today_transaction = add_expense(service, TODAY)
    past_transaction = add_expense(service, PAST_DATE)

    assert today_transaction.transaction_date == TODAY
    assert past_transaction.transaction_date == PAST_DATE


def test_future_date_is_rejected_on_add(
    service: TransactionService,
) -> None:
    with pytest.raises(FutureTransactionDateError) as captured:
        add_expense(service, TODAY + timedelta(days=1))

    assert captured.value.today == TODAY
    assert captured.value.transaction_date == TODAY + timedelta(days=1)


def test_future_date_is_rejected_when_moving_transaction(
    service: TransactionService,
) -> None:
    transaction = add_expense(service)

    with pytest.raises(FutureTransactionDateError):
        service.update_transaction(
            transaction.display_id,
            active_date=TODAY,
            transaction_date=TODAY + timedelta(days=1),
        )

    assert service.list_transactions_by_date(TODAY) == [transaction]


def test_future_date_is_rejected_for_date_listing(
    service: TransactionService,
) -> None:
    with pytest.raises(FutureTransactionDateError):
        service.list_transactions_by_date(TODAY + timedelta(days=1))


def test_public_workspace_date_validation_uses_injected_today(
    service: TransactionService,
) -> None:
    assert service.validate_transaction_date(TODAY) == TODAY
    assert service.validate_transaction_date(PAST_DATE) == PAST_DATE
    with pytest.raises(FutureTransactionDateError):
        service.validate_transaction_date(TODAY + timedelta(days=1))


def test_query_policy_accepts_same_day_and_rejects_reversed_range(
    service: TransactionService,
) -> None:
    dates = service.validate_date_query(
        start_date=PAST_DATE,
        end_date=PAST_DATE,
    )
    assert dates.start_date == PAST_DATE
    assert dates.end_date == PAST_DATE

    with pytest.raises(ValueError, match="Start date"):
        service.validate_date_query(
            start_date=TODAY,
            end_date=PAST_DATE,
        )


@pytest.mark.parametrize(
    "criteria",
    [
        {"transaction_date": TODAY + timedelta(days=1)},
        {"start_date": TODAY + timedelta(days=1)},
        {"end_date": TODAY + timedelta(days=1)},
    ],
)
def test_query_policy_rejects_every_future_boundary(
    service: TransactionService,
    criteria,
) -> None:
    with pytest.raises(FutureTransactionDateError):
        service.validate_date_query(**criteria)


def test_query_policy_rejects_exact_date_plus_range(
    service: TransactionService,
) -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        service.validate_date_query(
            transaction_date=PAST_DATE,
            start_date=PAST_DATE,
        )


def test_service_lists_all_transactions_for_read_workflows(
    service: TransactionService,
) -> None:
    past = add_expense(service, PAST_DATE)
    today = add_expense(service, TODAY)

    assert service.list_transactions() == [past, today]


@pytest.mark.parametrize(
    "clock_value",
    [
        datetime(2026, 7, 25, 9, 15),
        datetime(
            2026,
            7,
            25,
            12,
            15,
            tzinfo=timezone(timedelta(hours=3)),
        ),
    ],
)
def test_invalid_utc_clock_output_is_rejected_safely(
    repository,
    clock_value: datetime,
) -> None:
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: clock_value,
    )

    with pytest.raises(InvalidUtcClockError, match="timezone-aware UTC"):
        add_expense(service)

    assert repository.list_by_date(TODAY) == []


def test_creation_assigns_identity_date_and_same_timestamps(
    service: TransactionService,
) -> None:
    transaction = add_expense(service, PAST_DATE)

    assert UUID(transaction.id)
    assert transaction.display_id == "T-0001"
    assert transaction.transaction_date == PAST_DATE
    assert transaction.created_at == NOW
    assert transaction.updated_at == NOW
    assert transaction.account_id is None
    assert transaction.category_id is None


def test_display_ids_are_monotonic_and_not_reused_after_delete(
    service: TransactionService,
) -> None:
    first = add_expense(service)
    second = add_expense(service)
    service.delete_transaction(second.display_id, active_date=TODAY)

    third = add_expense(service)

    assert first.display_id == "T-0001"
    assert second.display_id == "T-0002"
    assert third.display_id == "T-0003"


def test_repository_create_rejects_duplicate_internal_id_without_writing(
    repository,
    service,
) -> None:
    original = add_expense(service)
    duplicate = replace(
        original,
        display_id=None,
        description="Duplicate identity",
    )

    with pytest.raises(StorageError, match="Duplicate transaction id"):
        repository.create(duplicate)

    assert repository.list_all() == [original]


def test_create_reads_allocates_and_writes_inside_one_lock(
    tmp_path,
    monkeypatch,
) -> None:
    repository = JsonTransactionRepository(
        tmp_path / "data" / "transactions.json"
    )
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )
    lock_active = False
    original_read = storage._read_document
    original_write = storage._write_document

    @contextmanager
    def tracking_lock(data_file=None):
        nonlocal lock_active
        assert lock_active is False
        lock_active = True
        try:
            yield
        finally:
            lock_active = False

    def checked_read(data_file=None):
        assert lock_active is True
        return original_read(data_file)

    def checked_write(document, data_file=None):
        assert lock_active is True
        return original_write(document, data_file)

    monkeypatch.setattr(storage, "transaction_file_lock", tracking_lock)
    monkeypatch.setattr(storage, "_read_document", checked_read)
    monkeypatch.setattr(storage, "_write_document", checked_write)

    transaction = add_expense(service)

    assert transaction.display_id == "T-0001"
    assert lock_active is False


def test_concurrent_creation_has_no_losses_or_duplicate_display_ids(
    tmp_path,
) -> None:
    data_file = tmp_path / "data" / "transactions.json"

    def create(index: int) -> Transaction:
        concurrent_service = TransactionService(
            JsonTransactionRepository(data_file),
            today_provider=lambda: TODAY,
            utc_now_provider=lambda: NOW,
        )
        return add_expense(
            concurrent_service,
            description=f"Transaction {index}",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        created = list(executor.map(create, range(24)))

    reloaded = JsonTransactionRepository(data_file).list_by_date(TODAY)
    display_ids = {transaction.display_id for transaction in created}
    assert len(reloaded) == 24
    assert len(display_ids) == 24
    assert display_ids == {f"T-{number:04d}" for number in range(1, 25)}


def test_replace_and_delete_read_modify_write_are_fully_locked(
    repository,
    service,
    monkeypatch,
) -> None:
    transaction = add_expense(service)
    lock_active = False
    lock_entries = 0
    original_read = storage._read_document
    original_write = storage._write_document

    @contextmanager
    def tracking_lock(data_file=None):
        nonlocal lock_active, lock_entries
        assert lock_active is False
        lock_active = True
        lock_entries += 1
        try:
            yield
        finally:
            lock_active = False

    def checked_read(data_file=None):
        assert lock_active is True
        return original_read(data_file)

    def checked_write(document, data_file=None):
        assert lock_active is True
        return original_write(document, data_file)

    monkeypatch.setattr(storage, "transaction_file_lock", tracking_lock)
    monkeypatch.setattr(storage, "_read_document", checked_read)
    monkeypatch.setattr(storage, "_write_document", checked_write)

    replaced = repository.replace(replace(transaction, amount=15.0))
    assert repository.delete_by_id(replaced.id) is True

    assert lock_entries == 2
    assert lock_active is False


def test_exact_date_listing_is_isolated_and_deterministic(
    service: TransactionService,
) -> None:
    first_today = add_expense(service, TODAY, description="First")
    add_expense(service, PAST_DATE)
    second_today = add_expense(service, TODAY, description="Second")

    assert service.list_transactions_by_date(TODAY) == [
        first_today,
        second_today,
    ]
    assert service.list_transactions_by_date(date(2026, 7, 20)) == []


def test_global_display_id_lookup(repository, service) -> None:
    transaction = add_expense(service, PAST_DATE)

    assert repository.get_by_display_id(" t-0001 ") == transaction
    assert repository.get_by_display_id("T-9999") is None


def test_date_summaries_are_distinct_counted_and_newest_first(
    service: TransactionService,
) -> None:
    add_expense(service, PAST_DATE)
    add_expense(service, TODAY)
    add_expense(service, PAST_DATE)

    summaries = service.list_transaction_date_summaries()

    assert [
        (summary.transaction_date, summary.transaction_count)
        for summary in summaries
    ] == [(TODAY, 1), (PAST_DATE, 2)]


def test_empty_repository_has_no_date_summaries(
    service: TransactionService,
) -> None:
    assert service.list_transaction_date_summaries() == []


def test_update_preserves_identity_and_creation_time_and_advances_update(
    repository,
) -> None:
    clock_values = iter([NOW, LATER])
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: next(clock_values),
    )
    original = add_expense(service)

    updated = service.update_transaction(
        original.display_id,
        active_date=TODAY,
        transaction_type="income",
        amount=25.5,
        category="Salary",
        account="Bank",
        description="Correction",
    )

    assert updated.id == original.id
    assert updated.display_id == original.display_id
    assert updated.created_at == NOW
    assert updated.updated_at == LATER
    assert updated.type == "income"
    assert updated.amount == 25.5
    assert updated.category == "Salary"
    assert updated.account == "Bank"
    assert updated.description == "Correction"
    assert JsonTransactionRepository(
        repository._data_file
    ).get_by_display_id(original.display_id) == updated


def test_unrelated_update_preserves_reference_ids(repository) -> None:
    original = repository.create(
        Transaction(
            id="transaction-with-references",
            display_id=None,
            type="expense",
            amount=10.0,
            category="Food",
            account="Cash",
            description="Lunch",
            transaction_date=TODAY,
            created_at=NOW,
            updated_at=NOW,
            account_id=ACCOUNT_ID,
            category_id=CATEGORY_ID,
        )
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

    assert updated.category == original.category
    assert updated.account == original.account
    assert updated.account_id == ACCOUNT_ID
    assert updated.category_id == CATEGORY_ID
    assert updated.amount == 12.0
    assert updated.id == original.id
    assert updated.display_id == original.display_id
    assert updated.created_at == NOW
    assert updated.updated_at == LATER
    assert JsonTransactionRepository(
        repository._data_file
    ).get_by_display_id(original.display_id) == updated


def test_metadata_only_update_advances_updated_at(repository) -> None:
    clock_values = iter([NOW, LATER])
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: next(clock_values),
    )
    original = add_expense(service)

    updated = service.update_transaction(
        original.display_id,
        active_date=TODAY,
    )

    assert updated.updated_at == LATER
    assert updated.description == original.description


def test_update_active_date_mismatch_is_distinct(
    service: TransactionService,
) -> None:
    transaction = add_expense(service, PAST_DATE)

    with pytest.raises(TransactionActiveDateMismatchError) as captured:
        service.update_transaction(
            transaction.display_id,
            active_date=TODAY,
            amount=20,
        )

    assert captured.value.transaction_date == PAST_DATE
    assert captured.value.active_date == TODAY
    assert "belongs to 2026-07-21" in str(captured.value)


def test_update_missing_transaction_is_not_found(
    service: TransactionService,
) -> None:
    with pytest.raises(TransactionNotFoundError):
        service.update_transaction("T-9999", active_date=TODAY, amount=20)


def test_update_moves_date_and_survives_reload(repository) -> None:
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )
    original = add_expense(service, PAST_DATE)

    moved = service.update_transaction(
        original.display_id,
        active_date=PAST_DATE,
        transaction_date=TODAY,
    )

    reloaded = JsonTransactionRepository(repository._data_file)
    assert moved.id == original.id
    assert moved.display_id == original.display_id
    assert reloaded.list_by_date(PAST_DATE) == []
    assert reloaded.list_by_date(TODAY) == [moved]


def test_legacy_update_preserves_missing_created_at(repository) -> None:
    legacy = repository.create(
        Transaction(
            id="legacy-uuid",
            display_id=None,
            type="expense",
            amount=10.0,
            category="Food",
            account="Cash",
            description="Lunch",
            transaction_date=PAST_DATE,
            created_at=None,
            updated_at=None,
        )
    )
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: LATER,
    )

    updated = service.update_transaction(
        legacy.display_id,
        active_date=PAST_DATE,
        amount=12.0,
    )

    assert updated.created_at is None
    assert updated.updated_at == LATER
    assert JsonTransactionRepository(
        repository._data_file
    ).get_by_display_id(legacy.display_id) == updated


def test_delete_active_date_match_removes_only_target_and_survives_reload(
    repository,
) -> None:
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )
    target = add_expense(service)
    survivor = add_expense(service)

    deleted = service.delete_transaction(target.display_id, active_date=TODAY)

    reloaded = JsonTransactionRepository(repository._data_file)
    assert deleted == target
    assert reloaded.get_by_display_id(target.display_id) is None
    assert reloaded.list_by_date(TODAY) == [survivor]


def test_delete_active_date_mismatch_is_distinct(
    service: TransactionService,
) -> None:
    transaction = add_expense(service, PAST_DATE)

    with pytest.raises(TransactionActiveDateMismatchError):
        service.delete_transaction(transaction.display_id, active_date=TODAY)

    assert service.list_transactions_by_date(PAST_DATE) == [transaction]


def test_delete_missing_transaction_is_not_found(
    service: TransactionService,
) -> None:
    with pytest.raises(TransactionNotFoundError):
        service.delete_transaction("T-9999", active_date=TODAY)


def test_repository_uses_atomic_writer(repository, service, monkeypatch) -> None:
    called = False
    original_write = storage.write_json_atomic

    def tracking_write(*args, **kwargs):
        nonlocal called
        called = True
        return original_write(*args, **kwargs)

    monkeypatch.setattr(storage, "write_json_atomic", tracking_write)

    add_expense(service)

    assert called is True


@pytest.mark.parametrize(
    "document",
    [
        {"metadata": {"next_display_id": 1}, "transactions": ["bad"]},
        {
            "schema_version": 99,
            "metadata": {"next_display_id": 1},
            "transactions": [],
        },
    ],
)
def test_repository_fails_safely_on_invalid_storage(
    tmp_path,
    document,
) -> None:
    data_file = tmp_path / "data" / "transactions.json"
    data_file.parent.mkdir(parents=True)
    original = json.dumps(document)
    data_file.write_text(original, encoding="utf-8")
    repository = JsonTransactionRepository(data_file)

    with pytest.raises(StorageError):
        repository.list_date_summaries()

    assert data_file.read_text(encoding="utf-8") == original
