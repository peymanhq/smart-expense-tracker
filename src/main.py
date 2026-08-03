"""Entry point for the Smart Expense Tracker application."""

from collections.abc import Callable
from datetime import date
import os
from pathlib import Path
from typing import TypeVar

from account import Account
from application import ApplicationServices, build_application
from category import Category
from clock import TodayProvider, local_today
from date_policy import ValidatedDateQuery
from excel_exporter import (
    ExcelExportError,
    export_transactions_to_excel,
    normalize_excel_destination,
)
from excel_import import ExcelImportError
from excel_import_service import (
    ExcelImportPreview,
    ExcelImportService,
)
from excel_template import generate_excel_import_template
from excel_workbook import ExcelWorkbookError
from formatter import format_transactions
from persistence_errors import StorageError
from report import (
    FinancialSummary,
    calculate_financial_summary,
    generate_daily_summary,
    generate_date_range_summary,
)
from search import (
    filter_transactions,
    find_transaction_by_display_id,
    search_transactions,
)
from transaction_service import (
    FutureTransactionDateError,
    TransactionActiveDateMismatchError,
    TransactionNotFoundError,
    TransactionService,
    TransactionServiceError,
)
from validators import validate_transaction_date, validate_transaction_type

TRANSACTION_TODAY_PROVIDER: TodayProvider = local_today
STORAGE_BACKEND_ENV = "SMART_EXPENSE_TRACKER_BACKEND"
MIGRATE_JSON_ENV = "SMART_EXPENSE_TRACKER_MIGRATE_JSON"
APPLICATION = build_application(
    today_provider=TRANSACTION_TODAY_PROVIDER,
)
ACTIVE_STORAGE_BACKEND = "json"
ACCOUNT_SERVICE = APPLICATION.account_service
CATEGORY_SERVICE = APPLICATION.category_service

# Bound application operations keep the CLI handlers simple and independently
# monkeypatchable while construction remains centralized in the factory.
activate_account = ACCOUNT_SERVICE.activate_account
add_account = ACCOUNT_SERVICE.add_account
deactivate_account = ACCOUNT_SERVICE.deactivate_account
get_account_by_display_id = APPLICATION.account_display_lookup
get_account_by_id = APPLICATION.account_lookup
list_accounts = APPLICATION.account_list
rename_account = ACCOUNT_SERVICE.rename_account
activate_category = CATEGORY_SERVICE.activate_category
add_category = CATEGORY_SERVICE.add_category
deactivate_category = CATEGORY_SERVICE.deactivate_category
get_category_by_display_id = APPLICATION.category_display_lookup
get_category_by_id = APPLICATION.category_lookup
list_categories = APPLICATION.category_list
rename_category = CATEGORY_SERVICE.rename_category

TRANSACTION_SERVICE = APPLICATION.transaction_service
TRANSACTION_ACTIVE_ACCOUNT_LIST = APPLICATION.active_account_list
TRANSACTION_ACCOUNT_DISPLAY_LOOKUP = get_account_by_display_id
TRANSACTION_ACTIVE_CATEGORY_LIST = APPLICATION.active_category_list
TRANSACTION_CATEGORY_DISPLAY_LOOKUP = get_category_by_display_id
EXCEL_IMPORT_SERVICE = APPLICATION.excel_import_service


def _bind_application(
    application: ApplicationServices,
    backend: str,
) -> None:
    """Replace CLI bindings after an explicit runtime backend selection."""
    global APPLICATION, ACTIVE_STORAGE_BACKEND
    global ACCOUNT_SERVICE, CATEGORY_SERVICE, TRANSACTION_SERVICE
    global EXCEL_IMPORT_SERVICE
    global TRANSACTION_ACTIVE_ACCOUNT_LIST, TRANSACTION_ACCOUNT_DISPLAY_LOOKUP
    global TRANSACTION_ACTIVE_CATEGORY_LIST, TRANSACTION_CATEGORY_DISPLAY_LOOKUP
    global activate_account, add_account, deactivate_account
    global get_account_by_display_id, get_account_by_id, list_accounts
    global rename_account
    global activate_category, add_category, deactivate_category
    global get_category_by_display_id, get_category_by_id, list_categories
    global rename_category

    APPLICATION = application
    ACTIVE_STORAGE_BACKEND = backend
    ACCOUNT_SERVICE = application.account_service
    CATEGORY_SERVICE = application.category_service
    TRANSACTION_SERVICE = application.transaction_service
    EXCEL_IMPORT_SERVICE = application.excel_import_service
    activate_account = ACCOUNT_SERVICE.activate_account
    add_account = ACCOUNT_SERVICE.add_account
    deactivate_account = ACCOUNT_SERVICE.deactivate_account
    get_account_by_display_id = application.account_display_lookup
    get_account_by_id = application.account_lookup
    list_accounts = application.account_list
    rename_account = ACCOUNT_SERVICE.rename_account
    activate_category = CATEGORY_SERVICE.activate_category
    add_category = CATEGORY_SERVICE.add_category
    deactivate_category = CATEGORY_SERVICE.deactivate_category
    get_category_by_display_id = application.category_display_lookup
    get_category_by_id = application.category_lookup
    list_categories = application.category_list
    rename_category = CATEGORY_SERVICE.rename_category
    TRANSACTION_ACTIVE_ACCOUNT_LIST = application.active_account_list
    TRANSACTION_ACCOUNT_DISPLAY_LOOKUP = get_account_by_display_id
    TRANSACTION_ACTIVE_CATEGORY_LIST = application.active_category_list
    TRANSACTION_CATEGORY_DISPLAY_LOOKUP = get_category_by_display_id


