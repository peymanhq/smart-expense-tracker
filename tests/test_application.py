"""SQLite-only application composition contracts."""

from datetime import date, datetime, timezone
from pathlib import Path

import account_service
import category_service
import main
import transaction_service
from application import ApplicationServices, build_application
from sqlite_account_repository import SQLiteAccountRepository
from sqlite_category_repository import SQLiteCategoryRepository
from sqlite_transaction_repository import SQLiteTransactionRepository

TODAY = date(2026, 7, 27)
NOW = datetime(2026, 7, 27, 10, 30, tzinfo=timezone.utc)


def build(workspace_root: Path) -> ApplicationServices:
    return build_application(
        workspace_root,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )


def test_composition_builds_initialized_sqlite_services(tmp_path: Path) -> None:
    application = build(tmp_path)

    assert isinstance(application, ApplicationServices)
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
    assert application.excel_import_service._transaction_service is (
        application.transaction_service
    )
    assert (tmp_path / "data" / "smart_expense_tracker.sqlite3").is_file()


def test_main_consumes_composed_application_dependencies() -> None:
    assert main.TRANSACTION_SERVICE is main.APPLICATION.transaction_service
    assert main.ACCOUNT_SERVICE is main.APPLICATION.account_service
    assert main.CATEGORY_SERVICE is main.APPLICATION.category_service
    assert main.EXCEL_IMPORT_SERVICE is main.APPLICATION.excel_import_service


def test_services_do_not_import_concrete_repositories() -> None:
    for module in (account_service, category_service, transaction_service):
        assert "SQLiteAccountRepository" not in vars(module)
        assert "SQLiteCategoryRepository" not in vars(module)
        assert "SQLiteTransactionRepository" not in vars(module)


def test_composed_dependencies_share_one_workspace(tmp_path: Path) -> None:
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
        amount="12.50",
        category=category.name,
        account=account.name,
        description="Lunch",
        account_id=account.id,
        category_id=category.id,
    )

    restarted = build(tmp_path)
    assert restarted.account_lookup(account.id) == account
    assert restarted.category_lookup(category.id) == category
    assert restarted.transaction_service.list_transactions() == [created]


def test_workspaces_are_isolated(tmp_path: Path) -> None:
    first = build(tmp_path / "first")
    second = build(tmp_path / "second")

    first.account_service.add_account("Cash")

    assert len(first.account_list()) == 1
    assert second.account_list() == []


def test_importing_main_uses_only_sqlite_composition() -> None:
    assert isinstance(
        main.APPLICATION.transaction_service._repository,
        SQLiteTransactionRepository,
    )
