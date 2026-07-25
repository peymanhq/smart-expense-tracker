"""Entry point for the Smart Expense Tracker application."""

from datetime import date

from account_service import (
    activate_account,
    add_account,
    deactivate_account,
    rename_account,
)
from account_storage import load_accounts
from category_service import (
    activate_category,
    add_category,
    deactivate_category,
    list_categories,
    rename_category,
)
from clock import TodayProvider, local_today
from date_policy import ValidatedDateQuery
from formatter import format_transactions
from json_storage import StorageError
from report import (
    FinancialSummary,
    calculate_financial_summary,
    generate_daily_summary,
    generate_date_range_summary,
)
from search import filter_transactions, search_transactions
from transaction_repository import JsonTransactionRepository
from transaction_service import (
    FutureTransactionDateError,
    TransactionActiveDateMismatchError,
    TransactionNotFoundError,
    TransactionService,
)
from validators import validate_transaction_date

TRANSACTION_TODAY_PROVIDER: TodayProvider = local_today
TRANSACTION_REPOSITORY = JsonTransactionRepository()
TRANSACTION_SERVICE = TransactionService(
    TRANSACTION_REPOSITORY,
    today_provider=TRANSACTION_TODAY_PROVIDER,
)

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
) -> None:
    print(f"Active transaction date: {active_date.isoformat()}")
    transaction_type = _choose_transaction_type()
    if transaction_type is None:
        return

    try:
        amount = input("Amount: ")
        category = input("Category: ")
        account = input("Account: ")
        description = input("Description: ")

        transaction = service.add_transaction(
            transaction_date=active_date,
            transaction_type=transaction_type,
            amount=amount,
            category=category,
            account=account,
            description=description,
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


def handle_update_transaction(
    service: TransactionService,
    active_date: date,
) -> None:
    handle_view_transactions(service, active_date)
    display_id = input("Transaction ID: ").strip().upper()
    if not display_id:
        print("Error: Transaction ID cannot be empty.")
        return

    amount_input = input("New amount [press Enter to keep current]: ").strip()
    description_input = input(
        "New description [press Enter to keep current]: "
    ).strip()
    type_input = input(
        "New type (income/expense) [press Enter to keep current]: "
    ).strip()
    category_input = input(
        "New category [press Enter to keep current]: "
    ).strip()
    account_input = input(
        "New account [press Enter to keep current]: "
    ).strip()
    print(f"Current transaction date: {active_date.isoformat()}")
    date_input = input(
        "New transaction date [press Enter to keep current]: "
    ).strip()

    try:
        new_date = (
            validate_transaction_date(date_input) if date_input else None
        )
        updates = {}
        if type_input:
            updates["transaction_type"] = type_input
        if amount_input:
            updates["amount"] = amount_input
        if category_input:
            updates["category"] = category_input
        if account_input:
            updates["account"] = account_input
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
    accounts = load_accounts()
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
}

"""=================Main fanection=================="""


def pause() -> None:
    input("\nPress Enter to return to the main menu...")


def main() -> None:

    while True:
        print("\n\n=== Smart Expense Tracker ===")
        print("1. Transaction Management")
        print("2. Financial Reports")
        print("3. Filter Transactions")
        print("4. Search")
        print("5. Account Management")
        print("6. Category Management")
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
