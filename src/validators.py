import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import TypeAlias
from uuid import UUID

AmountInput: TypeAlias = str | float | int | Decimal


def validate_amount(amount: AmountInput) -> Decimal:
    if isinstance(amount, bool):
        raise ValueError("Amount must be a valid number.")
    try:
        normalized = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Amount must be a valid number.") from error

    if not normalized.is_finite():
        raise ValueError("Amount must be a finite number.")
    if normalized <= 0:
        raise ValueError("Amount must be greater than zero.")

    return normalized


def serialize_amount(amount: Decimal) -> str:
    """Return one non-exponent decimal representation for persistence."""
    normalized = validate_amount(amount)
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def validate_serialized_amount(value: object) -> Decimal:
    """Parse one canonical decimal string from a current storage schema."""
    if not isinstance(value, str):
        raise ValueError("Stored amount must be canonical decimal text.")
    amount = validate_amount(value)
    if serialize_amount(amount) != value:
        raise ValueError("Stored amount must be canonical decimal text.")
    return amount


def validate_transaction_date(value: date | str) -> date:
    """Parse numeric YYYY-M-D text and return a normalized calendar date."""
    if isinstance(value, datetime):
        raise ValueError("Transaction date must be a date without a time.")

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        raise ValueError("Transaction date must be in YYYY-MM-DD format.")

    match = re.fullmatch(
        r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})",
        value,
    )
    if match is None:
        raise ValueError("Transaction date must be in YYYY-MM-DD format.")

    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError as error:
        raise ValueError(
            "Transaction date must be in YYYY-MM-DD format."
        ) from error


def validate_utc_datetime(value: datetime, field_name: str) -> datetime:
    """Validate and normalize an aware UTC datetime."""
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a timezone-aware UTC datetime.")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware UTC datetime.")

    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be a timezone-aware UTC datetime.")

    return value.astimezone(timezone.utc)


def parse_utc_datetime(
    value: datetime | str | None,
    field_name: str,
) -> datetime | None:
    """Parse an optional canonical ISO-8601 UTC timestamp."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return validate_utc_datetime(value, field_name)

    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a canonical timezone-aware UTC timestamp."
        )

    try:
        parsed_value = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"{field_name} must be a canonical timezone-aware UTC timestamp."
        ) from error

    parsed_value = validate_utc_datetime(parsed_value, field_name)
    if parsed_value.isoformat() != value:
        raise ValueError(
            f"{field_name} must be a canonical timezone-aware UTC timestamp."
        )

    return parsed_value


def validate_optional_uuid(
    value: object,
    field_name: str,
) -> str | None:
    """Accept ``None`` or canonical lowercase hyphenated UUID text."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a canonical UUID string.")

    try:
        parsed_value = UUID(value)
    except (ValueError, AttributeError) as error:
        raise ValueError(
            f"{field_name} must be a canonical UUID string."
        ) from error

    if str(parsed_value) != value:
        raise ValueError(f"{field_name} must be a canonical UUID string.")
    return value


def validate_date(date_input: date | str) -> date:
    """Backward-compatible name for transaction-date validation."""
    return validate_transaction_date(date_input)


def validate_required_text(value: str, field_name: str) -> str:
    cleaned_value = value.strip()

    if not cleaned_value:
        raise ValueError(f"{field_name} cannot be empty.")

    return cleaned_value


VALID_TRANSACTION_TYPES = {"income", "expense"}


def validate_transaction_type(transaction_type: str) -> str:
    transaction_type = transaction_type.strip().lower()

    if transaction_type not in VALID_TRANSACTION_TYPES:
        raise ValueError("Invalid transaction type.")

    return transaction_type
