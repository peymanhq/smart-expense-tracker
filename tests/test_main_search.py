import builtins
from datetime import date

import pytest

import main
from date_policy import validate_date_query
from transaction import Transaction


TODAY = date(2026, 7, 25)


def make_transaction(
    display_number: int,
    transaction_date: date,
    *,
    transaction_type: str = "expense",
    category: str = "Food",
    account: str = "Cash",
    description: str = "Lunch",
) -> Transaction:
    return Transaction(
        id=f"uuid-{display_number}",
        display_id=f"T-{display_number:04d}",
        type=transaction_type,
        amount=10.0,
        category=category,
        account=account,
        description=description,
        transaction_date=transaction_date,
    )


class SearchService:
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


def test_search_exact_date_prompt_and_result(monkeypatch, capsys) -> None:
    matching = make_transaction(1, date(2026, 7, 20))
    other = make_transaction(2, date(2026, 7, 21))
    service = SearchService([other, matching])
    prompts = set_inputs(monkeypatch, ["Lunch", "2", "2026-07-20"])

    main.handle_search(service)

    output = capsys.readouterr().out
    assert "Enter transaction date (YYYY-MM-DD): " in prompts
    assert "T-0001" in output
    assert "T-0002" not in output


def test_search_date_range_uses_both_prompts(monkeypatch, capsys) -> None:
    matching = make_transaction(1, date(2026, 7, 20))
    outside = make_transaction(2, date(2026, 7, 10))
    prompts = set_inputs(
        monkeypatch,
        ["Lunch", "3", "2026-07-15", "2026-07-20"],
    )

    main.handle_search(SearchService([outside, matching]))

    output = capsys.readouterr().out
    assert "Start date (YYYY-MM-DD): " in prompts
    assert "End date (YYYY-MM-DD): " in prompts
    assert "T-0001" in output
    assert "T-0002" not in output


@pytest.mark.parametrize(
    ("inputs", "expected_error"),
    [
        (["Lunch", "2", "20-07-2026"], "YYYY-MM-DD"),
        (["Lunch", "2", "2026-02-30"], "YYYY-MM-DD"),
        (["Lunch", "2", "2026-07-26"], "cannot be after today"),
        (
            ["Lunch", "3", "2026-07-20", "2026-07-19"],
            "Start date cannot be after end date",
        ),
    ],
)
def test_invalid_search_dates_do_not_execute(
    monkeypatch,
    capsys,
    inputs,
    expected_error,
) -> None:
    service = SearchService([])
    set_inputs(monkeypatch, inputs)

    main.handle_search(service)

    assert service.list_calls == 0
    assert expected_error in capsys.readouterr().out


@pytest.mark.parametrize(
    "inputs",
    [
        ["Lunch", "0"],
        ["Lunch", "2", ""],
        ["Lunch", "3", ""],
        ["Lunch", "3", "2026-07-01", ""],
    ],
)
def test_search_date_entry_can_be_cancelled(monkeypatch, capsys, inputs) -> None:
    service = SearchService([])
    set_inputs(monkeypatch, inputs)

    main.handle_search(service)

    assert service.list_calls == 0
    assert "cancelled" in capsys.readouterr().out.lower()


def test_search_empty_result_display(monkeypatch, capsys) -> None:
    set_inputs(monkeypatch, ["missing", "1"])

    main.handle_search(SearchService([]))

    assert "No matching transactions found." in capsys.readouterr().out


def test_filter_preserves_non_date_filters_and_combines_them(
    monkeypatch,
    capsys,
) -> None:
    matching = make_transaction(
        1,
        date(2026, 7, 20),
        description="Team lunch",
    )
    wrong_account = make_transaction(
        2,
        date(2026, 7, 20),
        account="Bank",
        description="Team lunch",
    )
    set_inputs(
        monkeypatch,
        [
            "expense",
            "Food",
            "Cash",
            "team",
            "2",
            "2026-07-20",
        ],
    )

    main.handle_filter_transactions(
        SearchService([wrong_account, matching])
    )

    output = capsys.readouterr().out
    assert "T-0001" in output
    assert "T-0002" not in output
