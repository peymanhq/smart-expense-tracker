from transaction import Transaction


def find_transaction_by_display_id(
    transactions: list[Transaction],
    display_id: str,
) -> Transaction | None:
    """Find one transaction by its exact, normalized display ID."""
    normalized_display_id = display_id.strip().casefold()
    if not normalized_display_id:
        return None

    return next(
        (
            transaction
            for transaction in transactions
            if transaction.display_id.strip().casefold() == normalized_display_id
        ),
        None,
    )


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
        or search_key in transaction.display_id.lower()
    ]
