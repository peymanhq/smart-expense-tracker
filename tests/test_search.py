from search import find_transaction_by_display_id
from transaction import Transaction


def test_find_transaction_by_display_id_is_exact_and_normalized() -> None:
    transaction = Transaction(
        id="uuid-1",
        display_id="T-0001",
        type="expense",
        amount=10.0,
        category="Food",
        account="Cash",
        description="Lunch",
        date="2026-07-24",
    )

    assert find_transaction_by_display_id([transaction], " t-0001 ") is transaction
    assert find_transaction_by_display_id([transaction], "T-000") is None
    assert find_transaction_by_display_id([transaction], "") is None
