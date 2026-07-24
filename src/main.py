"""Entry point for the Smart Expense Tracker application."""

from transaction_factory import create_transaction
from report import calculate_summary, filter_transactions
from formatter import format_transactions
from storage import (
    update_transaction,
    load_transactions,
    delete_transaction,
    get_next_display_id,
    save_transaction,
    find_transaction_by_display_id,
)
from search import search_transactions
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

    update_transaction(transaction.display_id, updated_transaction)

    print("Transaction updated successfully.")


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
        print("0. Exit")

        choice = input("\n===>Choose an option: ")

        if choice == "0":
            print("See you later !")
            break

        action = MENU_ACTIONS.get(choice)
        if action:
            action()
            pause()
        else:
            print("Invalid choice, Please try again.")


"""=================Program Runner=================="""
if __name__ == "__main__":
    main()
