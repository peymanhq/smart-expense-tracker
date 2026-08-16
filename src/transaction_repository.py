"""Transaction persistence contract and shared repository errors."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from report import FinancialSummary
from transaction import Transaction, transaction_comparison_key


@dataclass(frozen=True)
class TransactionDateSummary:
    """Count of persisted transactions for one populated financial date."""

    transaction_date: date
    transaction_count: int


@dataclass(frozen=True)
class TransactionQuery:
    """Backend-neutral transaction selection and pagination criteria."""

    transaction_type: str | None = None
    category: str | None = None
    account: str | None = None
    description: str | None = None
    text_query: str | None = None
    transaction_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    limit: int | None = None
    offset: int = 0
    category_id: str | None = None
    account_id: str | None = None


@dataclass(frozen=True)
class TransactionPage:
    items: list[Transaction]
    total_count: int
    limit: int | None
    offset: int


class TransactionRepository(Protocol):
    """Persistence operations required by transaction workflows."""

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

    def get_by_id(self, transaction_id: str) -> Transaction | None:
        """Look up one transaction by its internal UUID."""
        ...

    def list_all(self) -> list[Transaction]:
        """List every transaction as a detached collection."""
        ...

    def list_by_date(self, transaction_date: date) -> list[Transaction]:
        """List transactions for exactly one financial date."""
        ...

    def list_date_summaries(self) -> list[TransactionDateSummary]:
        """List distinct populated dates and their transaction counts."""
        ...

    def query(self, criteria: TransactionQuery) -> TransactionPage:
        """Select and paginate transactions without loading unrelated rows."""
        ...

    def summarize(self, criteria: TransactionQuery) -> FinancialSummary:
        """Aggregate selected amounts without materializing domain records."""
        ...

    def replace(
        self,
        expected: Transaction,
        replacement: Transaction,
    ) -> Transaction:
        """Atomically replace an unchanged persisted transaction."""
        ...

    def delete_by_id(self, transaction_id: str) -> bool:
        """Delete one persisted transaction by internal ID."""
        ...


class RepositoryTransactionNotFoundError(LookupError):
    """Raised when a persistence mutation cannot find its target."""


class RepositoryTransactionRecordChangedError(ValueError):
    """Raised when a transaction changed after the caller read it."""


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


def _validate_bulk_conflicts(
    transactions: list[Transaction],
    existing_transactions: list[Transaction],
) -> None:
    """Apply the managed-reference duplicate contract."""
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
