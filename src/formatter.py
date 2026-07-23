from transaction import Transaction


def format_transaction(transaction: Transaction) -> str:
    return (
        f"ID: {transaction.display_id}\n"
        f"Type: {transaction.type}\n"
        f"Amount: {transaction.amount}\n"
        f"Category: {transaction.category}\n"
        f"Account: {transaction.account}\n"
        f"Description: {transaction.description}\n"
        f"Date: {transaction.date}\n"
        "======================================"
    )


def format_transactions(transactions: list[Transaction]) -> str:
    if not transactions:
        return "No matching transactions found."

    return "\n".join(format_transaction(transaction) for transaction in transactions)


