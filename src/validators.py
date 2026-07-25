from datetime import date, datetime, timedelta, timezone
from uuid import UUID


def validate_amount(amount: str | float | int) -> float:
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValueError("Amount must be a valid number.")

    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    return amount


def validate_transaction_date(value: date | str) -> date:
    """Return a transaction date, accepting only canonical ISO date strings."""
    if isinstance(value, datetime):
        raise ValueError("Transaction date must be a date without a time.")

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        raise ValueError("Transaction date must be in YYYY-MM-DD format.")

    try:
        parsed_date = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            "Transaction date must be in YYYY-MM-DD format."
        ) from error

    if parsed_date.isoformat() != value:
        raise ValueError("Transaction date must be in YYYY-MM-DD format.")

    return parsed_date


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