def _environment_flag(name: str) -> bool:
    value = os.environ.get(name, "0").strip().casefold()
    if value in {"0", "false", "no", "off", ""}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    raise ValueError(f"{name} must be a true/false value.")


def configure_storage_from_environment() -> None:
    """Apply the opt-in backend selection without import-time disk access."""
    requested_backend = os.environ.get(STORAGE_BACKEND_ENV, "json")
    normalized_backend = requested_backend.strip().casefold()
    migrate_json = _environment_flag(MIGRATE_JSON_ENV)
    if normalized_backend == ACTIVE_STORAGE_BACKEND and not migrate_json:
        return
    application = build_application(
        backend=requested_backend,
        migrate_json=migrate_json,
        today_provider=TRANSACTION_TODAY_PROVIDER,
    )
    _bind_application(application, normalized_backend)

ManagedRecord = TypeVar("ManagedRecord", Account, Category)
AccountList = Callable[[], list[Account]]
CategoryList = Callable[..., list[Category]]
AccountDisplayLookup = Callable[[str], Account | None]
CategoryDisplayLookup = Callable[[str], Category | None]
ExcelExporter = Callable[..., Path]
ExcelTemplateGenerator = Callable[..., Path]

"""==============Handles Fanection================"""


def _print_transaction_error(error: Exception) -> None:
    if isinstance(error, StorageError):
        print(f"Storage error: {error}")
    else:
        print(f"Error: {error}")


def _choose_transaction_type() -> str | None:
    print("\nTransaction type:")
    print("1. Income")
    print("2. Expense")
    transaction_type = {
        "1": "income",
        "2": "expense",
    }.get(input("Choose transaction type: ").strip())
    if transaction_type is None:
        print("Invalid transaction type choice.")
    return transaction_type


def _select_by_display_id(
    candidates: list[ManagedRecord],
    *,
    heading: str,
    prompt: str,
    invalid_message: str,
    display_lookup: Callable[[str], ManagedRecord | None],
    allow_empty: bool = False,
) -> ManagedRecord | None:
    """Display candidates and resolve one using the public normalization rule."""
    available = list(candidates)
    print(f"\n{heading}")
    for candidate in available:
        print(f"{candidate.display_id} - {candidate.name}")

    candidate_ids = {candidate.id for candidate in available}
    while True:
        display_id = input(prompt)
        if allow_empty and not display_id.strip():
            return None
        selected = display_lookup(display_id)
        if selected is not None and selected.id in candidate_ids:
            return selected
        print(invalid_message)


def select_active_account(
    candidates: list[Account],
    *,
    display_lookup: AccountDisplayLookup,
    allow_empty: bool = False,
) -> Account | None:
    """Select an active Account without mutating the supplied candidates."""
    active_accounts = [
        account for account in candidates if account.is_active
    ]
    return _select_by_display_id(
        active_accounts,
        heading="Available accounts:",
        prompt=(
            "Enter a new account display ID, or press Enter to keep unchanged: "
            if allow_empty
            else "Select account ID: "
        ),
        invalid_message="Invalid or unavailable account display ID.",
        display_lookup=display_lookup,
        allow_empty=allow_empty,
    )


