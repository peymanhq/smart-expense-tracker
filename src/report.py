from transaction import Transaction



def calculate_summary(
    transactions: list[Transaction],
) -> tuple[float, float, float]:

    total_income = sum(
        transaction.amount
        for transaction in transactions
        if transaction.type == "income"
    )

    total_expense = sum(
        transaction.amount
        for transaction in transactions
        if transaction.type == "expense"
    )

    balance = total_income - total_expense

    return total_income, total_expense, balance

def filter_transactions(
    transactions: list[Transaction],
    transaction_type: str | None = None,
    category: str | None = None,
    account: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[Transaction]:

    filtered_transactions = transactions.copy()

    if transaction_type is not None:
        transaction_type = transaction_type.strip().lower()

        filtered_transactions = [
            transaction
            for transaction in filtered_transactions
            if transaction.type.lower() == transaction_type
        ]

    if category is not None:
        category = category.strip().lower()

        filtered_transactions = [
            transaction
            for transaction in filtered_transactions
            if transaction.category.lower() == category
        ]

    if account is not None:
        account = account.strip().lower()

        filtered_transactions = [
            transaction
            for transaction in filtered_transactions
            if transaction.account.lower() == account
        ]

    if start_date is not None:
        filtered_transactions = [
            transaction
            for transaction in filtered_transactions
            if transaction.date >= start_date
        ]

    if end_date is not None:
        filtered_transactions = [
            transaction
            for transaction in filtered_transactions
            if transaction.date <= end_date
        ]

    return filtered_transactions

    
    