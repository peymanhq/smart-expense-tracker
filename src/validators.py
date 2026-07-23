from datetime import datetime


def validate_amount(amount: str | float | int) -> float:
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValueError("Amount must be a valid number.")

    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    return amount


def validate_date(date_input: str) -> str:
    try:
        parsed_date = datetime.strptime(
            date_input.strip(),
            "%Y-%m-%d",
        )
    except ValueError:
        raise ValueError("Date must be in YYYY-MM-DD format.")

    return parsed_date.strftime("%Y-%m-%d")


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