def select_active_category(
    transaction_type: str,
    candidates: list[Category],
    *,
    display_lookup: CategoryDisplayLookup,
    allow_empty: bool = False,
) -> Category | None:
    """Select an active Category compatible with the requested type."""
    active_categories = [
        category
        for category in candidates
        if category.is_active
        and category.transaction_type == transaction_type
    ]
    return _select_by_display_id(
        active_categories,
        heading=f"Available {transaction_type} categories:",
        prompt=(
            "Enter a new category display ID, or press Enter to keep unchanged: "
            if allow_empty
            else "Select category ID: "
        ),
        invalid_message="Invalid or unavailable category display ID.",
        display_lookup=display_lookup,
        allow_empty=allow_empty,
    )


def _selected_transaction_service(
    service: TransactionService | None,
) -> TransactionService:
    return TRANSACTION_SERVICE if service is None else service


def _prompt_date_filter(
    service: TransactionService,
) -> tuple[bool, ValidatedDateQuery | None]:
    """Prompt for an independent search/report date without changing workspace."""
    print("\nDate filter:")
    print("1. No date filter")
    print("2. Exact date")
    print("3. Date range")
    print("0. Cancel")
    choice = input("Choose date filter: ").strip()

    if choice == "0" or not choice:
        print("Search cancelled.")
        return False, None
    if choice == "1":
        return True, service.validate_date_query()

    try:
        if choice == "2":
            value = input("Enter transaction date (YYYY-MM-DD): ").strip()
            if not value:
                print("Search cancelled.")
                return False, None
            transaction_date = validate_transaction_date(value)
            return True, service.validate_date_query(
                transaction_date=transaction_date,
            )

        if choice == "3":
            start_value = input("Start date (YYYY-MM-DD): ").strip()
            if not start_value:
                print("Search cancelled.")
                return False, None
            end_value = input("End date (YYYY-MM-DD): ").strip()
            if not end_value:
                print("Search cancelled.")
                return False, None
            start_date = validate_transaction_date(start_value)
            end_date = validate_transaction_date(end_value)
            return True, service.validate_date_query(
                start_date=start_date,
                end_date=end_date,
            )
    except (ValueError, FutureTransactionDateError) as error:
        _print_transaction_error(error)
        return False, None

    print("Invalid date filter choice.")
    return False, None


def handle_add_transaction(
    service: TransactionService,
    active_date: date,
    *,
    account_list: AccountList | None = None,
    account_display_lookup: AccountDisplayLookup | None = None,
    category_list: CategoryList | None = None,
    category_display_lookup: CategoryDisplayLookup | None = None,
) -> None:
    account_list = (
        TRANSACTION_ACTIVE_ACCOUNT_LIST
        if account_list is None
        else account_list
    )
    account_display_lookup = (
        TRANSACTION_ACCOUNT_DISPLAY_LOOKUP
        if account_display_lookup is None
        else account_display_lookup
    )
    category_list = (
        TRANSACTION_ACTIVE_CATEGORY_LIST
        if category_list is None
        else category_list
    )
    category_display_lookup = (
        TRANSACTION_CATEGORY_DISPLAY_LOOKUP
        if category_display_lookup is None
        else category_display_lookup
    )

    print(f"Active transaction date: {active_date.isoformat()}")
    transaction_type = _choose_transaction_type()
    if transaction_type is None:
        return

    try:
        amount = input("Amount: ")
        accounts = [
            account for account in account_list() if account.is_active
        ]
        if not accounts:
            print("No active accounts are available. Transaction not added.")
            return
        selected_account = select_active_account(
            accounts,
            display_lookup=account_display_lookup,
        )
        assert selected_account is not None

        categories = [
            category
            for category in category_list(transaction_type=transaction_type)
            if category.is_active
            and category.transaction_type == transaction_type
        ]
        if not categories:
            print(
                f"No active {transaction_type} categories are available. "
                "Transaction not added."
            )
            return
        selected_category = select_active_category(
            transaction_type,
            categories,
            display_lookup=category_display_lookup,
        )
        assert selected_category is not None

        description = input("Description: ")

        transaction = service.add_transaction(
            transaction_date=active_date,
            transaction_type=transaction_type,
            amount=amount,
            category=selected_category.name,
            account=selected_account.name,
            description=description,
            account_id=selected_account.id,
            category_id=selected_category.id,
        )

        print(
            f"Transaction {transaction.display_id} added for "
            f"{transaction.transaction_date.isoformat()}."
        )
    except (ValueError, StorageError) as error:
        _print_transaction_error(error)


def _print_financial_summary(summary: FinancialSummary) -> None:
    print(f"Total Income : {summary.total_income:.2f}")
    print(f"Total Expense: {summary.total_expense:.2f}")
    print(f"Balance      : {summary.balance:.2f}")
    print(f"Transaction Count: {summary.transaction_count}")


