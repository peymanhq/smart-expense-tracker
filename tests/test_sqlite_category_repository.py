"""SQLite-specific Category repository tests."""

import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from category_repository import (
    CategoryRepositoryConflictError,
    CategoryRepositoryRecordChangedError,
)
from persistence_errors import StorageError
from sqlite_category_repository import SQLiteCategoryRepository
from sqlite_database import SQLiteDatabase
from sqlite_schema import initialize_schema


def category_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, name))


@pytest.fixture
def sqlite_categories(
    tmp_path: Path,
) -> tuple[SQLiteCategoryRepository, SQLiteDatabase]:
    database = SQLiteDatabase(tmp_path / "database.sqlite3")
    initialize_schema(database)
    return SQLiteCategoryRepository(database), database


def test_construction_has_no_side_effect_and_uninitialized_use_fails(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "nested" / "database.sqlite3")
    repository = SQLiteCategoryRepository(database)
    assert not tmp_path.joinpath("nested").exists()

    with pytest.raises(StorageError) as caught:
        repository.list_all()

    assert isinstance(caught.value.__cause__, sqlite3.Error)


def test_mapping_rejects_inconsistent_persisted_name_key(
    sqlite_categories: tuple[SQLiteCategoryRepository, SQLiteDatabase],
) -> None:
    repository, database = sqlite_categories
    created = repository.create(
        category_id("corrupt-category"),
        "Food",
        "expense",
    )
    with database.connection() as connection:
        connection.execute(
            "UPDATE categories SET name_key = 'wrong' WHERE id = ?",
            (created.id,),
        )

    with pytest.raises(StorageError, match="name_key"):
        repository.list_all()


def test_failed_insert_rolls_back_counter_and_record(
    sqlite_categories: tuple[SQLiteCategoryRepository, SQLiteDatabase],
) -> None:
    repository, database = sqlite_categories
    first = repository.create(
        category_id("atomic-category"),
        "Food",
        "expense",
    )

    with pytest.raises(StorageError):
        repository.create(first.id, "Travel", "expense")

    with database.connection() as connection:
        counter = connection.execute(
            """
            SELECT next_value FROM display_id_counters
            WHERE entity_type = 'category'
            """
        ).fetchone()["next_value"]
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM categories"
        ).fetchone()["count"]
    assert counter == 2
    assert count == 1
    assert repository.create(
        category_id("after-failed-category"),
        "Salary",
        "income",
    ).display_id == "C-0002"


def test_malformed_create_is_neutral_and_does_not_advance_counter(
    sqlite_categories: tuple[SQLiteCategoryRepository, SQLiteDatabase],
) -> None:
    repository, _ = sqlite_categories

    with pytest.raises(StorageError):
        repository.create(  # type: ignore[arg-type]
            category_id("non-text-category"),
            None,
            "expense",
        )

    assert repository.create(
        category_id("valid-after-malformed-category"),
        "Food",
        "expense",
    ).display_id == "C-0001"


def test_competing_instances_allocate_distinct_ids_and_recheck_scoped_names(
    sqlite_categories: tuple[SQLiteCategoryRepository, SQLiteDatabase],
) -> None:
    first_repository, database = sqlite_categories
    second_repository = SQLiteCategoryRepository(database)

    first = first_repository.create(
        category_id("first-instance"),
        "Food",
        "expense",
    )
    second = second_repository.create(
        category_id("second-instance"),
        "Salary",
        "income",
    )
    with pytest.raises(CategoryRepositoryConflictError):
        second_repository.create(
            category_id("duplicate-instance"),
            "FOOD",
            "expense",
        )

    assert {first.display_id, second.display_id} == {"C-0001", "C-0002"}
    assert len(first_repository.list_all()) == 2


def test_competing_activation_and_rename_conflicts_are_rechecked(
    sqlite_categories: tuple[SQLiteCategoryRepository, SQLiteDatabase],
) -> None:
    first_repository, database = sqlite_categories
    second_repository = SQLiteCategoryRepository(database)
    first = first_repository.create(
        category_id("activation-1"),
        "Food",
        "expense",
    )
    second = first_repository.create(
        category_id("activation-2"),
        "Travel",
        "expense",
    )
    inactive = first_repository.replace(
        first,
        replace(first, is_active=False),
    )
    second_repository.replace(second, replace(second, name="Food"))

    with pytest.raises(CategoryRepositoryConflictError):
        first_repository.replace(
            inactive,
            replace(inactive, is_active=True),
        )

    current_second = first_repository.get_by_id(second.id)
    assert current_second is not None
    first_repository.replace(
        current_second,
        replace(current_second, name="Dining"),
    )
    with pytest.raises(CategoryRepositoryConflictError):
        second_repository.replace(
            inactive,
            replace(inactive, name="Dining", is_active=True),
        )


def test_stale_replace_does_not_overwrite_competing_change(
    sqlite_categories: tuple[SQLiteCategoryRepository, SQLiteDatabase],
) -> None:
    first_repository, database = sqlite_categories
    second_repository = SQLiteCategoryRepository(database)
    created = first_repository.create(
        category_id("stale-category"),
        "Food",
        "expense",
    )
    stale = second_repository.get_by_id(created.id)
    assert stale == created
    first_repository.replace(created, replace(created, name="Dining"))

    with pytest.raises(CategoryRepositoryRecordChangedError):
        second_repository.replace(stale, replace(stale, name="Travel"))

    assert first_repository.get_by_id(created.id).name == "Dining"


def test_failed_update_rolls_back_without_partial_mutation(
    sqlite_categories: tuple[SQLiteCategoryRepository, SQLiteDatabase],
) -> None:
    repository, database = sqlite_categories
    created = repository.create(
        category_id("invalid-update"),
        "Food",
        "expense",
    )

    with pytest.raises(StorageError):
        repository.replace(created, replace(created, name=""))

    assert repository.get_by_id(created.id) == created
    with database.connection() as connection:
        assert connection.execute(
            """
            SELECT next_value FROM display_id_counters
            WHERE entity_type = 'category'
            """
        ).fetchone()["next_value"] == 2


def test_database_lock_is_translated_without_consuming_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "database.sqlite3"
    database = SQLiteDatabase(path, busy_timeout_ms=0)
    initialize_schema(database)
    repository = SQLiteCategoryRepository(database)

    with database.transaction():
        with pytest.raises(StorageError) as caught:
            repository.create(
                category_id("locked-category"),
                "Food",
                "expense",
            )

    assert isinstance(caught.value.__cause__, sqlite3.OperationalError)
    assert repository.create(
        category_id("after-lock-category"),
        "Food",
        "expense",
    ).display_id == "C-0001"
