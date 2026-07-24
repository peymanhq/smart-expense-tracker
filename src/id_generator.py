import uuid


def generator_transaction_id() -> str:
    return str(uuid.uuid4())


def generate_account_id() -> str:
    """Generate an internal UUID for an account."""
    return str(uuid.uuid4())


def generate_display_id(number: int) -> str:
    """Format a positive display ID sequence number."""
    if number < 1:
        raise ValueError("Display ID number must be positive.")
    return f"T-{number:04d}"


def parse_display_id(display_id: str) -> int | None:
    """Return the numeric portion of a valid display ID."""
    normalized = display_id.strip().upper()
    if not normalized.startswith("T-"):
        return None

    number = normalized.removeprefix("T-")
    if not number.isdigit():
        return None

    parsed = int(number)
    return parsed if parsed > 0 else None


def calculate_next_display_id(display_ids: list[str]) -> int:
    """Calculate safe initial state for a legacy transaction list."""
    numbers = [
        number
        for display_id in display_ids
        if (number := parse_display_id(display_id)) is not None
    ]
    return max(numbers, default=0) + 1


def generate_account_display_id(number: int) -> str:
    """Format a positive account display-ID sequence number."""
    if number < 1:
        raise ValueError("Display ID number must be positive.")
    return f"A-{number:04d}"


def parse_account_display_id(display_id: str) -> int | None:
    """Return the numeric portion of a valid account display ID."""
    normalized = display_id.strip().upper()
    if not normalized.startswith("A-"):
        return None

    number = normalized.removeprefix("A-")
    if not number.isdigit():
        return None

    parsed = int(number)
    return parsed if parsed > 0 else None


def calculate_next_account_display_id(display_ids: list[str]) -> int:
    """Calculate safe account display-ID state from persisted accounts."""
    numbers = [
        number
        for display_id in display_ids
        if (number := parse_account_display_id(display_id)) is not None
    ]
    return max(numbers, default=0) + 1
