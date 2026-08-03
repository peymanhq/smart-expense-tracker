"""Application service composition for one workspace and storage backend."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from account import Account
from account_repository import AccountRepository, JsonAccountRepository
from account_service import AccountService
from category import Category
from category_repository import CategoryRepository, JsonCategoryRepository
from category_service import CategoryService
from clock import TodayProvider, UtcNowProvider, local_today, utc_now
from excel_import_service import ExcelImportService
from sqlite_account_repository import SQLiteAccountRepository
from sqlite_category_repository import SQLiteCategoryRepository
from sqlite_database import SQLiteDatabase
from sqlite_migration import json_workspace_exists, migrate_json_to_sqlite
from sqlite_schema import initialize_schema
from sqlite_transaction_repository import SQLiteTransactionRepository
from transaction_repository import (
    JsonTransactionRepository,
    TransactionRepository,
)
from transaction_service import TransactionService

AccountList = Callable[[], list[Account]]
CategoryList = Callable[..., list[Category]]
AccountLookup = Callable[[str], Account | None]
CategoryLookup = Callable[[str], Category | None]
SUPPORTED_STORAGE_BACKENDS = frozenset({"json", "sqlite"})


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


def _workspace_data_path(
    workspace_root: Path | str | None,
    filename: str,
) -> Path:
    if workspace_root is None:
        return Path("data") / filename
    return Path(workspace_root) / "data" / filename


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


def build_json_application(
    workspace_root: Path | str | None = None,
    *,
    today_provider: TodayProvider = local_today,
    utc_now_provider: UtcNowProvider = utc_now,
) -> ApplicationServices:
    """Compose application services for the current JSON persistence backend."""
    account_repository = JsonAccountRepository(
        _workspace_data_path(workspace_root, "accounts.json"),
        _workspace_data_path(workspace_root, "accounts_state.json"),
    )
    category_repository = JsonCategoryRepository(
        _workspace_data_path(workspace_root, "categories.json"),
        _workspace_data_path(workspace_root, "categories_state.json"),
    )
    transaction_repository = JsonTransactionRepository(
        _workspace_data_path(workspace_root, "transactions.json")
    )

    return _compose_application(
        account_repository,
        category_repository,
        transaction_repository,
        today_provider=today_provider,
        utc_now_provider=utc_now_provider,
    )


def build_sqlite_application(
    workspace_root: Path | str | None = None,
    *,
    today_provider: TodayProvider = local_today,
    utc_now_provider: UtcNowProvider = utc_now,
    migrate_json: bool = False,
    auto_migrate_json: bool = True,
) -> ApplicationServices:
    """Compose SQLite services with guarded first-start JSON migration."""
    database = SQLiteDatabase.for_workspace(workspace_root)
    should_auto_migrate = (
        auto_migrate_json
        and not database.path.exists()
        and json_workspace_exists(workspace_root)
    )
    if migrate_json or should_auto_migrate:
        migrate_json_to_sqlite(workspace_root, database=database)
    else:
        initialize_schema(database)
    return _compose_application(
        SQLiteAccountRepository(database),
        SQLiteCategoryRepository(database),
        SQLiteTransactionRepository(database),
        today_provider=today_provider,
        utc_now_provider=utc_now_provider,
    )


def build_application(
    workspace_root: Path | str | None = None,
    *,
    backend: str = "sqlite",
    migrate_json: bool = False,
    auto_migrate_json: bool = True,
    today_provider: TodayProvider = local_today,
    utc_now_provider: UtcNowProvider = utc_now,
) -> ApplicationServices:
    """Compose one backend; SQLite is primary and JSON is compatibility."""
    if not isinstance(backend, str):
        raise ValueError("Storage backend must be json or sqlite.")
    normalized_backend = backend.strip().casefold()
    if normalized_backend not in SUPPORTED_STORAGE_BACKENDS:
        raise ValueError(
            f"Unsupported storage backend {backend!r}; choose json or sqlite."
        )
    if migrate_json and normalized_backend != "sqlite":
        raise ValueError("JSON migration is only valid with the sqlite backend.")
    builder = (
        build_json_application
        if normalized_backend == "json"
        else build_sqlite_application
    )
    options = {
        "today_provider": today_provider,
        "utc_now_provider": utc_now_provider,
    }
    if normalized_backend == "sqlite":
        options["migrate_json"] = migrate_json
        options["auto_migrate_json"] = auto_migrate_json
    return builder(workspace_root, **options)
