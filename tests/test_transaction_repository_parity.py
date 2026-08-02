"""Backend-neutral Transaction repository contract tests."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3
from typing import Callable
from uuid import NAMESPACE_URL, uuid5

from openpyxl import Workbook
import pytest

from excel_import_service import (
    ExcelImportPersistenceConflictError,
    ExcelImportService,
)
from excel_workbook import REQUIRED_TRANSACTION_HEADERS
from persistence_errors import StorageError
from sqlite_account_repository import SQLiteAccountRepository
from sqlite_category_repository import SQLiteCategoryRepository
from sqlite_database import SQLiteDatabase
from sqlite_schema import initialize_schema
from sqlite_transaction_repository import SQLiteTransactionRepository
from transaction import Transaction
from transaction_repository import (
    JsonTransactionRepository,
    RepositoryTransactionConflictError,
    RepositoryTransactionNotFoundError,
    TransactionDateSummary,
    TransactionRepository,
)
from transaction_service import TransactionService

TODAY = date(2026, 8, 2)
PAST = date(2026, 7, 30)
NOW = datetime(2026, 8, 2, 8, 15, tzinfo=timezone.utc)
LATER = datetime(2026, 8, 2, 9, 30, tzinfo=timezone.utc)


def record_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, name))


def candidate(
    name: str,
    *,
    transaction_date: date = TODAY,
    amount: float = 10.0,
    description: str = "Lunch",
    account_id: str | None = None,
    category_id: str | None = None,
) -> Transaction:
    return Transaction(
        id=record_id(name),
        display_id="caller-supplied",
        type="expense",
        amount=amount,
        category="Food snapshot",
        account="Cash snapshot",
        description=description,
        transaction_date=transaction_date,
        created_at=NOW,
        updated_at=NOW,
        account_id=account_id,
        category_id=category_id,
    )


@pytest.fixture(params=["json", "sqlite"])
def transaction_backend(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> tuple[
    TransactionRepository,
    Callable[[], TransactionRepository],
    str,
    str,
]:
    account_id = record_id("managed-account")
    category_id = record_id("managed-category")
    if request.param == "json":
        data_file = tmp_path / "json" / "transactions.json"

        def build() -> TransactionRepository:
            return JsonTransactionRepository(data_file)

    else:
        database = SQLiteDatabase(tmp_path / "sqlite" / "database.sqlite3")
        initialize_schema(database)
        SQLiteAccountRepository(database).create(account_id, "Cash")
        SQLiteCategoryRepository(database).create(
            category_id,
            "Food",
            "expense",
        )

        def build() -> TransactionRepository:
            return SQLiteTransactionRepository(database)

    return build(), build, account_id, category_id


def test_empty_create_lookup_order_and_restart(
    transaction_backend: tuple[
        TransactionRepository,
        Callable[[], TransactionRepository],
        str,
        str,
    ],
) -> None:
    repository, restart, _, _ = transaction_backend
    assert repository.list_all() == []
    assert repository.list_by_date(TODAY) == []
    assert repository.list_date_summaries() == []

    first = repository.create(candidate("first", transaction_date=PAST))
    second = repository.create(candidate("second"))

    assert [first.display_id, second.display_id] == ["T-0001", "T-0002"]
    assert repository.get_by_id(first.id) == first
    assert repository.get_by_id(record_id("missing")) is None
    assert repository.get_by_display_id(" t-0001 ") == first
    assert repository.get_by_display_id("T-1") is None
    assert repository.get_by_display_id("T-9999") is None
    assert restart().list_all() == [first, second]
    detached = repository.list_all()
    detached.clear()
    assert repository.list_all() == [first, second]


def test_bulk_dates_references_and_timestamps(
    transaction_backend: tuple[
        TransactionRepository,
        Callable[[], TransactionRepository],
        str,
        str,
    ],
) -> None:
    repository, _, account_id, category_id = transaction_backend
    created = repository.create_many(
        [
            candidate(
                "bulk-1",
                transaction_date=TODAY,
                description="First",
                account_id=account_id,
                category_id=category_id,
            ),
            candidate(
                "bulk-2",
                transaction_date=PAST,
                amount=20.0,
                description="Second",
                account_id=account_id,
                category_id=category_id,
            ),
            candidate(
                "bulk-3",
                transaction_date=TODAY,
                amount=30.0,
                description="Third",
                account_id=account_id,
                category_id=category_id,
            ),
        ]
    )

    assert [item.display_id for item in created] == [
        "T-0001",
        "T-0002",
        "T-0003",
    ]
    assert repository.list_by_date(TODAY) == [created[0], created[2]]
    assert repository.list_date_summaries() == [
        TransactionDateSummary(TODAY, 2),
        TransactionDateSummary(PAST, 1),
    ]
    assert created[0].account_id == account_id
    assert created[0].category_id == category_id
    assert created[0].account == "Cash snapshot"
    assert created[0].category == "Food snapshot"
    assert created[0].created_at == NOW
    assert created[0].updated_at == NOW


def test_replace_delete_and_monotonic_allocation(
    transaction_backend: tuple[
        TransactionRepository,
        Callable[[], TransactionRepository],
        str,
        str,
    ],
) -> None:
    repository, restart, _, _ = transaction_backend
    original = repository.create(candidate("replace"))
    replacement = replace(
        original,
        display_id="T-9999",
        amount=25.0,
        transaction_date=PAST,
        created_at=LATER,
        updated_at=LATER,
    )

    updated = repository.replace(replacement)

    assert updated.id == original.id
    assert updated.display_id == original.display_id
    assert updated.created_at == original.created_at
    assert updated.updated_at == LATER
    assert restart().get_by_id(original.id) == updated
    assert repository.delete_by_id(original.id) is True
    assert repository.delete_by_id(original.id) is False
    assert restart().create(candidate("after-delete")).display_id == "T-0002"
    with pytest.raises(RepositoryTransactionNotFoundError):
        repository.replace(replace(updated, id=record_id("absent")))


def test_bulk_duplicate_rules_are_atomic(
    transaction_backend: tuple[
        TransactionRepository,
        Callable[[], TransactionRepository],
        str,
        str,
    ],
) -> None:
    repository, _, account_id, category_id = transaction_backend
    existing = repository.create_many(
        [
            candidate(
                "existing",
                account_id=account_id,
                category_id=category_id,
            )
        ]
    )[0]

    with pytest.raises(RepositoryTransactionConflictError) as conflict:
        repository.create_many(
            [
                candidate(
                    "existing-copy",
                    account_id=account_id,
                    category_id=category_id,
                )
            ]
        )
    assert conflict.value.candidate_index == 0
    assert conflict.value.matching_display_id == existing.display_id

    first = candidate(
        "batch-first",
        amount=20.0,
        account_id=account_id,
        category_id=category_id,
    )
    with pytest.raises(RepositoryTransactionConflictError) as conflict:
        repository.create_many([first, replace(first, id=record_id("copy"))])
    assert conflict.value.candidate_index == 1
    assert conflict.value.earlier_candidate_index == 0
    assert repository.list_all() == [existing]
    assert repository.create(
        candidate("after-conflicts")
    ).display_id == "T-0002"


def test_failed_duplicate_uuid_and_bulk_insert_do_not_advance_counter(
    transaction_backend: tuple[
        TransactionRepository,
        Callable[[], TransactionRepository],
        str,
        str,
    ],
) -> None:
    repository, _, account_id, category_id = transaction_backend
    first = repository.create(candidate("duplicate-id"))
    with pytest.raises(StorageError):
        repository.create(replace(candidate("other"), id=first.id))

    duplicate_id = record_id("bulk-duplicate-id")
    with pytest.raises(StorageError):
        repository.create_many(
            [
                candidate(
                    "bulk-a",
                    amount=20.0,
                    account_id=account_id,
                    category_id=category_id,
                ),
                replace(
                    candidate(
                        "bulk-b",
                        amount=30.0,
                        account_id=account_id,
                        category_id=category_id,
                    ),
                    id=duplicate_id,
                ),
                replace(
                    candidate(
                        "bulk-c",
                        amount=40.0,
                        account_id=account_id,
                        category_id=category_id,
                    ),
                    id=duplicate_id,
                ),
            ]
        )

    assert repository.list_all() == [first]
    assert repository.create(candidate("after-failures")).display_id == "T-0002"


def test_create_ignores_externally_supplied_display_id(
    transaction_backend: tuple[
        TransactionRepository,
        Callable[[], TransactionRepository],
        str,
        str,
    ],
) -> None:
    repository, _, _, _ = transaction_backend
    first = repository.create(replace(candidate("external-1"), display_id="T-0042"))
    second = repository.create(replace(candidate("external-2"), display_id="T-0042"))
    assert [first.display_id, second.display_id] == ["T-0001", "T-0002"]


def test_empty_bulk_is_neutral(
    transaction_backend: tuple[
        TransactionRepository,
        Callable[[], TransactionRepository],
        str,
        str,
    ],
) -> None:
    repository, _, _, _ = transaction_backend
    assert repository.create_many([]) == []
    assert repository.create(candidate("after-empty")).display_id == "T-0001"


def test_sqlite_instances_allocate_unique_ids_concurrently(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "concurrent.sqlite3")
    initialize_schema(database)

    def create(index: int) -> Transaction:
        return SQLiteTransactionRepository(database).create(
            candidate(f"concurrent-{index}")
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        created = list(executor.map(create, range(20)))

    assert {item.display_id for item in created} == {
        f"T-{number:04d}" for number in range(1, 21)
    }
    assert len(SQLiteTransactionRepository(database).list_all()) == 20


def test_sqlite_foreign_key_failure_rolls_back_row_and_counter(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "foreign-key.sqlite3")
    initialize_schema(database)
    repository = SQLiteTransactionRepository(database)

    with pytest.raises(StorageError):
        repository.create(
            candidate(
                "missing-reference",
                account_id=record_id("missing-account"),
            )
        )

    assert repository.list_all() == []
    assert repository.create(candidate("after-reference-failure")).display_id == (
        "T-0001"
    )


def test_sqlite_lock_error_is_translated_without_consuming_id(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(
        tmp_path / "locked.sqlite3",
        busy_timeout_ms=0,
    )
    initialize_schema(database)
    repository = SQLiteTransactionRepository(database)

    with database.transaction():
        with pytest.raises(StorageError) as caught:
            repository.create(candidate("locked"))

    assert isinstance(caught.value.__cause__, sqlite3.OperationalError)
    assert repository.create(candidate("after-lock")).display_id == "T-0001"


def test_sqlite_failed_reference_update_preserves_existing_row(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "failed-update.sqlite3")
    initialize_schema(database)
    repository = SQLiteTransactionRepository(database)
    original = repository.create(candidate("update-reference"))

    with pytest.raises(StorageError):
        repository.replace(
            replace(
                original,
                amount=99.0,
                account_id=record_id("missing-update-account"),
            )
        )

    assert repository.get_by_id(original.id) == original


def test_sqlite_malformed_persisted_row_raises_storage_error(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "malformed-row.sqlite3")
    initialize_schema(database)
    repository = SQLiteTransactionRepository(database)
    original = repository.create(candidate("malformed-row"))
    with database.connection() as connection:
        connection.execute(
            "UPDATE transactions SET created_at = 'not-a-timestamp' WHERE id = ?",
            (original.id,),
        )

    with pytest.raises(StorageError, match="record is invalid"):
        repository.get_by_id(original.id)


def test_sqlite_excel_import_late_duplicate_uses_repository_contract(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "excel.sqlite3")
    initialize_schema(database)
    account = SQLiteAccountRepository(database).create(
        record_id("excel-account"),
        "Cash",
    )
    category = SQLiteCategoryRepository(database).create(
        record_id("excel-category"),
        "Food",
        "expense",
    )
    repository = SQLiteTransactionRepository(database)
    service = TransactionService(
        repository,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
        account_lookup=lambda account_id: (
            account if account_id == account.id else None
        ),
        category_lookup=lambda category_id: (
            category if category_id == category.id else None
        ),
    )
    importer = ExcelImportService(
        service,
        account_list=lambda: [account],
        category_list=lambda: [category],
    )
    source = tmp_path / "late-duplicate.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Transactions"
    worksheet.append(REQUIRED_TRANSACTION_HEADERS)
    worksheet.append(("2026-08-02", "Expense", 10, "Lunch", "Cash", "Food"))
    workbook.save(source)
    workbook.close()
    preview = importer.analyze(source)
    service.add_transaction(
        transaction_date=TODAY,
        transaction_type="expense",
        amount=10,
        category="Food",
        account="Cash",
        description="Lunch",
        account_id=account.id,
        category_id=category.id,
    )

    with pytest.raises(
        ExcelImportPersistenceConflictError,
        match="existing transaction T-0001",
    ):
        importer.persist(preview)

    assert [item.display_id for item in repository.list_all()] == ["T-0001"]
