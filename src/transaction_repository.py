"""Minimal transaction repository and JSON-backed implementation."""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Protocol

from id_generator import generate_display_id, parse_display_id
from search import find_transaction_by_display_id
import storage
from transaction import Transaction, transaction_comparison_key


@dataclass(frozen=True)
class TransactionDateSummary:
    """Count of persisted transactions for one populated financial date."""

    transaction_date: date
    transaction_count: int


class TransactionRepository(Protocol):
    """Persistence operations required by the transaction service."""

    def create(self, transaction: Transaction) -> Transaction:
        """Atomically allocate a display ID and persist a transaction."""
        ...

    def create_many(
        self,
        transactions: list[Transaction],
    ) -> list[Transaction]:
        """Atomically allocate display IDs and persist ordered transactions."""
        ...

    def get_by_display_id(self, display_id: str) -> Transaction | None:
        """Look up one transaction globally by display ID."""
        ...

    def list_all(self) -> list[Transaction]:
        """List every transaction as a detached in-memory collection."""
        ...

    def list_by_date(self, transaction_date: date) -> list[Transaction]:
        """List transactions for exactly one financial date."""
        ...

    def list_date_summaries(self) -> list[TransactionDateSummary]:
        """List distinct populated dates and their transaction counts."""
        ...

    def replace(self, transaction: Transaction) -> Transaction:
        """Replace one persisted transaction by internal ID."""
        ...

    def delete_by_id(self, transaction_id: str) -> bool:
        """Delete one persisted transaction by internal ID."""
        ...


class RepositoryTransactionNotFoundError(LookupError):
    """Raised when a locked persistence mutation cannot find its target."""


class RepositoryTransactionConflictError(ValueError):
    """Raised when bulk creation conflicts with a persisted or batch record."""

    def __init__(
        self,
        candidate_index: int,
        *,
        matching_display_id: str | None = None,
        earlier_candidate_index: int | None = None,
    ) -> None:
        self.candidate_index = candidate_index
        self.matching_display_id = matching_display_id
        self.earlier_candidate_index = earlier_candidate_index
        if matching_display_id is not None:
            message = (
                "Transaction candidate conflicts with existing transaction "
                f"{matching_display_id}."
            )
        else:
            message = (
                "Transaction candidate conflicts with earlier candidate "
                f"{earlier_candidate_index}."
            )
        super().__init__(message)


def _display_order(transaction: Transaction) -> tuple[int, str]:
    number = parse_display_id(transaction.display_id)
    return (
        number if number is not None else 2**63 - 1,
        transaction.display_id,
    )


class JsonTransactionRepository:
    """JSON implementation backed by the existing transaction document."""

    def __init__(self, data_file: Path | None = None) -> None:
        self._data_file = data_file

    def _read(self) -> tuple[dict, list[Transaction]]:
        document = storage._read_document(self._data_file)
        return document, storage._deserialize_transactions(document)

    def create(self, transaction: Transaction) -> Transaction:
        """Allocate and persist under one complete mutation lock."""
        with storage.transaction_file_lock(self._data_file):
            document, transactions = self._read()
            next_number = document["metadata"]["next_display_id"]
            display_id = generate_display_id(next_number)
            created_transaction = replace(
                transaction,
                display_id=display_id,
            )
            transactions.append(created_transaction)
            document["transactions"] = [
                storage._serialize_transaction(item) for item in transactions
            ]
            document["metadata"]["next_display_id"] = next_number + 1
            storage._write_document(document, self._data_file)
            return created_transaction

    def create_many(
        self,
        transactions: list[Transaction],
    ) -> list[Transaction]:
        """Allocate ordered display IDs and persist through one mutation."""
        if not transactions:
            return []
        with storage.transaction_file_lock(self._data_file):
            document, existing_transactions = self._read()
            existing_by_key = {
                key: transaction
                for transaction in existing_transactions
                if (key := transaction_comparison_key(transaction)) is not None
            }
            batch_keys: dict[tuple, int] = {}
            for index, transaction in enumerate(transactions):
                key = transaction_comparison_key(transaction)
                if key is None:
                    raise ValueError(
                        "Bulk transactions require managed Account and "
                        "Category references."
                    )
                existing = existing_by_key.get(key)
                if existing is not None:
                    raise RepositoryTransactionConflictError(
                        index,
                        matching_display_id=existing.display_id,
                    )
                if key in batch_keys:
                    raise RepositoryTransactionConflictError(
                        index,
                        earlier_candidate_index=batch_keys[key],
                    )
                batch_keys[key] = index

            next_number = document["metadata"]["next_display_id"]
            created_transactions = [
                replace(
                    transaction,
                    display_id=generate_display_id(next_number + index),
                )
                for index, transaction in enumerate(transactions)
            ]
            document["transactions"] = [
                storage._serialize_transaction(item)
                for item in (*existing_transactions, *created_transactions)
            ]
            document["metadata"]["next_display_id"] = (
                next_number + len(created_transactions)
            )
            storage._write_document(document, self._data_file)
            return created_transactions

    def get_by_display_id(self, display_id: str) -> Transaction | None:
        _, transactions = self._read()
        return find_transaction_by_display_id(transactions, display_id)

    def list_all(self) -> list[Transaction]:
        _, transactions = self._read()
        return list(transactions)

    def list_by_date(self, transaction_date: date) -> list[Transaction]:
        """Return one date ordered by ascending numeric display ID."""
        _, transactions = self._read()
        return sorted(
            (
                transaction
                for transaction in transactions
                if transaction.transaction_date == transaction_date
            ),
            key=_display_order,
        )

    def list_date_summaries(self) -> list[TransactionDateSummary]:
        _, transactions = self._read()
        counts = Counter(
            transaction.transaction_date for transaction in transactions
        )
        return [
            TransactionDateSummary(
                transaction_date=transaction_date,
                transaction_count=counts[transaction_date],
            )
            for transaction_date in sorted(counts, reverse=True)
        ]

    def replace(self, transaction: Transaction) -> Transaction:
        with storage.transaction_file_lock(self._data_file):
            document, transactions = self._read()
            for index, existing in enumerate(transactions):
                if existing.id != transaction.id:
                    continue

                preserved_transaction = replace(
                    transaction,
                    id=existing.id,
                    display_id=existing.display_id,
                    created_at=existing.created_at,
                )
                transactions[index] = preserved_transaction
                document["transactions"] = [
                    storage._serialize_transaction(item)
                    for item in transactions
                ]
                storage._write_document(document, self._data_file)
                return preserved_transaction

        raise RepositoryTransactionNotFoundError(
            f"Transaction id {transaction.id} no longer exists."
        )

    def delete_by_id(self, transaction_id: str) -> bool:
        with storage.transaction_file_lock(self._data_file):
            document, transactions = self._read()
            remaining = [
                transaction
                for transaction in transactions
                if transaction.id != transaction_id
            ]
            if len(remaining) == len(transactions):
                return False

            document["transactions"] = [
                storage._serialize_transaction(item) for item in remaining
            ]
            storage._write_document(document, self._data_file)
            return True
