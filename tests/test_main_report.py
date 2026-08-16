import builtins
from datetime import date

import pytest

import main
from category import Category
from date_policy import validate_date_query
from report import (
    calculate_financial_summary,
    generate_daily_summary,
    generate_date_range_summary,
)
from transaction import Transaction
from transaction_repository import TransactionPage
from transaction_service import DetailedFinancialReport

TODAY = date(2026, 7, 25)
CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174001"
OTHER_CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174002"


def make_transaction(
    display_number: int,
    transaction_type: str,
    amount: float,
    transaction_date: date,
    *,
    category: str = "General",
    category_id: str | None = None,
) -> Transaction:
    return Transaction(
        id=f"uuid-{display_number}",
        display_id=f"T-{display_number:04d}",
        type=transaction_type,
        amount=amount,
        category=category,
        account="Cash",
        description="",
        transaction_date=transaction_date,
        category_id=category_id,
    )


class ReportService:
    def __init__(self, transactions):
        self.transactions = transactions
        self.list_calls = 0

    def validate_date_query(self, **criteria):
        return validate_date_query(
            **criteria,
            today_provider=lambda: TODAY,
        )

    def list_transactions(self):
        self.list_calls += 1
        return list(self.transactions)

    def financial_summary(
        self,
        *,
        transaction_date=None,
        start_date=None,
        end_date=None,
        category_id=None,
        account_id=None,
    ):
        self.list_calls += 1
        selected = [
            transaction
            for transaction in self.transactions
            if (category_id is None or transaction.category_id == category_id)
            and (account_id is None or transaction.account_id == account_id)
        ]
        if transaction_date is not None:
            return generate_daily_summary(selected, transaction_date)
        if start_date is not None or end_date is not None:
            return generate_date_range_summary(
                selected,
                start_date,
                end_date,
            )
        return calculate_financial_summary(selected)

    def query_transactions(
        self,
        *,
        transaction_date=None,
        start_date=None,
        end_date=None,
        category_id=None,
        account_id=None,
        **_criteria,
    ):
        selected = [
            transaction
            for transaction in self.transactions
            if (category_id is None or transaction.category_id == category_id)
            and (account_id is None or transaction.account_id == account_id)
        ]
        if transaction_date is not None:
            selected = [
                transaction
                for transaction in selected
                if transaction.transaction_date == transaction_date
            ]
        if start_date is not None:
            selected = [
                transaction
                for transaction in selected
                if transaction.transaction_date >= start_date
            ]
        if end_date is not None:
            selected = [
                transaction
                for transaction in selected
                if transaction.transaction_date <= end_date
            ]
        return TransactionPage(selected, len(selected), None, 0)

    def detailed_financial_report(self, **criteria):
        transactions = tuple(self.query_transactions(**criteria).items)
        return DetailedFinancialReport(
            calculate_financial_summary(transactions),
            transactions,
        )


def set_inputs(monkeypatch, values):
    prompts = []
    responses = iter(values)

    def fake_input(prompt):
        prompts.append(prompt)
        return next(responses)

    monkeypatch.setattr(builtins, "input", fake_input)
    return prompts


def test_daily_report_displays_period_and_summary(monkeypatch, capsys) -> None:
    service = ReportService(
        [
            make_transaction(1, "income", 100, date(2026, 7, 20)),
            make_transaction(2, "expense", 25, date(2026, 7, 20)),
            make_transaction(3, "income", 999, date(2026, 7, 21)),
        ]
    )
    prompts = set_inputs(monkeypatch, ["2026-07-20"])

    main.handle_daily_report(service)

    output = capsys.readouterr().out
    assert "Enter transaction date (YYYY-MM-DD): " in prompts
    assert "Financial report for 2026-07-20" in output
    assert "100.00" in output
    assert "25.00" in output
    assert "75.00" in output
    assert "Transaction Count: 2" in output


def test_range_report_displays_period_and_inclusive_summary(
    monkeypatch,
    capsys,
) -> None:
    service = ReportService(
        [
            make_transaction(1, "income", 100, date(2026, 7, 1)),
            make_transaction(2, "expense", 40, date(2026, 7, 25)),
            make_transaction(3, "income", 999, date(2026, 7, 26)),
        ]
    )
    prompts = set_inputs(
        monkeypatch,
        ["2026-07-01", "2026-07-25"],
    )

    main.handle_date_range_report(service)

    output = capsys.readouterr().out
    assert "Start date (YYYY-MM-DD): " in prompts
    assert "End date (YYYY-MM-DD): " in prompts
    assert "Financial report from 2026-07-01 to 2026-07-25" in output
    assert "100.00" in output
    assert "40.00" in output
    assert "60.00" in output
    assert "Transaction Count: 2" in output


def test_empty_daily_report_displays_zero_summary(monkeypatch, capsys) -> None:
    set_inputs(monkeypatch, ["2026-07-20"])

    main.handle_daily_report(ReportService([]))

    output = capsys.readouterr().out
    assert output.count("0.00") == 3
    assert "Transaction Count: 0" in output


