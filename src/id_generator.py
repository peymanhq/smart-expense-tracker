import uuid
from transaction import Transaction


def generator_transaction_id() -> str:
    return str(uuid.uuid4())


def generate_display_id(
    transactions: list[Transaction],
) -> str:
    if not transactions:
        return "T-0001"
    numbers = []
    for transaction in transactions:
        display_id = transaction.display_id

        if display_id.startswith("T-"):
            number = int(display_id.removeprefix("T-"))
            numbers.append(number)
    next_number = max(numbers, default=0) + 1
    return f"T-{next_number:04d}"