def handle_view_balance(
    service: TransactionService | None = None,
) -> None:
    service = _selected_transaction_service(service)
    summary = calculate_financial_summary(service.list_transactions())

    print("\n--- Financial Summary ---")
    _print_financial_summary(summary)


def handle_daily_report(
    service: TransactionService | None = None,
) -> None:
    service = _selected_transaction_service(service)
    value = input("Enter transaction date (YYYY-MM-DD): ").strip()
    if not value:
        print("Report cancelled.")
        return

    try:
        transaction_date = validate_transaction_date(value)
        dates = service.validate_date_query(
            transaction_date=transaction_date,
        )
    except (ValueError, FutureTransactionDateError) as error:
        _print_transaction_error(error)
        return

    summary = generate_daily_summary(
        service.list_transactions(),
        dates.transaction_date,
    )
    print(
        f"\nFinancial report for "
        f"{dates.transaction_date.isoformat()}"
    )
    _print_financial_summary(summary)


def handle_date_range_report(
    service: TransactionService | None = None,
) -> None:
    service = _selected_transaction_service(service)
    start_value = input("Start date (YYYY-MM-DD): ").strip()
    if not start_value:
        print("Report cancelled.")
        return
    end_value = input("End date (YYYY-MM-DD): ").strip()
    if not end_value:
        print("Report cancelled.")
        return

    try:
        start_date = validate_transaction_date(start_value)
        end_date = validate_transaction_date(end_value)
        dates = service.validate_date_query(
            start_date=start_date,
            end_date=end_date,
        )
    except (ValueError, FutureTransactionDateError) as error:
        _print_transaction_error(error)
        return

    summary = generate_date_range_summary(
        service.list_transactions(),
        dates.start_date,
        dates.end_date,
    )
    print(
        f"\nFinancial report from {dates.start_date.isoformat()} "
        f"to {dates.end_date.isoformat()}"
    )
    _print_financial_summary(summary)


def financial_report_menu(
    service: TransactionService | None = None,
) -> None:
    service = _selected_transaction_service(service)
    print("\n=== Financial Reports ===")
    print("1. All-time report")
    print("2. Daily report")
    print("3. Date-range report")
    print("0. Back")
    choice = input("Choose report: ").strip()
    if choice == "1":
        handle_view_balance(service)
    elif choice == "2":
        handle_daily_report(service)
    elif choice == "3":
        handle_date_range_report(service)
    elif choice != "0":
        print("Invalid report choice.")


def handle_excel_export(
    service: TransactionService | None = None,
    *,
    today_provider: TodayProvider | None = None,
    account_list: AccountList | None = None,
    category_list: CategoryList | None = None,
    exporter: ExcelExporter = export_transactions_to_excel,
) -> None:
    """Gather report data and coordinate one safe Excel export."""
    service = _selected_transaction_service(service)
    today_provider = (
        TRANSACTION_TODAY_PROVIDER
        if today_provider is None
        else today_provider
    )
    account_list = list_accounts if account_list is None else account_list
    category_list = list_categories if category_list is None else category_list
    default_destination = Path("exports") / (
        f"smart_expense_tracker_{today_provider().isoformat()}.xlsx"
    )
    entered_destination = input(
        f"Destination [{default_destination}]: "
    ).strip()

    try:
        destination = normalize_excel_destination(
            entered_destination or default_destination
        )
        overwrite = False
        if destination.exists():
            confirmation = input(
                f"{destination} already exists. Overwrite? (y/N): "
            ).strip().casefold()
            if confirmation not in {"y", "yes"}:
                print("Excel export cancelled.")
                return
            overwrite = True

        transactions = service.list_transactions()
        accounts = account_list()
        categories = category_list()
        result = exporter(
            transactions,
            destination,
            account_names={account.id: account.name for account in accounts},
            category_names={
                category.id: category.name for category in categories
            },
            overwrite=overwrite,
        )
    except (ExcelExportError, StorageError, OSError) as error:
        print(f"Excel export error: {error}")
        return

    print(f"Excel workbook exported to {result.resolve()}")


def _print_excel_import_issues(preview: ExcelImportPreview) -> None:
    print("\nExcel import validation failed.")
    print(f"File: {preview.source_path}")
    print(f"Invalid rows: {preview.invalid_row_count}")
    print(f"Duplicate conflicts: {preview.duplicate_conflict_count}")
    print("Issues:")
    for issue in preview.issues:
        print(f"- Row {issue.row_number}: {issue.message}")
    print("No transactions were imported.")


