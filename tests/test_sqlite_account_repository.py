"""SQLite-specific Account repository tests."""

import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from account_repository import (
    AccountRepositoryConflictError,
    AccountRepositoryRecordChangedError,
)
from persistence_errors import StorageError
from sqlite_account_repository import SQLiteAccountRepository
from sqlite_database import SQLiteDatabase
from sqlite_schema import initialize_schema


def account_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, name))


@pytest.fixture
def sqlite_accounts(
    tmp_path: Path,
) -> tuple[SQLiteAccountRepository, SQLiteDatabase]:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")
    initialize_schema(database)
    return SQLiteAccountRepository(database), database


def test_construction_has_no_side_effect_and_uninitialized_use_fails(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "nested" / "database.sqlite3")
    repository = SQLiteAccountRepository(database)
    assert not tmp_path.joinpath("nested").exists()

    with pytest.raises(StorageError) as caught:
        repository.list_all()

    assert isinstance(caught.value.__cause__, sqlite3.Error)


def test_mapping_rejects_inconsistent_persisted_name_key(
    sqlite_accounts: tuple[SQLiteAccountRepository, SQLiteDatabase],
) -> None:
    repository, database = sqlite_accounts
    created = repository.create(account_id("corrupt-account"), "Cash")
    with database.connection() as connection:
        connection.execute(
            "UPDATE accounts SET name_key = 'wrong' WHERE id = ?",
            (created.id,),
        )

    with pytest.raises(StorageError, match="name_key"):
        repository.list_all()


def test_failed_insert_rolls_back_counter_and_record(
    sqlite_accounts: tuple[SQLiteAccountRepository, SQLiteDatabase],
) -> None:
    repository, database = sqlite_accounts
    first = repository.create(account_id("atomic-account"), "Cash")

    with pytest.raises(StorageError):
        repository.create(first.id, "Bank")

    with database.connection() as connection:
        counter = connection.execute(
            """
            SELECT next_value FROM display_id_counters
            WHERE entity_type = 'account'
            """
        ).fetchone()["next_value"]
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM accounts"
        ).fetchone()["count"]
    assert counter == 2
    assert count == 1
    assert repository.create(
        account_id("after-failed-account"),
        "Savings",
    ).display_id == "A-0002"


def test_malformed_create_is_neutral_and_does_not_advance_counter(
    sqlite_accounts: tuple[SQLiteAccountRepository, SQLiteDatabase],
) -> None:
    repository, _ = sqlite_accounts

    with pytest.raises(StorageError):
        repository.create(
            account_id("non-text-account"),
            None,  # type: ignore[arg-type]
        )

    assert repository.create(
        account_id("valid-after-malformed-account"),
        "Cash",
    ).display_id == "A-0001"


def test_competing_instances_allocate_distinct_ids_and_recheck_names(
    sqlite_accounts: tuple[SQLiteAccountRepository, SQLiteDatabase],
) -> None:
    first_repository, database = sqlite_accounts
    second_repository = SQLiteAccountRepository(database)

    first = first_repository.create(account_id("first-instance"), "Cash")
    second = second_repository.create(account_id("second-instance"), "Bank")
    with pytest.raises(AccountRepositoryConflictError):
        second_repository.create(account_id("duplicate-instance"), "CASH")

    assert {first.display_id, second.display_id} == {"A-0001", "A-0002"}
    assert len(first_repository.list_all()) == 2


def test_competing_activation_and_rename_conflicts_are_rechecked(
    sqlite_accounts: tuple[SQLiteAccountRepository, SQLiteDatabase],
) -> None:
    first_repository, database = sqlite_accounts
    second_repository = SQLiteAccountRepository(database)
    first = first_repository.create(account_id("activation-1"), "Cash")
    second = first_repository.create(account_id("activation-2"), "Bank")
    inactive = first_repository.replace(
        first,
        replace(first, is_active=False),
    )
    second_repository.replace(second, replace(second, name="Cash"))

    with pytest.raises(AccountRepositoryConflictError):
        first_repository.replace(
            inactive,
            replace(inactive, is_active=True),
        )

    current_second = first_repository.get_by_id(second.id)
    assert current_second is not None
    first_repository.replace(
        current_second,
        replace(current_second, name="Wallet"),
    )
    with pytest.raises(AccountRepositoryConflictError):
        second_repository.replace(
            inactive,
            replace(inactive, name="Wallet", is_active=True),
        )


def test_stale_replace_does_not_overwrite_competing_change(
    sqlite_accounts: tuple[SQLiteAccountRepository, SQLiteDatabase],
) -> None:
    first_repository, database = sqlite_accounts
    second_repository = SQLiteAccountRepository(database)
    created = first_repository.create(account_id("stale-account"), "Cash")
    stale = second_repository.get_by_id(created.id)
    assert stale == created
    first_repository.replace(created, replace(created, name="Wallet"))

    with pytest.raises(AccountRepositoryRecordChangedError):
        second_repository.replace(stale, replace(stale, name="Bank"))

    assert first_repository.get_by_id(created.id).name == "Wallet"


def test_failed_update_rolls_back_without_partial_mutation(
    sqlite_accounts: tuple[SQLiteAccountRepository, SQLiteDatabase],
) -> None:
    repository, database = sqlite_accounts
    created = repository.create(account_id("invalid-update"), "Cash")

    with pytest.raises(StorageError):
        repository.replace(created, replace(created, name=""))

    assert repository.get_by_id(created.id) == created
    with database.connection() as connection:
        assert connection.execute(
            """
            SELECT next_value FROM display_id_counters
            WHERE entity_type = 'account'
            """
        ).fetchone()["next_value"] == 2


def test_database_lock_is_translated_without_consuming_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "database.sqlite3"
    database = SQLiteDatabase(path, busy_timeout_ms=0)
    initialize_schema(database)
    repository = SQLiteAccountRepository(database)

    with database.transaction():
        with pytest.raises(StorageError) as caught:
            repository.create(account_id("locked-account"), "Cash")

    assert isinstance(caught.value.__cause__, sqlite3.OperationalError)
    assert repository.create(
        account_id("after-lock-account"),
        "Cash",
    ).display_id == "A-0001"
