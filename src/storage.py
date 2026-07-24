"""JSON persistence for the Smart Expense Tracker."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from id_generator import (
    calculate_next_display_id,
    generate_display_id,
    parse_display_id,
)
from transaction import Transaction


"""Specify the file address"""
BASE_DIR = Path(__file__).resolve().parent.parent  # Find the root folder
DATA_FILE = BASE_DIR / "data" / "transactions.json"  # Json file address


class StorageError(Exception):
    """Raised when transaction data cannot be safely loaded or saved."""


def _empty_document() -> dict[str, Any]:
    return {"metadata": {"next_display_id": 1}, "transactions": []}


def _normalize_document(raw_data: Any) -> dict[str, Any]:
    if isinstance(raw_data, list):
        transaction_data = raw_data
        next_display_id = calculate_next_display_id(
            [
                item.get("display_id", "")
                for item in transaction_data
                if isinstance(item, dict)
            ]
        )
        return {
            "metadata": {"next_display_id": next_display_id},
            "transactions": transaction_data,
        }

    if not isinstance(raw_data, dict):
        raise StorageError("Transaction data must be a JSON object or legacy list.")

    metadata = raw_data.get("metadata")
    transaction_data = raw_data.get("transactions")
    if not isinstance(metadata, dict) or not isinstance(transaction_data, list):
        raise StorageError(
            "Transaction data must contain metadata and transactions sections."
        )

    next_display_id = metadata.get("next_display_id")
    if (
        not isinstance(next_display_id, int)
        or isinstance(next_display_id, bool)
        or next_display_id < 1
    ):
        raise StorageError("metadata.next_display_id must be a positive integer.")

    return {
        "metadata": {"next_display_id": next_display_id},
        "transactions": transaction_data,
    }


def _read_document() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return _empty_document()

    try:
        content = DATA_FILE.read_text(encoding="utf-8")
    except OSError as error:
        raise StorageError(f"Could not read transaction data: {error}") from error

    if not content.strip():
        return _empty_document()

    try:
        return _normalize_document(json.loads(content))
    except json.JSONDecodeError as error:
        raise StorageError(
            f"Transaction data contains malformed JSON at line {error.lineno}, "
            f"column {error.colno}."
        ) from error


def _deserialize_transactions(document: dict[str, Any]) -> list[Transaction]:
    transaction_data = document["transactions"]
    if not all(isinstance(item, dict) for item in transaction_data):
        raise StorageError("Every transaction entry must be a JSON object.")

    try:
        return [Transaction(**item) for item in transaction_data]
    except TypeError as error:
        raise StorageError(f"Transaction data has an invalid structure: {error}") from error


def _write_document(document: dict[str, Any]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(document, file, indent=4)
        file.write("\n")


def get_next_display_id() -> str:
    """Return the next persisted display ID without consuming it."""
    document = _read_document()
    return generate_display_id(document["metadata"]["next_display_id"])


def load_transactions() -> list[Transaction]:
    """Load all transactions, treating missing and empty files as empty."""
    return _deserialize_transactions(_read_document())


def save_transaction(transaction: Transaction) -> None:
    """Append one transaction and advance persistent display ID state."""
    document = _read_document()
    _deserialize_transactions(document)
    document["transactions"].append(asdict(transaction))

    assigned_number = parse_display_id(transaction.display_id)
    if assigned_number is not None:
        document["metadata"]["next_display_id"] = max(
            document["metadata"]["next_display_id"],
            assigned_number + 1,
        )

    _write_document(document)


def save_transactions(transactions: list[Transaction]) -> None:
    """Save a complete transaction list while retaining monotonic ID state."""
    document = _read_document()
    document["transactions"] = [asdict(transaction) for transaction in transactions]
    _write_document(document)


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
