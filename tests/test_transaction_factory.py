import pytest

from transaction_factory import create_transaction


def test_create_valid_transaction() -> None:
    transaction = create_transaction(
        transaction_type=" Income ",
        amount="125.50",
        category=" Salary ",
        account=" Bank ",
        description=" Monthly pay ",
        date="2026-07-24",
        transaction_id="uuid-1",
        display_id="T-0001",
    )

    assert transaction.id == "uuid-1"
    assert transaction.display_id == "T-0001"
    assert transaction.type == "income"
    assert transaction.amount == 125.5
    assert transaction.category == "Salary"
    assert transaction.account == "Bank"
    assert transaction.description == "Monthly pay"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("amount", "not-a-number", "Amount must be a valid number."),
        ("amount", 0, "Amount must be greater than zero."),
        ("transaction_type", "transfer", "Invalid transaction type."),
        ("category", " ", "Category cannot be empty."),
        ("account", "", "Account cannot be empty."),
        ("date", "24-07-2026", "Date must be in YYYY-MM-DD format."),
    ],
)
def test_reject_invalid_transaction_input(
    field: str,
    value: object,
    message: str,
) -> None:
    values = {
        "transaction_type": "expense",
        "amount": "10",
        "category": "Food",
        "account": "Cash",
        "description": "",
        "date": "2026-07-24",
        "display_id": "T-0001",
    }
    values[field] = value

    with pytest.raises(ValueError, match=message):
        create_transaction(**values)