def _print_excel_import_preview(preview: ExcelImportPreview) -> None:
    print("\n=== Excel Import Preview ===")
    print(f"File: {preview.source_path}")
    print(f"Valid transactions: {preview.valid_candidate_count}")
    print(f"Income transactions: {preview.income_transaction_count}")
    print(f"Expense transactions: {preview.expense_transaction_count}")
    print(f"Total income: {preview.total_income:.2f}")
    print(f"Total expense: {preview.total_expense:.2f}")
    print(f"Net balance impact: {preview.net_balance_impact:.2f}")


def handle_excel_import(
    import_service: ExcelImportService | None = None,
) -> None:
    """Coordinate validation, preview, confirmation, and one atomic import."""
    import_service = (
        EXCEL_IMPORT_SERVICE if import_service is None else import_service
    )
    source = input("Excel file to import (.xlsx): ").strip()
    if not source:
        print("Excel import cancelled.")
        return

    try:
        preview = import_service.analyze(source)
    except (ExcelImportError, StorageError) as error:
        print(f"Excel import error: {error}")
        return

    if not preview.is_valid:
        _print_excel_import_issues(preview)
        return
    if preview.valid_candidate_count == 0:
        print("No transaction rows were found. Nothing was imported.")
        return

    _print_excel_import_preview(preview)
    confirmation = input(
        "Import all previewed transactions? (y/N): "
    ).strip().casefold()
    if confirmation not in {"y", "yes"}:
        print("Excel import cancelled. No transactions were imported.")
        return

    try:
        result = import_service.persist(preview)
    except (
        ExcelImportError,
        StorageError,
        TransactionServiceError,
    ) as error:
        print(f"Excel import error: {error}")
        return
    print(
        f"Imported {result.imported_count} transaction(s) atomically. "
        f"Net balance impact: {result.net_balance_impact:.2f}"
    )


def handle_excel_import_template(
    *,
    today_provider: TodayProvider | None = None,
    account_list: AccountList | None = None,
    category_list: CategoryList | None = None,
    generator: ExcelTemplateGenerator = generate_excel_import_template,
) -> None:
    """Coordinate one safe, workspace-aware Excel template generation."""
    today_provider = (
        TRANSACTION_TODAY_PROVIDER
        if today_provider is None
        else today_provider
    )
    account_list = list_accounts if account_list is None else account_list
    category_list = list_categories if category_list is None else category_list
    default_destination = Path("exports") / (
        "smart_expense_tracker_import_template_"
        f"{today_provider().isoformat()}.xlsx"
    )
    entered_destination = input(
        f"Template destination [{default_destination}]: "
    ).strip()

    try:
        destination = normalize_excel_destination(
            entered_destination or default_destination
        )
        overwrite = False
        if destination.exists():
            confirmation = input(
                f"{destination} already exists. Overwrite? (y/N): "
            ).strip().casefold()
            if confirmation not in {"y", "yes"}:
                print("Excel template generation cancelled.")
                return
            overwrite = True
        result = generator(
            account_list(),
            category_list(),
            destination,
            overwrite=overwrite,
        )
    except (ExcelWorkbookError, StorageError) as error:
        print(f"Excel template error: {error}")
        return
    print(f"Excel import template created at {result.resolve()}")


def handle_view_transactions(
    service: TransactionService,
    active_date: date,
) -> None:
    try:
        transactions = service.list_transactions_by_date(active_date)
    except (ValueError, StorageError) as error:
        _print_transaction_error(error)
        return

    if not transactions:
        print(f"No transactions found for {active_date.isoformat()}.")
        return

    print(f"\nTransactions for {active_date.isoformat()}")
    print(format_transactions(transactions))


def handle_filter_transactions(
    service: TransactionService | None = None,
) -> None:
    service = _selected_transaction_service(service)

    transaction_type = input(
        "Transaction type (income/expense, leave blank for all): "
    ).strip()
    transaction_type = transaction_type or None

    category = input("Category (leave blank for all): ").strip()
    category = category or None

    account = input("Account (leave blank for all): ").strip()
    account = account or None

    description = input(
        "Description text (leave blank for all): "
    ).strip()
    description = description or None

    accepted, dates = _prompt_date_filter(service)
    if not accepted or dates is None:
        return

    results = filter_transactions(
        service.list_transactions(),
        transaction_type=transaction_type,
        category=category,
        account=account,
        description=description,
        transaction_date=dates.transaction_date,
        start_date=dates.start_date,
        end_date=dates.end_date,
    )

    print("\n=== Filtered Transactions ===")
    print(format_transactions(results))


