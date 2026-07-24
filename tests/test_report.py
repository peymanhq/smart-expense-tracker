from report import calculate_summary
from transaction import Transaction


def make_transaction(transaction_type: str, amount: float) -> Transaction:
    return Transaction(
        id=f"uuid-{transaction_type}-{amount}",
        display_id="T-0001",
        type=transaction_type,
        amount=amount,
        category="General",
        account="Cash",
        description="",
        date="2026-07-24",
    )


def test_calculate_summary() -> None:
    transactions = [
        make_transaction("income", 100.0),
        make_transaction("income", 25.0),
        make_transaction("expense", 40.0),
    ]

    assert calculate_summary(transactions) == (125.0, 40.0, 85.0)


def test_calculate_empty_summary() -> None:
    assert calculate_summary([]) == (0, 0, 0)
