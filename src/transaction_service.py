"""Application workflows for date-scoped transaction management."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from account import Account
from category import Category
from clock import TodayProvider, UtcNowProvider, local_today, utc_now
from date_policy import (
    FutureTransactionDateError,
    ValidatedDateQuery,
    validate_date_query,
)
from transaction import Transaction
from transaction_factory import create_transaction
from transaction_repository import (
    RepositoryTransactionConflictError,
    RepositoryTransactionNotFoundError,
    TransactionDateSummary,
    TransactionRepository,
)
from validators import (
    validate_optional_uuid,
    validate_transaction_date,
    validate_transaction_type,
    validate_utc_datetime,
)

AccountLookup = Callable[[str], Account | None]
CategoryLookup = Callable[[str], Category | None]


@dataclass(frozen=True)
class TransactionCreateRequest:
    """Service-boundary input for one ordered bulk-created transaction."""

    transaction_date: date
    transaction_type: str
    amount: float
    category: str
    account: str
    description: str
    account_id: str
    category_id: str


class _ReferenceNotSupplied:
    """Private marker distinguishing omission from unsupported clearing."""


_REFERENCE_NOT_SUPPLIED = _ReferenceNotSupplied()


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


class TransactionBulkConflictError(TransactionServiceError):
    """Raised when atomic bulk creation detects a late duplicate conflict."""

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
        super().__init__("Bulk transaction creation found a duplicate conflict.")


class TransactionBulkValidationError(TransactionServiceError):
    """Raised when one ordered bulk request becomes invalid before mutation."""

    def __init__(
        self,
        candidate_index: int,
        reason: Exception,
    ) -> None:
        self.candidate_index = candidate_index
        self.reason = reason
        super().__init__(
            f"Bulk transaction candidate {candidate_index} is invalid: {reason}"
        )


class ManagedReferenceError(TransactionServiceError, ValueError):
    """Base class for managed Account and Category reference errors."""


class ManagedLookupUnavailableError(ManagedReferenceError):
    """Raised when a managed reference has no configured lookup."""

    def __init__(self, record_type: str) -> None:
        self.record_type = record_type
        super().__init__(f"Managed {record_type.lower()} lookup is unavailable.")


class ManagedAccountNotFoundError(ManagedReferenceError, LookupError):
    """Raised when an account UUID does not resolve."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"Account reference {account_id} was not found.")


