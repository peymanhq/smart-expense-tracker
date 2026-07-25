"""Transaction model."""

from dataclasses import dataclass
from datetime import date, datetime

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
