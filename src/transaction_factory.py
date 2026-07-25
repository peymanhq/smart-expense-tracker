"""=====================Inputs======================="""

from datetime import date, datetime

from transaction import Transaction
from id_generator import generator_transaction_id

from validators import (
    parse_utc_datetime,
    validate_amount,
    validate_required_text,
    validate_transaction_date,
    validate_transaction_type,
)


def create_transaction(
    transaction_type: str,
    amount: str | float | int,
    category: str,
    account: str,
    description: str,
    transaction_date: date | str,
    created_at: datetime | str | None,
    updated_at: datetime | str,
    transaction_id: str | None = None,
    display_id: str | None = None,
) -> Transaction:

    amount = validate_amount(amount)
    transaction_type = validate_transaction_type(transaction_type)
    category = validate_required_text(category, "Category")
    account = validate_required_text(account, "Account")
    transaction_date = validate_transaction_date(transaction_date)
    created_at = parse_utc_datetime(created_at, "created_at")
    updated_at = parse_utc_datetime(updated_at, "updated_at")

    if created_at is None and transaction_id is None:
        raise ValueError("New transactions require created_at and updated_at.")
    if updated_at is None:
        raise ValueError("Transactions require updated_at.")

    if transaction_id is None:
        transaction_id = generator_transaction_id()

    return Transaction(
        id=transaction_id,
        display_id=display_id,
        type=transaction_type,
        amount=amount,
        category=category,
        account=account,
        description=description.strip(),
        transaction_date=transaction_date,
        created_at=created_at,
        updated_at=updated_at,
    )
