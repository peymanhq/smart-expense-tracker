"""CLI orchestration tests for Excel import and template generation."""

from datetime import date
from pathlib import Path

import pytest

from excel_import import ExcelImportIssue, InvalidExcelWorkbookError
from excel_import_service import (
    ExcelImportPreview,
    ExcelImportResult,
    ResolvedExcelImportRow,
)
from excel_workbook import ExcelSaveError
import main


def candidate(
    row_number: int,
    transaction_type: str,
    amount: float,
) -> ResolvedExcelImportRow:
    return ResolvedExcelImportRow(
        row_number=row_number,
        transaction_date=date(2026, 7, 20),
        transaction_type=transaction_type,
        amount=amount,
        description=f"Row {row_number}",
        account_name="Cash",
        account_id="123e4567-e89b-12d3-a456-426614174000",
        category_name="Category",
        category_id="123e4567-e89b-12d3-a456-426614174001",
    )


def preview(*, issues=()) -> ExcelImportPreview:
    candidates = (
        candidate(2, "income", 100),
        candidate(3, "expense", 30),
    )
    return ExcelImportPreview(
        source_path=Path("transactions.xlsx"),
        worksheet_name="Transactions",
        total_physical_data_rows=2,
        empty_rows_ignored=0,
        candidates=candidates,
        issues=tuple(issues),
    )


class ImportService:
    def __init__(self, analyzed_preview=None, error=None):
        self.analyzed_preview = (
            preview() if analyzed_preview is None else analyzed_preview
        )
        self.error = error
        self.analyze_calls = []
        self.persist_calls = []

    def analyze(self, source):
        self.analyze_calls.append(source)
        if self.error is not None:
            raise self.error
        return self.analyzed_preview

    def persist(self, received_preview):
        self.persist_calls.append(received_preview)
        if self.error is not None:
            raise self.error
        return ExcelImportResult(
            source_path=received_preview.source_path,
            worksheet_name="Transactions",
            transactions=("first", "second"),
            total_income=received_preview.total_income,
            total_expense=received_preview.total_expense,
            net_balance_impact=received_preview.net_balance_impact,
        )


def set_inputs(monkeypatch, values):
    responses = iter(values)
    monkeypatch.setattr("builtins.input", lambda prompt: next(responses))


def test_empty_import_path_cancels_without_analysis(
    monkeypatch,
    capsys,
) -> None:
    set_inputs(monkeypatch, [""])
    service = ImportService()

    main.handle_excel_import(service)

    assert service.analyze_calls == []
    assert "cancelled" in capsys.readouterr().out


def test_invalid_file_shows_readable_expected_error(
    monkeypatch,
    capsys,
) -> None:
    set_inputs(monkeypatch, ["bad.xlsx"])
    service = ImportService(
        error=InvalidExcelWorkbookError("invalid workbook"),
    )

    main.handle_excel_import(service)

    output = capsys.readouterr().out
    assert "Excel import error: invalid workbook" in output
    assert "Traceback" not in output


def test_validation_issues_show_rows_and_do_not_prompt_for_confirmation(
    monkeypatch,
    capsys,
) -> None:
    issue = ExcelImportIssue(
        row_number=8,
        message="Account is required.",
        code="invalid_account",
        field="Account",
    )
    set_inputs(monkeypatch, ["invalid.xlsx"])
    service = ImportService(analyzed_preview=preview(issues=[issue]))

    main.handle_excel_import(service)

    output = capsys.readouterr().out
    assert "Row 8: Account is required." in output
    assert "No transactions were imported." in output
    assert service.persist_calls == []


def test_empty_valid_workbook_does_not_prompt_or_persist(
    monkeypatch,
    capsys,
) -> None:
    empty_preview = ExcelImportPreview(
        source_path=Path("empty.xlsx"),
        worksheet_name="Transactions",
        total_physical_data_rows=0,
        empty_rows_ignored=0,
        candidates=(),
        issues=(),
    )
    set_inputs(monkeypatch, ["empty.xlsx"])
    service = ImportService(analyzed_preview=empty_preview)

    main.handle_excel_import(service)

    assert service.persist_calls == []
    assert "No transaction rows were found" in capsys.readouterr().out


