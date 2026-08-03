"""Application composition and workspace-isolation contracts."""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import account_service
from account_repository import JsonAccountRepository
from application import (
    ApplicationServices,
    build_application,
    build_json_application,
    build_sqlite_application,
)
import category_service
from category_repository import JsonCategoryRepository
from json_storage import StorageError as JsonStorageError
import main
from persistence_errors import StorageError
import storage
from transaction_repository import JsonTransactionRepository
from sqlite_account_repository import SQLiteAccountRepository
from sqlite_category_repository import SQLiteCategoryRepository
from sqlite_transaction_repository import SQLiteTransactionRepository
import transaction_service
from transaction_service import TransactionService

TODAY = date(2026, 7, 27)
NOW = datetime(2026, 7, 27, 10, 30, tzinfo=timezone.utc)


def build(workspace_root: Path) -> ApplicationServices:
    return build_json_application(
        workspace_root,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )


def test_composition_builds_json_services_without_creating_files(
    tmp_path: Path,
) -> None:
    application = build(tmp_path)

    assert isinstance(application, ApplicationServices)
    assert isinstance(
        application.account_service._repository,
        JsonAccountRepository,
    )
    assert isinstance(
        application.category_service._repository,
        JsonCategoryRepository,
    )
    assert isinstance(
        application.transaction_service._repository,
        JsonTransactionRepository,
    )
    assert application.excel_import_service._transaction_service is (
        application.transaction_service
    )
    assert not (tmp_path / "data").exists()


def test_composition_builds_initialized_sqlite_services(tmp_path: Path) -> None:
    application = build_sqlite_application(tmp_path)

    assert isinstance(
        application.account_service._repository,
        SQLiteAccountRepository,
    )
    assert isinstance(
        application.category_service._repository,
        SQLiteCategoryRepository,
    )
    assert isinstance(
        application.transaction_service._repository,
        SQLiteTransactionRepository,
    )
    assert (tmp_path / "data" / "smart_expense_tracker.sqlite3").is_file()


@pytest.mark.parametrize("backend", ["json", " JSON "])
def test_generic_composition_keeps_json_as_default_and_normalizes_backend(
    tmp_path: Path,
    backend: str,
) -> None:
    application = build_application(tmp_path, backend=backend)
    assert isinstance(
        application.transaction_service._repository,
        JsonTransactionRepository,
    )
    assert not (tmp_path / "data").exists()


def test_generic_composition_selects_sqlite_and_rejects_invalid_options(
    tmp_path: Path,
) -> None:
    application = build_application(tmp_path, backend="SQLITE")
    assert isinstance(
        application.transaction_service._repository,
        SQLiteTransactionRepository,
    )
    with pytest.raises(ValueError, match="Unsupported storage backend"):
        build_application(tmp_path, backend="postgres")
    with pytest.raises(ValueError, match="only valid with the sqlite"):
        build_application(tmp_path, migrate_json=True)


def test_main_consumes_the_composed_application_dependencies() -> None:
    assert main.TRANSACTION_SERVICE is main.APPLICATION.transaction_service
    assert main.ACCOUNT_SERVICE is main.APPLICATION.account_service
    assert main.CATEGORY_SERVICE is main.APPLICATION.category_service
    assert main.EXCEL_IMPORT_SERVICE is main.APPLICATION.excel_import_service
    assert main.list_accounts is main.APPLICATION.account_list
    assert main.list_categories is main.APPLICATION.category_list


def test_services_do_not_import_concrete_json_repositories() -> None:
    for module in (account_service, category_service, transaction_service):
        assert "JsonAccountRepository" not in vars(module)
        assert "JsonCategoryRepository" not in vars(module)
        assert "JsonTransactionRepository" not in vars(module)


def test_composed_dependencies_share_one_workspace_and_detached_lists(
    tmp_path: Path,
) -> None:
    application = build(tmp_path)
    account = application.account_service.add_account("Cash").account
    category = application.category_service.add_category(
        "Food",
        "expense",
    ).category
    assert account is not None
    assert category is not None

    created = application.transaction_service.add_transaction(
        transaction_date=TODAY,
        transaction_type="expense",
        amount=12.5,
        category=category.name,
        account=account.name,
        description="Lunch",
        account_id=account.id,
        category_id=category.id,
    )

    assert created.account_id == account.id
    assert created.category_id == category.id
    assert application.account_lookup(account.id) == account
    assert application.category_lookup(category.id) == category
    assert application.active_account_list() == [account]
    assert application.active_category_list() == [category]
    assert application.excel_import_service._account_list() == [account]
    assert application.excel_import_service._category_list() == [category]

    detached_accounts = application.account_list()
    detached_accounts.clear()
    assert application.account_list() == [account]
    assert {
        path.name for path in (tmp_path / "data").iterdir()
        if not path.name.startswith(".")
    } == {
        "accounts.json",
        "categories.json",
        "categories_state.json",
        "transactions.json",
    }


def test_separate_workspace_roots_do_not_share_state(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = build(first_root)
    second = build(second_root)

    created = first.account_service.add_account("Cash").account

    assert created is not None
    assert first.account_list() == [created]
    assert second.account_list() == []
    assert (first_root / "data" / "accounts.json").exists()
    assert not (second_root / "data").exists()


def test_default_composition_tracks_current_working_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    application = build_json_application(
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )
    assert not (tmp_path / "data").exists()

    application.account_service.add_account("Cash")

    assert (tmp_path / "data" / "accounts.json").exists()


def test_transaction_service_requires_explicit_repository() -> None:
    with pytest.raises(TypeError):
        TransactionService()  # type: ignore[call-arg]


def test_storage_error_remains_compatible_and_backend_neutral() -> None:
    assert JsonStorageError is StorageError


def test_legacy_transaction_storage_functions_remain_compatibility_surface() -> None:
    assert callable(storage.load_transactions)
    assert callable(storage.save_transaction)
    assert callable(storage.update_transaction)
    assert callable(storage.delete_transaction)
