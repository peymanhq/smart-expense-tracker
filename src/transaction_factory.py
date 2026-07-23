"""=====================Inputs======================="""

from transaction import Transaction
from id_generator import generator_transaction_id

from validators import (
    validate_amount,
    validate_date,
    validate_required_text,
    validate_transaction_type,
)


def create_transaction(
    transaction_type: str,
    amount: str | float | int,
    category: str,
    account: str,
    description: str,
    date: str,
    transaction_id: str | None = None,
    display_id: str | None = None,
) -> Transaction:

    amount = validate_amount(amount)
    transaction_type = validate_transaction_type(transaction_type)
    category = validate_required_text(category, "Category")
    account = validate_required_text(account, "Account")
    date = validate_date(date)

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
        date=date,
    )