def test_valid_preview_shows_counts_totals_and_decline_persists_nothing(
    monkeypatch,
    capsys,
) -> None:
    set_inputs(monkeypatch, ["valid.xlsx", "n"])
    service = ImportService()

    main.handle_excel_import(service)

    output = capsys.readouterr().out
    assert "Valid transactions: 2" in output
    assert "Income transactions: 1" in output
    assert "Expense transactions: 1" in output
    assert "Total income: 100.00" in output
    assert "Total expense: 30.00" in output
    assert "Net balance impact: 70.00" in output
    assert "cancelled" in output
    assert service.persist_calls == []


def test_confirmed_import_calls_persistence_once_and_prints_summary(
    monkeypatch,
    capsys,
) -> None:
    set_inputs(monkeypatch, ["valid.xlsx", "yes"])
    service = ImportService()

    main.handle_excel_import(service)

    assert service.analyze_calls == ["valid.xlsx"]
    assert service.persist_calls == [service.analyzed_preview]
    output = capsys.readouterr().out
    assert "Imported 2 transaction(s) atomically." in output
    assert "Net balance impact: 70.00" in output


def test_expected_persistence_error_does_not_print_traceback(
    monkeypatch,
    capsys,
) -> None:
    set_inputs(monkeypatch, ["valid.xlsx", "yes"])
    service = ImportService()

    def fail_persist(_preview):
        raise InvalidExcelWorkbookError("changed")

    service.persist = fail_persist
    main.handle_excel_import(service)

    output = capsys.readouterr().out
    assert "Excel import error: changed" in output
    assert "Traceback" not in output


def test_unexpected_import_error_is_not_silently_swallowed(monkeypatch) -> None:
    set_inputs(monkeypatch, ["valid.xlsx"])
    service = ImportService(error=RuntimeError("programming error"))

    with pytest.raises(RuntimeError, match="programming error"):
        main.handle_excel_import(service)


def test_template_default_path_loads_references_and_generates_once(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    set_inputs(monkeypatch, [""])
    calls = []

    def generator(accounts, categories, destination, **kwargs):
        calls.append((accounts, categories, destination, kwargs))
        return destination

    main.handle_excel_import_template(
        today_provider=lambda: date(2026, 7, 27),
        account_list=lambda: ["account"],
        category_list=lambda: ["category"],
        generator=generator,
    )

    assert calls == [
        (
            ["account"],
            ["category"],
            Path(
                "exports/"
                "smart_expense_tracker_import_template_2026-07-27.xlsx"
            ),
            {"overwrite": False},
        )
    ]
    assert str(calls[0][2].resolve()) in capsys.readouterr().out


def test_template_declined_overwrite_does_not_load_references(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    destination = tmp_path / "existing.xlsx"
    destination.touch()
    set_inputs(monkeypatch, [str(destination), "no"])

    main.handle_excel_import_template(
        account_list=lambda: pytest.fail("accounts should not load"),
        category_list=lambda: pytest.fail("categories should not load"),
        generator=lambda *args, **kwargs: pytest.fail(
            "generator should not run"
        ),
    )

    assert "cancelled" in capsys.readouterr().out


def test_template_expected_error_is_readable(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    set_inputs(monkeypatch, [str(tmp_path / "template.xlsx")])

    def fail_generator(*args, **kwargs):
        raise ExcelSaveError("permission denied")

    main.handle_excel_import_template(
        account_list=lambda: [],
        category_list=lambda: [],
        generator=fail_generator,
    )

    output = capsys.readouterr().out
    assert "Excel template error: permission denied" in output
    assert "Traceback" not in output


def test_main_menu_reaches_import_and_template_options(
    monkeypatch,
) -> None:
    calls = []
    set_inputs(monkeypatch, ["8", "", "9", "", "0"])
    monkeypatch.setattr(
        main,
        "MENU_ACTIONS",
        {
            **main.MENU_ACTIONS,
            "8": lambda: calls.append("import"),
            "9": lambda: calls.append("template"),
        },
    )

    main.main()

    assert calls == ["import", "template"]
