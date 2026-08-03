"""=====================Inputs======================="""

from datetime import date, datetime
from typing import cast

from transaction import Transaction
from id_generator import generator_transaction_id

from validators import (
    AmountInput,
    parse_utc_datetime,
    validate_amount,
    validate_optional_uuid,
    validate_required_text,
    validate_transaction_date,
    validate_transaction_type,
)


def create_transaction(
    transaction_type: str,
    amount: AmountInput,
    category: str,
    account: str,
    description: str,
    transaction_date: date | str,
    created_at: datetime | str | None,
    updated_at: datetime | str,
    transaction_id: str | None = None,
    display_id: str | None = None,
    account_id: str | None = None,
    category_id: str | None = None,
) -> Transaction:

    accepted_amount = validate_amount(amount)
    accepted_type = validate_transaction_type(transaction_type)
    accepted_category = validate_required_text(category, "Category")
    accepted_account = validate_required_text(account, "Account")
    accepted_account_id = validate_optional_uuid(account_id, "Account ID")
    accepted_category_id = validate_optional_uuid(category_id, "Category ID")
    accepted_date = validate_transaction_date(transaction_date)
    accepted_created_at = parse_utc_datetime(created_at, "created_at")
    accepted_updated_at = parse_utc_datetime(updated_at, "updated_at")

    if accepted_created_at is None and transaction_id is None:
        raise ValueError("New transactions require created_at and updated_at.")
    if accepted_updated_at is None:
        raise ValueError("Transactions require updated_at.")

    if transaction_id is None:
        transaction_id = generator_transaction_id()

    return Transaction(
        id=transaction_id,
        display_id=cast(str, display_id),
        type=accepted_type,
        amount=accepted_amount,
        category=accepted_category,
        account=accepted_account,
        description=description.strip(),
        transaction_date=accepted_date,
        created_at=accepted_created_at,
        updated_at=accepted_updated_at,
        account_id=accepted_account_id,
        category_id=accepted_category_id,
    )
