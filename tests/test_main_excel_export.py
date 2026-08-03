"""CLI orchestration tests for Excel export."""

from datetime import date
from pathlib import Path

import pytest

from account import Account
from excel_exporter import ExcelSaveError
import main
from category import Category


class ExportService:
    def __init__(self, transactions=None):
        self.transactions = [] if transactions is None else transactions
        self.list_calls = 0

    def list_transactions(self):
        self.list_calls += 1
        return list(self.transactions)


def set_inputs(monkeypatch, values):
    responses = iter(values)
    monkeypatch.setattr("builtins.input", lambda prompt: next(responses))


def records():
    return (
        [
            Account(
                id="account-uuid",
                display_id="A-0001",
                name="Savings",
            )
        ],
        [
            Category(
                id="category-uuid",
                display_id="C-0001",
                name="Salary",
                transaction_type="income",
            )
        ],
    )


def test_empty_destination_uses_dated_default_and_resolved_names(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    set_inputs(monkeypatch, [""])
    service = ExportService(["transaction"])
    accounts, categories = records()
    calls = []

    def exporter(transactions, destination, **kwargs):
        calls.append((transactions, destination, kwargs))
        return destination

    main.handle_excel_export(
        service,
        today_provider=lambda: date(2026, 7, 26),
        account_list=lambda: accounts,
        category_list=lambda: categories,
        exporter=exporter,
    )

    assert service.list_calls == 1
    assert len(calls) == 1
    transactions, destination, kwargs = calls[0]
    assert transactions == ["transaction"]
    assert destination == Path(
        "exports/smart_expense_tracker_2026-07-26.xlsx"
    )
    assert kwargs == {
        "account_names": {"account-uuid": "Savings"},
        "category_names": {"category-uuid": "Salary"},
        "overwrite": False,
    }
    assert str(destination.resolve()) in capsys.readouterr().out


def test_explicit_destination_is_normalized_and_passed_once(
    tmp_path,
    monkeypatch,
) -> None:
    destination = tmp_path / "custom"
    set_inputs(monkeypatch, [str(destination)])
    calls = []

    def exporter(transactions, received_destination, **kwargs):
        calls.append(received_destination)
        return received_destination

    main.handle_excel_export(
        ExportService(),
        account_list=lambda: [],
        category_list=lambda: [],
        exporter=exporter,
    )

    assert calls == [destination.with_suffix(".xlsx")]


def test_declining_overwrite_does_not_load_or_export(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    destination = tmp_path / "existing.xlsx"
    destination.touch()
    set_inputs(monkeypatch, [str(destination), "n"])
    service = ExportService()
    calls = []

    main.handle_excel_export(
        service,
        account_list=lambda: pytest.fail("accounts should not load"),
        category_list=lambda: pytest.fail("categories should not load"),
        exporter=lambda *args, **kwargs: calls.append(args),
    )

    assert service.list_calls == 0
    assert calls == []
    assert "cancelled" in capsys.readouterr().out


def test_accepting_overwrite_preserves_mappings_and_exports_once(
    tmp_path,
    monkeypatch,
) -> None:
    destination = tmp_path / "existing.xlsx"
    destination.touch()
    set_inputs(monkeypatch, [str(destination), "yes"])
    accounts, categories = records()
    calls = []

    def exporter(transactions, received_destination, **kwargs):
        calls.append(kwargs)
        return received_destination

    main.handle_excel_export(
        ExportService(),
        account_list=lambda: accounts,
        category_list=lambda: categories,
        exporter=exporter,
    )

    assert len(calls) == 1
    assert calls[0]["overwrite"] is True
    assert calls[0]["account_names"] == {"account-uuid": "Savings"}
    assert calls[0]["category_names"] == {"category-uuid": "Salary"}


def test_expected_export_error_is_displayed(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    set_inputs(monkeypatch, ["output.xlsx"])

    def exporter(*args, **kwargs):
        raise ExcelSaveError("permission denied")

    main.handle_excel_export(
        ExportService(),
        account_list=lambda: [],
        category_list=lambda: [],
        exporter=exporter,
    )

    assert "Excel export error: permission denied" in capsys.readouterr().out


def test_main_menu_dispatches_excel_export(monkeypatch) -> None:
    calls = []
    set_inputs(monkeypatch, ["7", "", "0"])
    monkeypatch.setattr(
        main,
        "MENU_ACTIONS",
        {**main.MENU_ACTIONS, "7": lambda: calls.append("export")},
    )
    monkeypatch.setenv("SMART_EXPENSE_TRACKER_BACKEND", "json")

    main.main()

    assert calls == ["export"]


def test_export_orchestration_does_not_call_mutating_service_methods(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    set_inputs(monkeypatch, ["output.xlsx"])

    class ReadOnlyService(ExportService):
        def __getattr__(self, name):
            if name in {
                "add_transaction",
                "update_transaction",
                "delete_transaction",
            }:
                pytest.fail(f"unexpected persistence mutation: {name}")
            raise AttributeError(name)

    main.handle_excel_export(
        ReadOnlyService(),
        account_list=lambda: [],
        category_list=lambda: [],
        exporter=lambda transactions, destination, **kwargs: destination,
    )