class ManagedAccountInactiveError(ManagedReferenceError):
    """Raised when a newly selected account is inactive."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"Account reference {account_id} is inactive.")


class ManagedCategoryNotFoundError(ManagedReferenceError, LookupError):
    """Raised when a category UUID does not resolve."""

    def __init__(self, category_id: str) -> None:
        self.category_id = category_id
        super().__init__(f"Category reference {category_id} was not found.")


class ManagedCategoryInactiveError(ManagedReferenceError):
    """Raised when a newly selected category is inactive."""

    def __init__(self, category_id: str) -> None:
        self.category_id = category_id
        super().__init__(f"Category reference {category_id} is inactive.")


class ManagedCategoryTypeMismatchError(ManagedReferenceError):
    """Raised when a managed category conflicts with a transaction type."""

    def __init__(
        self,
        category_id: str,
        category_type: str,
        transaction_type: str,
    ) -> None:
        self.category_id = category_id
        self.category_type = category_type
        self.transaction_type = transaction_type
        super().__init__(
            f"Category reference {category_id} is for {category_type} "
            f"transactions, not {transaction_type}."
        )


class ManagedSnapshotUpdateError(ManagedReferenceError):
    """Raised when text attempts to override a preserved managed snapshot."""

    def __init__(self, record_type: str) -> None:
        self.record_type = record_type
        super().__init__(
            f"{record_type} snapshot cannot be changed while preserving its "
            f"managed reference; supply a new {record_type.lower()} reference."
        )


class ManagedReferenceClearingError(ManagedReferenceError):
    """Raised when callers explicitly request unsupported reference clearing."""

    def __init__(self, record_type: str) -> None:
        self.record_type = record_type
        super().__init__(
            f"Clearing a managed {record_type.lower()} reference is not supported."
        )


class TransactionService:
    """Coordinate transaction validation, clocks, and persistence."""

    def __init__(
        self,
        repository: TransactionRepository,
        *,
        today_provider: TodayProvider = local_today,
        utc_now_provider: UtcNowProvider = utc_now,
        account_lookup: AccountLookup | None = None,
        category_lookup: CategoryLookup | None = None,
    ) -> None:
        self._repository = repository
        self._today_provider = today_provider
        self._utc_now_provider = utc_now_provider
        self._account_lookup = account_lookup
        self._category_lookup = category_lookup

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

    def _account_by_id(self, account_id: str) -> Account:
        if self._account_lookup is None:
            raise ManagedLookupUnavailableError("Account")
        account = self._account_lookup(account_id)
        if account is None:
            raise ManagedAccountNotFoundError(account_id)
        return account

    def _category_by_id(self, category_id: str) -> Category:
        if self._category_lookup is None:
            raise ManagedLookupUnavailableError("Category")
        category = self._category_lookup(category_id)
        if category is None:
            raise ManagedCategoryNotFoundError(category_id)
        return category

    def _active_account(self, account_id: str) -> Account:
        account_id = validate_optional_uuid(account_id, "Account ID")
        assert account_id is not None
        account = self._account_by_id(account_id)
        if not account.is_active:
            raise ManagedAccountInactiveError(account_id)
        return account

    def _compatible_category(
        self,
        category_id: str,
        transaction_type: str,
        *,
        require_active: bool,
    ) -> Category:
        category_id = validate_optional_uuid(category_id, "Category ID")
        assert category_id is not None
        category = self._category_by_id(category_id)
        if require_active and not category.is_active:
            raise ManagedCategoryInactiveError(category_id)
        if category.transaction_type != transaction_type:
            raise ManagedCategoryTypeMismatchError(
                category_id,
                category.transaction_type,
                transaction_type,
            )
        return category

    def add_transaction(
        self,
        *,
        transaction_date: date,
        transaction_type: str,
        amount: float,
        category: str,
        account: str,
        description: str,
        account_id: str | None = None,
        category_id: str | None = None,
    ) -> Transaction:
        accepted_date = self._accepted_date(transaction_date)
        accepted_type = validate_transaction_type(transaction_type)
        if account_id is not None:
            managed_account = self._active_account(account_id)
            account_id = managed_account.id
            account = managed_account.name
        if category_id is not None:
            managed_category = self._compatible_category(
                category_id,
                accepted_type,
                require_active=True,
            )
            category_id = managed_category.id
            category = managed_category.name
        timestamp = self._utc_now()
        transaction = create_transaction(
            transaction_type=accepted_type,
            amount=amount,
            category=category,
            account=account,
            description=description,
            transaction_date=accepted_date,
            created_at=timestamp,
            updated_at=timestamp,
            account_id=account_id,
            category_id=category_id,
        )
        return self._repository.create(transaction)

    def add_transactions(
        self,
        requests: list[TransactionCreateRequest],
    ) -> list[Transaction]:
        """Validate and atomically persist ordered new transactions."""
        candidates: list[Transaction] = []
        for index, request in enumerate(requests):
            try:
                accepted_date = self._accepted_date(request.transaction_date)
                accepted_type = validate_transaction_type(
                    request.transaction_type
                )
                managed_account = self._active_account(request.account_id)
                managed_category = self._compatible_category(
                    request.category_id,
                    accepted_type,
                    require_active=True,
                )
                timestamp = self._utc_now()
                candidates.append(
                    create_transaction(
                        transaction_type=accepted_type,
                        amount=request.amount,
                        category=managed_category.name,
                        account=managed_account.name,
                        description=request.description,
                        transaction_date=accepted_date,
                        created_at=timestamp,
                        updated_at=timestamp,
                        account_id=managed_account.id,
                        category_id=managed_category.id,
                    )
                )
            except (
                FutureTransactionDateError,
                ManagedReferenceError,
            ) as error:
                raise TransactionBulkValidationError(index, error) from error
        try:
            return self._repository.create_many(candidates)
        except RepositoryTransactionConflictError as error:
            raise TransactionBulkConflictError(
                error.candidate_index,
                matching_display_id=error.matching_display_id,
                earlier_candidate_index=error.earlier_candidate_index,
            ) from error

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
        account_id: str | None | _ReferenceNotSupplied = (
            _REFERENCE_NOT_SUPPLIED
        ),
        category_id: str | None | _ReferenceNotSupplied = (
            _REFERENCE_NOT_SUPPLIED
        ),
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
        accepted_type = (
            existing.type
            if transaction_type is None
            else validate_transaction_type(transaction_type)
        )

        accepted_account_id = existing.account_id
        accepted_account = existing.account
        if account_id is not _REFERENCE_NOT_SUPPLIED:
            if account_id is None:
                raise ManagedReferenceClearingError("Account")
            managed_account = self._active_account(account_id)
            accepted_account_id = managed_account.id
            accepted_account = managed_account.name
        elif existing.account_id is not None:
            if account is not None:
                raise ManagedSnapshotUpdateError("Account")
        elif account is not None:
            accepted_account = account

        accepted_category_id = existing.category_id
        accepted_category = existing.category
        if category_id is not _REFERENCE_NOT_SUPPLIED:
            if category_id is None:
                raise ManagedReferenceClearingError("Category")
            managed_category = self._compatible_category(
                category_id,
                accepted_type,
                require_active=True,
            )
            accepted_category_id = managed_category.id
            accepted_category = managed_category.name
        elif existing.category_id is not None:
            if category is not None:
                raise ManagedSnapshotUpdateError("Category")
            if accepted_type != existing.type:
                self._compatible_category(
                    existing.category_id,
                    accepted_type,
                    require_active=False,
                )
        elif category is not None:
            accepted_category = category

        timestamp = self._utc_now()

        # An update always advances updated_at, including a metadata-only update
        # where all optional financial/content fields are omitted.
        updated = create_transaction(
            transaction_type=accepted_type,
            amount=existing.amount if amount is None else amount,
            category=accepted_category,
            account=accepted_account,
            description=(
                existing.description if description is None else description
            ),
            transaction_date=destination_date,
            created_at=existing.created_at,
            updated_at=timestamp,
            transaction_id=existing.id,
            display_id=existing.display_id,
            account_id=accepted_account_id,
            category_id=accepted_category_id,
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
