import builtins
from datetime import date

import pytest

import main
from date_policy import validate_date_query
from transaction import Transaction


TODAY = date(2026, 7, 25)


def make_transaction(
    display_number: int,
    transaction_type: str,
    amount: float,
    transaction_date: date,
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
