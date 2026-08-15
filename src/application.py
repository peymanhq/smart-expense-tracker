"""Application service composition for one SQLite workspace."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from account import Account
from account_repository import AccountRepository
from account_service import AccountService
from category import Category
from category_repository import CategoryRepository
from category_service import CategoryService
from clock import TodayProvider, UtcNowProvider, local_today, utc_now
from excel_import_service import ExcelImportService
from sqlite_account_repository import SQLiteAccountRepository
from sqlite_category_repository import SQLiteCategoryRepository
from sqlite_database import SQLiteDatabase
from sqlite_schema import initialize_schema
from sqlite_transaction_repository import SQLiteTransactionRepository
from transaction_repository import TransactionRepository
from transaction_service import TransactionService

AccountList = Callable[[], list[Account]]
CategoryList = Callable[..., list[Category]]
AccountLookup = Callable[[str], Account | None]
CategoryLookup = Callable[[str], Category | None]


@dataclass(frozen=True)
class ApplicationServices:
    """Services and managed-record dependencies for one application workspace."""

    transaction_service: TransactionService
    account_service: AccountService
    category_service: CategoryService
    excel_import_service: ExcelImportService
    today_provider: TodayProvider
    account_list: AccountList
    category_list: CategoryList
    active_account_list: AccountList
    active_category_list: CategoryList
    account_lookup: AccountLookup
    category_lookup: CategoryLookup
    account_display_lookup: AccountLookup
    category_display_lookup: CategoryLookup


def _compose_application(
    account_repository: AccountRepository,
    category_repository: CategoryRepository,
    transaction_repository: TransactionRepository,
    *,
    today_provider: TodayProvider,
    utc_now_provider: UtcNowProvider,
) -> ApplicationServices:
    """Wire backend-neutral repositories into the application services."""
    account_service = AccountService(account_repository)
    category_service = CategoryService(category_repository)
    account_list = account_service.list_accounts
    category_list = category_service.list_categories
    account_lookup = account_service.get_account_by_id
    category_lookup = category_service.get_category_by_id
    account_display_lookup = account_service.get_account_by_display_id
    category_display_lookup = category_service.get_category_by_display_id
    active_account_list = partial(account_list, active_only=True)
    active_category_list = partial(category_list, active_only=True)

    transaction_service = TransactionService(
        transaction_repository,
        today_provider=today_provider,
        utc_now_provider=utc_now_provider,
        account_lookup=account_lookup,
        category_lookup=category_lookup,
    )
    excel_import_service = ExcelImportService(
        transaction_service,
        account_list=account_list,
        category_list=category_list,
    )

    return ApplicationServices(
        transaction_service=transaction_service,
        account_service=account_service,
        category_service=category_service,
        excel_import_service=excel_import_service,
        today_provider=today_provider,
        account_list=account_list,
        category_list=category_list,
        active_account_list=active_account_list,
        active_category_list=active_category_list,
        account_lookup=account_lookup,
        category_lookup=category_lookup,
        account_display_lookup=account_display_lookup,
        category_display_lookup=category_display_lookup,
    )


def build_application(
    workspace_root: Path | str | None = None,
    *,
    today_provider: TodayProvider = local_today,
    utc_now_provider: UtcNowProvider = utc_now,
) -> ApplicationServices:
    """Compose all application services for one SQLite workspace."""
    database = SQLiteDatabase.for_workspace(workspace_root)
    initialize_schema(database)
    return compose_application(
        database,
        today_provider=today_provider,
        utc_now_provider=utc_now_provider,
    )


def compose_application(
    database: SQLiteDatabase,
    *,
    today_provider: TodayProvider = local_today,
    utc_now_provider: UtcNowProvider = utc_now,
) -> ApplicationServices:
    """Compose services around an initialized or deliberately lazy database."""
    return _compose_application(
        SQLiteAccountRepository(database),
        SQLiteCategoryRepository(database),
        SQLiteTransactionRepository(database),
        today_provider=today_provider,
        utc_now_provider=utc_now_provider,
    )


# Backward-compatible alias for integrations that used the explicit name.
build_sqlite_application = build_application
