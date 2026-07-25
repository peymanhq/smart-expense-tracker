from datetime import date, datetime, timezone

import pytest

from report import (
    FinancialSummary,
    calculate_financial_summary,
    calculate_summary,
    generate_daily_summary,
    generate_date_range_summary,
)
from transaction import Transaction


def make_transaction(
    display_number: int,
    transaction_type: str,
    amount: float,
    transaction_date: date,
    *,
    created_at: datetime | None = None,
) -> Transaction:
    return Transaction(
        id=f"uuid-{display_number}",
        display_id=f"T-{display_number:04d}",
        type=transaction_type,
        amount=amount,
        category="General",
        account="Cash",
        description="",
        transaction_date=transaction_date,
        created_at=created_at,
    )


TRANSACTIONS = [
    make_transaction(1, "income", 100.0, date(2026, 7, 1)),
    make_transaction(2, "expense", 40.0, date(2026, 7, 15)),
    make_transaction(3, "income", 25.0, date(2026, 7, 31)),
    make_transaction(4, "expense", 5.0, date(2026, 8, 1)),
]


def test_calculate_financial_summary_and_legacy_all_time_tuple() -> None:
    summary = calculate_financial_summary(TRANSACTIONS)

    assert summary == FinancialSummary(125.0, 45.0, 80.0, 4)
    assert calculate_summary(TRANSACTIONS) == (125.0, 45.0, 80.0)


def test_empty_summary_uses_zero_values() -> None:
    assert calculate_financial_summary([]) == FinancialSummary(0, 0, 0, 0)
    assert calculate_summary([]) == (0, 0, 0)


def test_daily_report_totals_balance_count_and_empty() -> None:
    transactions = [
        make_transaction(1, "income", 100.0, date(2026, 7, 20)),
        make_transaction(2, "expense", 35.0, date(2026, 7, 20)),
        make_transaction(3, "income", 50.0, date(2026, 7, 21)),
    ]

    assert generate_daily_summary(
        transactions,
        date(2026, 7, 20),
    ) == FinancialSummary(100.0, 35.0, 65.0, 2)
    assert generate_daily_summary(
        transactions,
        date(2026, 7, 19),
    ) == FinancialSummary(0, 0, 0, 0)


def test_range_report_has_inclusive_boundaries_and_empty_result() -> None:
    assert generate_date_range_summary(
        TRANSACTIONS,
        date(2026, 7, 1),
        date(2026, 7, 31),
    ) == FinancialSummary(125.0, 40.0, 85.0, 3)
    assert generate_date_range_summary(
        TRANSACTIONS,
        date(2026, 6, 1),
        date(2026, 6, 30),
    ) == FinancialSummary(0, 0, 0, 0)


def test_range_report_rejects_reversed_dates() -> None:
    with pytest.raises(ValueError, match="Start date"):
        generate_date_range_summary(
            TRANSACTIONS,
            date(2026, 7, 31),
            date(2026, 7, 1),
        )


def test_reports_use_financial_date_with_mismatched_or_legacy_timestamps() -> None:
    financial_match = make_transaction(
        1,
        "income",
        10.0,
        date(2026, 7, 20),
        created_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    legacy = make_transaction(
        2,
        "expense",
        4.0,
        date(2026, 7, 20),
        created_at=None,
    )
    record_date_only = make_transaction(
        3,
        "income",
        999.0,
        date(2026, 7, 25),
        created_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )

    assert generate_daily_summary(
        [record_date_only, financial_match, legacy],
        date(2026, 7, 20),
    ) == FinancialSummary(10.0, 4.0, 6.0, 2)
