from datetime import date, datetime, timezone

import pytest

from transaction_factory import create_transaction


def test_create_valid_transaction() -> None:
    transaction = create_transaction(
        transaction_type=" Income ",
        amount="125.50",
        category=" Salary ",
        account=" Bank ",
        description=" Monthly pay ",
        transaction_date="2026-07-24",
        created_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
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
    assert transaction.transaction_date == date(2026, 7, 24)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("amount", "not-a-number", "Amount must be a valid number."),
        ("amount", 0, "Amount must be greater than zero."),
        ("transaction_type", "transfer", "Invalid transaction type."),
        ("category", " ", "Category cannot be empty."),
        ("account", "", "Account cannot be empty."),
        (
            "transaction_date",
            "24-07-2026",
            "Transaction date must be in YYYY-MM-DD format.",
        ),
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
        "transaction_date": "2026-07-24",
        "created_at": datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        "display_id": "T-0001",
    }
    values[field] = value

    with pytest.raises(ValueError, match=message):
        create_transaction(**values)


@pytest.mark.parametrize(
    "transaction_date",
    ["2026/07/24", "2026-7-24", " 2026-07-24", "2026-07-24 "],
)
def test_reject_noncanonical_transaction_date_formats(
    transaction_date: str,
) -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        create_transaction(
            transaction_type="expense",
            amount=10,
            category="Food",
            account="Cash",
            description="Lunch",
            transaction_date=transaction_date,
            created_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        )


def test_reject_invalid_calendar_date() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        create_transaction(
            transaction_type="expense",
            amount=10,
            category="Food",
            account="Cash",
            description="Lunch",
            transaction_date="2026-02-30",
            created_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        )


def test_reject_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        create_transaction(
            transaction_type="expense",
            amount=10,
            category="Food",
            account="Cash",
            description="Lunch",
            transaction_date="2026-07-24",
            created_at=datetime(2026, 7, 24, 9, 15),
            updated_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        )


def test_update_can_preserve_missing_legacy_created_at() -> None:
    transaction = create_transaction(
        transaction_type="expense",
        amount=10,
        category="Food",
        account="Cash",
        description="Lunch",
        transaction_date="2026-07-24",
        created_at=None,
        updated_at=datetime(2026, 7, 25, 10, 30, tzinfo=timezone.utc),
        transaction_id="legacy-uuid",
        display_id="T-0001",
    )

    assert transaction.created_at is None
    assert transaction.updated_at == datetime(
        2026,
        7,
        25,
        10,
        30,
        tzinfo=timezone.utc,
    )
