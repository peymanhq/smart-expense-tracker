"""Entry point for the Smart Expense Tracker application."""

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
from formatter import format_transactions
from report import calculate_summary, filter_transactions
from search import find_transaction_by_display_id, search_transactions
from storage import (
    StorageError,
    delete_transaction,
    get_next_display_id,
    load_transactions,
    save_transaction,
    update_transaction,
)
from transaction_factory import create_transaction
from validators import validate_date

"""==============Handles Fanection================"""


def handle_add_transaction(transaction_type: str) -> None:
    try:
        display_id = get_next_display_id()
        amount = input("Amount: ")
        category = input("Category: ")
        account = input("Account: ")
        description = input("Description: ")
        date = input("Date: ")

        transaction = create_transaction(
            transaction_type=transaction_type,
            amount=amount,
            category=category,
            account=account,
            description=description,
            date=date,
            display_id=display_id,
        )

        save_transaction(transaction)

        print(f"{transaction_type.title()} saved successfully.")

    except ValueError as error:
        print(f"Error: {error}")


def handle_view_balance() -> None:
    transactions = load_transactions()

    total_income, total_expense, balance = calculate_summary(transactions)

    print("\n--- Financial Summary ---")
    print(f"Total Income : {total_income:.2f}")
    print(f"Total Expense: {total_expense:.2f}")
    print(f"Balance      : {balance:.2f}")


def handle_view_transactions() -> None:
    transactions = load_transactions()

    if not transactions:
        print("No transactions found.")
        return
    print(f"\n>>> There are {len(transactions)} Transactions <<<\n")
    print("================================")
    for transaction in transactions:
        print(f"ID: {transaction.display_id}")
        print(f"Type: {transaction.type}")
        print(f"Amount: {transaction.amount}")
        print(f"Category: {transaction.category}")
        print(f"Account: {transaction.account}")
        print(f"Description: {transaction.description}")
        print(f"Date: {transaction.date}")
        print("\n--------------------")
    print("================================")


def handle_filter_transactions() -> None:
    transactions = load_transactions()

    transaction_type = input(
        "Transaction type (income/expense, leave blank for all): "
    ).strip()
    transaction_type = transaction_type or None

    category = input("Category (leave blank for all): ").strip()
    category = category or None

    account = input("Account (leave blank for all): ").strip()
    account = account or None

    start_date = input("Start date YYYY-MM-DD (leave blank for all): ").strip()
    start_date = start_date or None

    end_date = input("End date YYYY-MM-DD (leave blank for all): ").strip()
    end_date = end_date or None

    try:
        if start_date:
            start_date = validate_date(start_date)

        if end_date:
            end_date = validate_date(end_date)

    except ValueError as error:
        print(f"Error: {error}")
        return

    results = filter_transactions(
        transactions,
        transaction_type=transaction_type,
        category=category,
        account=account,
        start_date=start_date,
        end_date=end_date,
    )

    print("\n=== Filtered Transactions ===")
    print(format_transactions(results))


def handle_update_transaction() -> None:
    transactions = load_transactions()

    display_id = input("Transaction ID: ").strip().upper()

    transaction = find_transaction_by_display_id(
        transactions,
        display_id,
    )

    if transaction is None:
        print("Transaction not found.")
        return

    amount_input = input(f"New Amount [{transaction.amount}]: ").strip()
    description_input = input(f"New Description [{transaction.description}]: ").strip()
    type_input = input(f"New Type [{transaction.type}]: ").strip().lower()
    category_input = input(f"New Category [{transaction.category}]: ").strip()
    account_input = input(f"New Account [{transaction.account}]: ").strip()
    date_input = input(f"New Date [{transaction.date}]: ").strip()

    try:
        updated_transaction = create_transaction(
            transaction_type=type_input or transaction.type,
            amount=amount_input or transaction.amount,
            category=category_input or transaction.category,
            account=account_input or transaction.account,
            description=description_input or transaction.description,
            date=date_input or transaction.date,
            transaction_id=transaction.id,
            display_id=transaction.display_id,
        )

    except ValueError as error:
        print(f"Error: {error}")
        return

    updated = update_transaction(transaction.display_id, updated_transaction)
    if updated:
        print("Transaction updated successfully.")
    else:
        print("Transaction not found.")


def handle_delete_transaction() -> None:
    display_id = input("Enter transaction ID: ").strip().upper()
    deleted = delete_transaction(display_id)

    if deleted:
        print("Transaction deleted successfully.")
    else:
        print("Transaction not found.")


def handle_search() -> None:
    transactions = load_transactions()
    search_key = input("Enter search term: ")

    results = search_transactions(
        transactions=transactions,
        search_key=search_key,
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
    "1": lambda: handle_add_transaction("income"),
    "2": lambda: handle_add_transaction("expense"),
    "3": handle_view_transactions,
    "4": handle_view_balance,
    "5": handle_filter_transactions,
    "6": handle_delete_transaction,
    "7": handle_update_transaction,
    "8": handle_search,
    "9": account_management_menu,
    "10": category_management_menu,
}

"""=================Main fanection=================="""


def pause() -> None:
    input("\nPress Enter to return to the main menu...")


def main() -> None:

    while True:
        print("\n\n=== Smart Expense Tracker ===")
        print("1. Add Income")
        print("2. Add Expense")
        print("3. View Transactions")
        print("4. View Balance")
        print("5. Filter Transactions")
        print("6. Delet Transaction")
        print("7. Update Transaction")
        print("8. search")
        print("9. Account Management")
        print("10. Category Management")
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