def prompt_transaction_date(current_date: date) -> date | None:
    """Prompt until an optional replacement transaction date is valid."""
    print(f"Current transaction date: {current_date.isoformat()}")
    while True:
        date_input = input(
            "Enter new date, or press Enter to keep unchanged: "
        ).strip()
        if not date_input:
            return None
        try:
            return validate_transaction_date(date_input)
        except ValueError as error:
            _print_transaction_error(error)


def handle_update_transaction(
    service: TransactionService,
    active_date: date,
    *,
    account_list: AccountList | None = None,
    account_display_lookup: AccountDisplayLookup | None = None,
    category_list: CategoryList | None = None,
    category_display_lookup: CategoryDisplayLookup | None = None,
) -> None:
    account_list = (
        TRANSACTION_ACTIVE_ACCOUNT_LIST
        if account_list is None
        else account_list
    )
    account_display_lookup = (
        TRANSACTION_ACCOUNT_DISPLAY_LOOKUP
        if account_display_lookup is None
        else account_display_lookup
    )
    category_list = (
        TRANSACTION_ACTIVE_CATEGORY_LIST
        if category_list is None
        else category_list
    )
    category_display_lookup = (
        TRANSACTION_CATEGORY_DISPLAY_LOOKUP
        if category_display_lookup is None
        else category_display_lookup
    )

    handle_view_transactions(service, active_date)
    display_id = input("Transaction ID: ").strip().upper()
    if not display_id:
        print("Error: Transaction ID cannot be empty.")
        return

    try:
        existing = find_transaction_by_display_id(
            service.list_transactions(),
            display_id,
        )
        if existing is None:
            raise TransactionNotFoundError(display_id)

        amount_input = input(
            "New amount [press Enter to keep current]: "
        ).strip()
        description_input = input(
            "New description [press Enter to keep current]: "
        ).strip()
        type_input = input(
            "New type (income/expense) [press Enter to keep current]: "
        ).strip()
        resulting_type = (
            existing.type
            if not type_input
            else validate_transaction_type(type_input)
        )

        print(f"Current account: {existing.account}")
        accounts = [
            account for account in account_list() if account.is_active
        ]
        selected_account = None
        if accounts:
            selected_account = select_active_account(
                accounts,
                display_lookup=account_display_lookup,
                allow_empty=True,
            )
        else:
            print(
                "No active replacement accounts are available. "
                "Current account will remain unchanged."
            )

        print(f"Current category: {existing.category}")
        categories = [
            category
            for category in category_list(transaction_type=resulting_type)
            if category.is_active
            and category.transaction_type == resulting_type
        ]
        selected_category = None
        if categories:
            selected_category = select_active_category(
                resulting_type,
                categories,
                display_lookup=category_display_lookup,
                allow_empty=True,
            )
        else:
            print(
                f"No active {resulting_type} replacement categories are "
                "available. Current category will remain unchanged."
            )

        new_date = prompt_transaction_date(existing.transaction_date)
        updates = {}
        if type_input:
            updates["transaction_type"] = resulting_type
        if amount_input:
            updates["amount"] = amount_input
        if selected_category is not None:
            updates["category_id"] = selected_category.id
        if selected_account is not None:
            updates["account_id"] = selected_account.id
        if description_input:
            updates["description"] = description_input
        if new_date is not None:
            updates["transaction_date"] = new_date

        updated = service.update_transaction(
            display_id,
            active_date=active_date,
            **updates,
        )
    except (
        ValueError,
        StorageError,
        TransactionNotFoundError,
        TransactionActiveDateMismatchError,
    ) as error:
        _print_transaction_error(error)
        return

    if updated.transaction_date != active_date:
        print(
            f"Transaction {updated.display_id} updated and moved from "
            f"{active_date.isoformat()} to "
            f"{updated.transaction_date.isoformat()}."
        )
    else:
        print(f"Transaction {updated.display_id} updated.")


def handle_delete_transaction(
    service: TransactionService,
    active_date: date,
) -> None:
    handle_view_transactions(service, active_date)
    display_id = input("Enter transaction ID: ").strip().upper()
    if not display_id:
        print("Error: Transaction ID cannot be empty.")
        return
    confirmation = input(
        f"Delete transaction {display_id}? (y/N): "
    ).strip().casefold()
    if confirmation not in {"y", "yes"}:
        print("Deletion cancelled.")
        return

    try:
        deleted = service.delete_transaction(
            display_id,
            active_date=active_date,
        )
    except (
        ValueError,
        StorageError,
        TransactionNotFoundError,
        TransactionActiveDateMismatchError,
    ) as error:
        _print_transaction_error(error)
        return

    print(
        f"Transaction {deleted.display_id} deleted from "
        f"{deleted.transaction_date.isoformat()}."
    )


