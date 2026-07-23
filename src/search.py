from transaction import Transaction


def search_transactions(
    transactions: list[Transaction],
    search_key: str,
) -> list[Transaction]:
    search_key = search_key.strip().lower()

    if not search_key:
        return []

    return [
        transaction
        for transaction in transactions
        if search_key in transaction.type.lower()
        or search_key in transaction.category.lower()
        or search_key in transaction.account.lower()
        or search_key in transaction.description.lower()
        or search_key in transaction.date.lower()
        or search_key in transaction.id.lower()
    ]
