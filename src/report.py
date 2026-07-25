"""Pure financial aggregation for selected transaction collections."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from search import filter_transactions
from transaction import Transaction


@dataclass(frozen=True)
class FinancialSummary:
    total_income: float
    total_expense: float
    balance: float
    transaction_count: int


def calculate_financial_summary(
    transactions: Iterable[Transaction],
) -> FinancialSummary:
    """Aggregate an already selected transaction collection."""
    total_income = 0.0
    total_expense = 0.0
    transaction_count = 0

    for transaction in transactions:
        transaction_count += 1
        if transaction.type == "income":
            total_income += transaction.amount
        elif transaction.type == "expense":
            total_expense += transaction.amount

    return FinancialSummary(
        total_income=total_income,
        total_expense=total_expense,
        balance=total_income - total_expense,
        transaction_count=transaction_count,
    )


def generate_daily_summary(
    transactions: Iterable[Transaction],
    transaction_date: date,
) -> FinancialSummary:
    selected = filter_transactions(
        transactions,
        transaction_date=transaction_date,
    )
    return calculate_financial_summary(selected)


def generate_date_range_summary(
    transactions: Iterable[Transaction],
    start_date: date,
    end_date: date,
) -> FinancialSummary:
    selected = filter_transactions(
        transactions,
        start_date=start_date,
        end_date=end_date,
    )
    return calculate_financial_summary(selected)


def calculate_summary(
    transactions: Iterable[Transaction],
) -> tuple[float, float, float]:
    """Backward-compatible tuple API for the existing all-time report."""
    summary = calculate_financial_summary(transactions)
    return summary.total_income, summary.total_expense, summary.balance


__all__ = [
    "FinancialSummary",
    "calculate_financial_summary",
    "calculate_summary",
    "filter_transactions",
    "generate_daily_summary",
    "generate_date_range_summary",
]