def handle_change_active_date(
    service: TransactionService,
    active_date: date,
) -> date:
    date_input = input("Enter transaction date (YYYY-MM-DD): ").strip()
    if not date_input:
        print("Active date unchanged.")
        return active_date

    try:
        requested_date = validate_transaction_date(date_input)
        accepted_date = service.validate_transaction_date(requested_date)
    except (ValueError, FutureTransactionDateError) as error:
        _print_transaction_error(error)
        return active_date

    print(f"Active date changed to {accepted_date.isoformat()}.")
    return accepted_date


def handle_browse_transaction_dates(
    service: TransactionService,
    active_date: date,
) -> date:
    try:
        summaries = service.list_transaction_date_summaries()
    except StorageError as error:
        _print_transaction_error(error)
        return active_date

    if not summaries:
        print("No transaction dates found.")
        return active_date

    print("\nDates with transactions")
    for index, summary in enumerate(summaries, start=1):
        label = (
            "transaction"
            if summary.transaction_count == 1
            else "transactions"
        )
        print(
            f"{index}. {summary.transaction_date.isoformat()} — "
            f"{summary.transaction_count} {label}"
        )
    print("0. Cancel")

    selection = input("Choose a date: ").strip()
    if selection == "0" or not selection:
        print("Active date unchanged.")
        return active_date
    try:
        selected_index = int(selection)
    except ValueError:
        print("Invalid date selection.")
        return active_date
    if not 1 <= selected_index <= len(summaries):
        print("Invalid date selection.")
        return active_date

    try:
        selected_date = service.validate_transaction_date(
            summaries[selected_index - 1].transaction_date
        )
    except FutureTransactionDateError as error:
        _print_transaction_error(error)
        return active_date
    print(f"Active date changed to {selected_date.isoformat()}.")
    return selected_date


def pause_transaction_management() -> None:
    input("\nPress Enter to return to Transaction Management...")


def transaction_management_menu(
    service: TransactionService | None = None,
    today_provider: TodayProvider | None = None,
) -> None:
    service = TRANSACTION_SERVICE if service is None else service
    today_provider = (
        TRANSACTION_TODAY_PROVIDER
        if today_provider is None
        else today_provider
    )
    active_date = service.validate_transaction_date(today_provider())

    while True:
        print("\n=== Transaction Management ===")
        print(f"Active date: {active_date.isoformat()}")
        print("1. Add transaction")
        print("2. View transactions")
        print("3. Update transaction")
        print("4. Delete transaction")
        print("5. Change active date")
        print("6. Browse transaction dates")
        print("7. Return to today")
        print("0. Back")

        choice = input("\n===>Choose an option: ").strip()
        if choice == "0":
            return

        if choice == "1":
            handle_add_transaction(service, active_date)
        elif choice == "2":
            handle_view_transactions(service, active_date)
        elif choice == "3":
            handle_update_transaction(service, active_date)
        elif choice == "4":
            handle_delete_transaction(service, active_date)
        elif choice == "5":
            active_date = handle_change_active_date(service, active_date)
        elif choice == "6":
            active_date = handle_browse_transaction_dates(
                service,
                active_date,
            )
        elif choice == "7":
            try:
                active_date = service.validate_transaction_date(
                    today_provider()
                )
                print(
                    f"Active date reset to {active_date.isoformat()}."
                )
            except ValueError as error:
                _print_transaction_error(error)
        else:
            print("Invalid choice. Please try again.")
            continue

        pause_transaction_management()


def handle_search(
    service: TransactionService | None = None,
) -> None:
    service = _selected_transaction_service(service)
    search_key = input("Enter search term: ")
    accepted, dates = _prompt_date_filter(service)
    if not accepted or dates is None:
        return

    results = search_transactions(
        transactions=service.list_transactions(),
        search_key=search_key,
        transaction_date=dates.transaction_date,
        start_date=dates.start_date,
        end_date=dates.end_date,
    )

    if not results:
        print("No matching transactions found.")
        return

    print(f"\n===Found {len(results)} matching transaction(s)===\n")
    print(format_transactions(results))


def handle_add_account() -> None:
    result = add_account(input("Account name: "))
    print(result.message)


def handle_view_accounts() -> None:
    accounts = list_accounts()
    if not accounts:
        print("No accounts found.")
        return

    for account in accounts:
        status = "Active" if account.is_active else "Inactive"
        print(f"{account.display_id} | {account.name} | {status}")


def handle_rename_account() -> None:
    display_id = input("Account display ID: ")
    new_name = input("New account name: ")
    result = rename_account(display_id, new_name)
    print(result.message)


