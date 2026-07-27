"""Transaction model."""

from dataclasses import dataclass
from datetime import date, datetime
import unicodedata

from validators import validate_transaction_date, validate_utc_datetime


@dataclass
class Transaction:
    """Represents a financial transaction."""

    id: str
    display_id: str
    type: str
    amount: float
    category: str
    account: str
    description: str
    transaction_date: date
    created_at: datetime | None = None
    updated_at: datetime | None = None
    account_id: str | None = None
    category_id: str | None = None

    def __post_init__(self) -> None:
        """Enforce typed values without consulting the system clock."""
        if validate_transaction_date(self.transaction_date) is not self.transaction_date:
            raise ValueError("transaction_date must be a datetime.date.")

        if self.created_at is not None:
            validate_utc_datetime(self.created_at, "created_at")
        if self.updated_at is not None:
            validate_utc_datetime(self.updated_at, "updated_at")


TransactionComparisonKey = tuple[date, str, float, str, str, str]


def normalized_transaction_description(description: str) -> str:
    """Return the stable comparison form used by duplicate detection."""
    return unicodedata.normalize("NFC", description.strip()).casefold()


def transaction_comparison_key(
    transaction: Transaction,
) -> TransactionComparisonKey | None:
    """Return the import duplicate key for fully managed transactions."""
    if transaction.account_id is None or transaction.category_id is None:
        return None
    return (
        transaction.transaction_date,
        transaction.type,
        transaction.amount,
        normalized_transaction_description(transaction.description),
        transaction.account_id,
        transaction.category_id,
    )
