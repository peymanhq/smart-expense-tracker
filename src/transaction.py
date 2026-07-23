"""Transaction model."""

from dataclasses import dataclass


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
    date: str
