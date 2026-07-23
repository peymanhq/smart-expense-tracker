"""Storage functionality for the Smart Expense Tracker."""

import json
from dataclasses import asdict
from pathlib import Path

from transaction import Transaction


"""Specify the file address"""
BASE_DIR = Path(__file__).resolve().parent.parent  # Find the root folder
DATA_FILE = BASE_DIR / "data" / "transactions.json"  # Json file address


def save_transaction(transaction: Transaction) -> None:
    """Save a transaction to the JSON data file."""

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    transactions = []

    if DATA_FILE.exists():
        with DATA_FILE.open("r", encoding="utf-8") as file:
            transactions = json.load(file)

    transactions.append(asdict(transaction))

    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(transactions, file, indent=4)


def save_transactions(transactions: list[Transaction]) -> None:
    transactions_data = [asdict(transaction) for transaction in transactions]

    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(transactions_data, file, indent=4)


def load_transactions() -> list[Transaction]:
    """Load all transactions from the JSON data file."""

    if not DATA_FILE.exists():
        return []

    with DATA_FILE.open("r", encoding="utf-8") as file:
        transactions_data = json.load(file)

    return [Transaction(**transaction_data) for transaction_data in transactions_data]


def delete_transaction(transaction_id: str) -> bool:
    transactions = load_transactions()

    for transaction in transactions:
        if transaction.display_id.upper() == transaction_id:
            transactions.remove(transaction)
            save_transactions(transactions)
            return True

    return False


def update_transaction(
    display_id: str,
    updated_transaction: Transaction,
) -> bool:
    transactions = load_transactions()

    for index, transaction in enumerate(transactions):
        if transaction.display_id.upper() == display_id.upper():
            transactions[index] = updated_transaction
            save_transactions(transactions)
            return True

    return False


def find_transaction_by_display_id(
    transactions: list[Transaction],
    display_id: str,
) -> Transaction | None:
    """
    Find a transaction by its display ID.

    Args:
        display_id: Display ID (e.g. T-0001)
        transactions: List of transactions

    Returns:
        Transaction if found, otherwise None.
    """

    display_id = display_id.strip().upper()

    return next(
        (
            transaction
            for transaction in transactions
            if transaction.display_id.upper() == display_id
        ),
        None,
    )
