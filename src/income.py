"""Income-related fanctionality for the Smart Expense Tracker"""


def add_income(
    amount: float,
    category: str,
    account: str,
    description: str,
) -> dict:
    """Create and return a new income transaction"""
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if not category.strip():
        raise ValueError("Category cannot be empty.")
    if not account.strip():
        raise ValueError("Account cannot be empty.")
    return {
        "type": "income",
        "amount": amount,
        "category": category.strip(),
        "account": account.strip(),
        "description": description.strip(),
    }
