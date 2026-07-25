"""Application workflows for date-scoped transaction management."""

from datetime import date, datetime

from clock import TodayProvider, UtcNowProvider, local_today, utc_now
from date_policy import (
    FutureTransactionDateError,
    ValidatedDateQuery,
    validate_date_query,
)
from transaction import Transaction
from transaction_factory import create_transaction
from transaction_repository import (
    JsonTransactionRepository,
    RepositoryTransactionNotFoundError,
    TransactionDateSummary,
    TransactionRepository,
)
from validators import validate_transaction_date, validate_utc_datetime


class TransactionServiceError(Exception):
    """Base class for transaction application errors."""


class TransactionNotFoundError(TransactionServiceError, LookupError):
    """Raised when a display ID does not identify a transaction."""

    def __init__(self, display_id: str) -> None:
        self.display_id = display_id
        super().__init__(f"Transaction {display_id.strip().upper()} was not found.")


class TransactionActiveDateMismatchError(TransactionServiceError):
    """Raised when a mutation target belongs to another financial date."""

    def __init__(
        self,
        display_id: str,
        transaction_date: date,
        active_date: date,
    ) -> None:
        self.display_id = display_id
        self.transaction_date = transaction_date
        self.active_date = active_date
        super().__init__(
            f"Transaction {display_id} belongs to "
            f"{transaction_date.isoformat()}, not the active date "
            f"{active_date.isoformat()}."
        )


class InvalidUtcClockError(TransactionServiceError, ValueError):
    """Raised when the injected UTC clock violates its contract."""


class TransactionService:
    """Coordinate transaction validation, clocks, and persistence."""

    def __init__(
        self,
        repository: TransactionRepository | None = None,
        *,
        today_provider: TodayProvider = local_today,
        utc_now_provider: UtcNowProvider = utc_now,
    ) -> None:
        self._repository = (
            JsonTransactionRepository() if repository is None else repository
        )
        self._today_provider = today_provider
        self._utc_now_provider = utc_now_provider

    def _accepted_date(self, value: date) -> date:
        accepted_date = validate_date_query(
            transaction_date=value,
            today_provider=self._today_provider,
        ).transaction_date
        assert accepted_date is not None
        return accepted_date

    def validate_transaction_date(self, transaction_date: date) -> date:
        """Validate a date for use as an active transaction workspace date."""
        return self._accepted_date(transaction_date)

    def validate_date_query(
        self,
        *,
        transaction_date: date | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> ValidatedDateQuery:
        """Apply the shared financial-date policy using the injected today."""
        return validate_date_query(
            transaction_date=transaction_date,
            start_date=start_date,
            end_date=end_date,
            today_provider=self._today_provider,
        )

    def _utc_now(self) -> datetime:
        value = self._utc_now_provider()
        try:
            return validate_utc_datetime(value, "UTC clock output")
        except ValueError as error:
            raise InvalidUtcClockError(str(error)) from error

    def add_transaction(
        self,
        *,
        transaction_date: date,
        transaction_type: str,
        amount: float,
        category: str,
        account: str,
        description: str,
    ) -> Transaction:
        accepted_date = self._accepted_date(transaction_date)
        timestamp = self._utc_now()
        transaction = create_transaction(
            transaction_type=transaction_type,
            amount=amount,
            category=category,
            account=account,
            description=description,
            transaction_date=accepted_date,
            created_at=timestamp,
            updated_at=timestamp,
        )
        return self._repository.create(transaction)

    def list_transactions_by_date(
        self,
        transaction_date: date,
    ) -> list[Transaction]:
        accepted_date = self._accepted_date(transaction_date)
        return self._repository.list_by_date(accepted_date)

    def list_transactions(self) -> list[Transaction]:
        """Return all persisted transactions for pure search/report workflows."""
        return self._repository.list_all()

    def list_transaction_date_summaries(
        self,
    ) -> list[TransactionDateSummary]:
        return self._repository.list_date_summaries()

    def update_transaction(
        self,
        display_id: str,
        *,
        active_date: date,
        transaction_type: str | None = None,
        amount: float | None = None,
        category: str | None = None,
        account: str | None = None,
        description: str | None = None,
        transaction_date: date | None = None,
    ) -> Transaction:
        """Persist requested changes and always advance ``updated_at``."""
        accepted_active_date = self._accepted_date(active_date)
        existing = self._require_active_transaction(
            display_id,
            accepted_active_date,
        )
        destination_date = (
            existing.transaction_date
            if transaction_date is None
            else self._accepted_date(transaction_date)
        )
        timestamp = self._utc_now()

        # An update always advances updated_at, including a metadata-only update
        # where all optional financial/content fields are omitted.
        updated = create_transaction(
            transaction_type=(
                existing.type if transaction_type is None else transaction_type
            ),
            amount=existing.amount if amount is None else amount,
            category=existing.category if category is None else category,
            account=existing.account if account is None else account,
            description=(
                existing.description if description is None else description
            ),
            transaction_date=destination_date,
            created_at=existing.created_at,
            updated_at=timestamp,
            transaction_id=existing.id,
            display_id=existing.display_id,
        )
        try:
            return self._repository.replace(updated)
        except RepositoryTransactionNotFoundError as error:
            raise TransactionNotFoundError(display_id) from error

    def delete_transaction(
        self,
        display_id: str,
        *,
        active_date: date,
    ) -> Transaction:
        accepted_active_date = self._accepted_date(active_date)
        existing = self._require_active_transaction(
            display_id,
            accepted_active_date,
        )
        if not self._repository.delete_by_id(existing.id):
            raise TransactionNotFoundError(display_id)
        return existing

    def _require_active_transaction(
        self,
        display_id: str,
        active_date: date,
    ) -> Transaction:
        transaction = self._repository.get_by_display_id(display_id)
        if transaction is None:
            raise TransactionNotFoundError(display_id)
        if transaction.transaction_date != active_date:
            raise TransactionActiveDateMismatchError(
                transaction.display_id,
                transaction.transaction_date,
                active_date,
            )
        return transaction