@pytest.mark.parametrize(
    ("handler", "inputs", "expected_error"),
    [
        (main.handle_daily_report, ["bad"], "YYYY-MM-DD"),
        (
            main.handle_daily_report,
            ["2026-07-26"],
            "cannot be after today",
        ),
        (
            main.handle_date_range_report,
            ["2026-07-20", "2026-07-19"],
            "Start date cannot be after end date",
        ),
        (
            main.handle_date_range_report,
            ["2026-07-01", "2026-07-26"],
            "cannot be after today",
        ),
    ],
)
def test_invalid_report_dates_do_not_load_transactions(
    monkeypatch,
    capsys,
    handler,
    inputs,
    expected_error,
) -> None:
    service = ReportService([])
    set_inputs(monkeypatch, inputs)

    handler(service)

    assert service.list_calls == 0
    assert expected_error in capsys.readouterr().out


@pytest.mark.parametrize(
    ("handler", "inputs"),
    [
        (main.handle_daily_report, [""]),
        (main.handle_date_range_report, [""]),
        (main.handle_date_range_report, ["2026-07-01", ""]),
    ],
)
def test_report_entry_can_be_cancelled(
    monkeypatch,
    capsys,
    handler,
    inputs,
) -> None:
    service = ReportService([])
    set_inputs(monkeypatch, inputs)

    handler(service)

    assert service.list_calls == 0
    assert "Report cancelled." in capsys.readouterr().out


def test_existing_all_time_report_remains_available(capsys) -> None:
    service = ReportService(
        [
            make_transaction(1, "income", 100, date(2026, 7, 1)),
            make_transaction(2, "expense", 40, date(2026, 8, 1)),
        ]
    )

    main.handle_view_balance(service)

    output = capsys.readouterr().out
    assert "--- Financial Summary ---" in output
    assert "100.00" in output
    assert "40.00" in output
    assert "60.00" in output
    assert "Transaction Count: 2" in output


def test_report_menu_dispatches_daily_report(monkeypatch) -> None:
    called_with = None
    service = ReportService([])
    set_inputs(monkeypatch, ["2"])

    def fake_daily(received_service):
        nonlocal called_with
        called_with = received_service

    monkeypatch.setattr(main, "handle_daily_report", fake_daily)

    main.financial_report_menu(service)

    assert called_with is service


def test_category_report_uses_uuid_for_renamed_inactive_category(
    monkeypatch,
    capsys,
) -> None:
    matching = make_transaction(
        1,
        "expense",
        42.5,
        date(2026, 7, 20),
        category="Food",
        category_id=CATEGORY_ID,
    )
    wrong_category = make_transaction(
        2,
        "expense",
        99,
        date(2026, 7, 20),
        category="Food",
        category_id=OTHER_CATEGORY_ID,
    )
    renamed = Category(
        CATEGORY_ID,
        "C-0004",
        "Dining",
        "expense",
        is_active=False,
    )
    set_inputs(
        monkeypatch,
        ["C-0004", "3", "2026-07-01", "2026-07-25"],
    )

    main.handle_category_report(
        ReportService([matching, wrong_category]),
        category_list=lambda: [renamed],
        category_display_lookup=lambda display_id: (
            renamed if display_id.strip().upper() == "C-0004" else None
        ),
    )

    output = capsys.readouterr().out
    assert "Category Report: Dining (C-0004)" in output
    assert "Type: Expense" in output
    assert "Status: Inactive" in output
    assert "Period: 2026-07-01 to 2026-07-25" in output
    assert "Total Expense: 42.50" in output
    assert "Transaction Count: 1" in output
    assert "T-0001" in output
    assert "T-0002" not in output


def test_income_category_report_supports_all_time_period(
    monkeypatch,
    capsys,
) -> None:
    income = Category(
        CATEGORY_ID,
        "C-0001",
        "Salary",
        "income",
    )
    transaction = make_transaction(
        1,
        "income",
        125,
        date(2026, 7, 20),
        category="Old salary name",
        category_id=CATEGORY_ID,
    )
    set_inputs(monkeypatch, ["C-0001", "1"])

    main.handle_category_report(
        ReportService([transaction]),
        category_list=lambda: [income],
        category_display_lookup=lambda _display_id: income,
    )

    output = capsys.readouterr().out
    assert "Period: All time" in output
    assert "Total Income: 125.00" in output
    assert "Transaction Count: 1" in output


def test_report_menu_dispatches_category_report(monkeypatch) -> None:
    called_with = None
    service = ReportService([])
    set_inputs(monkeypatch, ["4"])

    def fake_category_report(received_service):
        nonlocal called_with
        called_with = received_service

    monkeypatch.setattr(main, "handle_category_report", fake_category_report)

    main.financial_report_menu(service)

    assert called_with is service
