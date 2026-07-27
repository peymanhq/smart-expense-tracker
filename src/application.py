"""Application service composition for one JSON-backed workspace."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from account import Account
from account_repository import JsonAccountRepository
from account_service import AccountService
from category import Category
from category_repository import JsonCategoryRepository
from category_service import CategoryService
from clock import TodayProvider, UtcNowProvider, local_today, utc_now
from excel_import_service import ExcelImportService
from transaction_repository import JsonTransactionRepository
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


def _workspace_data_path(
    workspace_root: Path | str | None,
    filename: str,
) -> Path:
    if workspace_root is None:
        return Path("data") / filename
    return Path(workspace_root) / "data" / filename


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