def handle_deactivate_account() -> None:
    display_id = input("Account display ID: ")
    result = deactivate_account(display_id)
    print(result.message)


def handle_activate_account() -> None:
    display_id = input("Account display ID: ")
    result = activate_account(display_id)
    print(result.message)


def pause_account_management() -> None:
    input("\nPress Enter to return to Account Management...")


def account_management_menu() -> None:
    actions = {
        "1": handle_add_account,
        "2": handle_view_accounts,
        "3": handle_rename_account,
        "4": handle_deactivate_account,
        "5": handle_activate_account,
    }

    while True:
        print("\n=== Account Management ===")
        print("1. Add account")
        print("2. View accounts")
        print("3. Rename account")
        print("4. Deactivate account")
        print("5. Activate account")
        print("6. Back")

        choice = input("\n===>Choose an option: ")
        if choice == "6":
            return

        action = actions.get(choice)
        if action is None:
            print("Invalid choice. Please try again.")
            continue

        try:
            action()
        except StorageError as error:
            print(f"Storage error: {error}")
        pause_account_management()


def handle_add_category() -> None:
    print("\nTransaction type:")
    print("1. Income")
    print("2. Expense")
    transaction_types = {"1": "income", "2": "expense"}
    transaction_type = transaction_types.get(input("Choose transaction type: "))
    if transaction_type is None:
        print("Invalid transaction type choice.")
        return

    result = add_category(input("Category name: "), transaction_type)
    print(result.message)


def handle_view_categories() -> None:
    categories = list_categories()
    if not categories:
        print("No categories found.")
        return

    for category in categories:
        status = "Active" if category.is_active else "Inactive"
        print(
            f"{category.display_id} | {category.name} | "
            f"{category.transaction_type.title()} | {status}"
        )


def handle_rename_category() -> None:
    display_id = input("Category display ID: ")
    new_name = input("New category name: ")
    result = rename_category(display_id, new_name)
    print(result.message)


def handle_activate_category() -> None:
    display_id = input("Category display ID: ")
    result = activate_category(display_id)
    print(result.message)


def handle_deactivate_category() -> None:
    display_id = input("Category display ID: ")
    result = deactivate_category(display_id)
    print(result.message)


def pause_category_management() -> None:
    input("\nPress Enter to return to Category Management...")


def category_management_menu() -> None:
    actions = {
        "1": handle_add_category,
        "2": handle_view_categories,
        "3": handle_rename_category,
        "4": handle_activate_category,
        "5": handle_deactivate_category,
    }

    while True:
        print("\n=== Category Management ===")
        print("1. Add category")
        print("2. View categories")
        print("3. Rename category")
        print("4. Activate category")
        print("5. Deactivate category")
        print("6. Back")

        choice = input("\n===>Choose an option: ")
        if choice == "6":
            return

        action = actions.get(choice)
        if action is None:
            print("Invalid choice. Please try again.")
            continue

        try:
            action()
        except StorageError as error:
            print(f"Storage error: {error}")
        pause_category_management()


"""=================Menu dic========================"""
MENU_ACTIONS = {
    "1": transaction_management_menu,
    "2": financial_report_menu,
    "3": handle_filter_transactions,
    "4": handle_search,
    "5": account_management_menu,
    "6": category_management_menu,
    "7": handle_excel_export,
    "8": handle_excel_import,
    "9": handle_excel_import_template,
}

"""=================Main fanection=================="""


def pause() -> None:
    input("\nPress Enter to return to the main menu...")


def main() -> None:
    try:
        configure_storage_from_environment()
    except (StorageError, ValueError) as error:
        print(f"Storage configuration error: {error}")
        return
    print(f"Storage backend: {ACTIVE_STORAGE_BACKEND.upper()}")

    while True:
        print("\n\n=== Smart Expense Tracker ===")
        print("1. Transaction Management")
        print("2. Financial Reports")
        print("3. Filter Transactions")
        print("4. Search")
        print("5. Account Management")
        print("6. Category Management")
        print("7. Export transactions to Excel")
        print("8. Import transactions from Excel")
        print("9. Generate Excel import template")
        print("0. Exit")

        choice = input("\n===>Choose an option: ")

        if choice == "0":
            print("See you later !")
            break

        action = MENU_ACTIONS.get(choice)
        if action:
            try:
                action()
            except StorageError as error:
                print(f"Storage error: {error}")
            pause()
        else:
            print("Invalid choice, Please try again.")


"""=================Program Runner=================="""
if __name__ == "__main__":
    main()
