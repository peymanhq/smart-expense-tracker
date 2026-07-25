from datetime import date, datetime, timezone

import pytest

from transaction_factory import create_transaction


ACCOUNT_ID = "123e4567-e89b-12d3-a456-426614174000"
CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174001"


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
    assert transaction.account_id is None
    assert transaction.category_id is None


@pytest.mark.parametrize(
    ("account_id", "category_id"),
    [
        (ACCOUNT_ID, None),
        (None, CATEGORY_ID),
        (ACCOUNT_ID, CATEGORY_ID),
    ],
)
def test_create_transaction_accepts_optional_canonical_reference_ids(
    account_id: str | None,
    category_id: str | None,
) -> None:
    transaction = create_transaction(
        transaction_type="expense",
        amount="12.50",
        category=" Food ",
        account=" Cash ",
        description="Lunch",
        transaction_date="2026-07-24",
        created_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        account_id=account_id,
        category_id=category_id,
    )

    assert transaction.account == "Cash"
    assert transaction.category == "Food"
    assert transaction.account_id == account_id
    assert transaction.category_id == category_id


def test_create_transaction_accepts_explicit_none_reference_ids() -> None:
    transaction = create_transaction(
        transaction_type="expense",
        amount="10",
        category="Food",
        account="Cash",
        description="Lunch",
        transaction_date="2026-07-24",
        created_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        account_id=None,
        category_id=None,
    )

    assert transaction.account_id is None
    assert transaction.category_id is None


@pytest.mark.parametrize("field", ["account_id", "category_id"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        f" {ACCOUNT_ID}",
        "not-a-uuid",
        f"{{{ACCOUNT_ID}}}",
    ],
)
def test_create_transaction_rejects_invalid_reference_ids(
    field: str,
    value: str,
) -> None:
    values = {
        "transaction_type": "expense",
        "amount": "10",
        "category": "Food",
        "account": "Cash",
        "description": "Lunch",
        "transaction_date": "2026-07-24",
        "created_at": datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        field: value,
    }

    with pytest.raises(ValueError, match="canonical UUID"):
        create_transaction(**values)


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
    ["2026/07/24", " 2026-07-24", "2026-07-24 "],
)
def test_reject_unsupported_transaction_date_formats(
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


@pytest.mark.parametrize(
    "transaction_date",
    ["2026-7-5", "2026-07-5", "2026-7-05"],
)
def test_normalize_supported_unpadded_transaction_date(
    transaction_date: str,
) -> None:
    transaction = create_transaction(
        transaction_type="expense",
        amount=10,
        category="Food",
        account="Cash",
        description="Lunch",
        transaction_date=transaction_date,
        created_at=datetime(2026, 7, 5, 9, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 5, 9, 15, tzinfo=timezone.utc),
    )

    assert transaction.transaction_date == date(2026, 7, 5)


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
