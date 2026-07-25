import builtins
from datetime import date
from types import SimpleNamespace

import pytest

import main
from account import Account
from category import Category
from id_generator import (
    parse_account_display_id,
    parse_category_display_id,
)
from transaction import Transaction


ACTIVE_DATE = date(2026, 7, 20)
ACCOUNT = Account(
    "123e4567-e89b-12d3-a456-426614174000",
    "A-0001",
    "Cash",
)
SECOND_ACCOUNT = Account(
    "123e4567-e89b-12d3-a456-426614174002",
    "A-0002",
    "Bank",
)
INACTIVE_ACCOUNT = Account(
    "123e4567-e89b-12d3-a456-426614174003",
    "A-0003",
    "Closed",
    is_active=False,
)
EXPENSE_CATEGORY = Category(
    "123e4567-e89b-12d3-a456-426614174001",
    "C-0001",
    "Food",
    "expense",
)
SECOND_EXPENSE_CATEGORY = Category(
    "123e4567-e89b-12d3-a456-426614174006",
    "C-0002",
    "Transport",
    "expense",
)
INCOME_CATEGORY = Category(
    "123e4567-e89b-12d3-a456-426614174004",
    "C-0004",
    "Salary",
    "income",
)
INACTIVE_CATEGORY = Category(
    "123e4567-e89b-12d3-a456-426614174005",
    "C-0005",
    "Old Food",
    "expense",
    is_active=False,
)


def account_display_lookup(value: str) -> Account | None:
    number = parse_account_display_id(value)
    return {
        1: ACCOUNT,
        2: SECOND_ACCOUNT,
        3: INACTIVE_ACCOUNT,
    }.get(number)


def category_display_lookup(value: str) -> Category | None:
    number = parse_category_display_id(value)
    return {
        1: EXPENSE_CATEGORY,
        2: SECOND_EXPENSE_CATEGORY,
        4: INCOME_CATEGORY,
        5: INACTIVE_CATEGORY,
    }.get(number)


def set_inputs(monkeypatch, values):
    prompts = []
    responses = iter(values)

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    monkeypatch.setattr(builtins, "input", fake_input)
    return prompts


def make_transaction(
    *,
    transaction_type: str = "expense",
    account: str = "Cash snapshot",
    category: str = "Food snapshot",
    account_id: str | None = ACCOUNT.id,
    category_id: str | None = EXPENSE_CATEGORY.id,
) -> Transaction:
    return Transaction(
        id="transaction-id",
        display_id="T-0001",
        type=transaction_type,
        amount=10.0,
        category=category,
        account=account,
        description="Lunch",
        transaction_date=ACTIVE_DATE,
        account_id=account_id,
        category_id=category_id,
    )


class RecordingService:
    def __init__(
        self,
        existing: Transaction | None = None,
        *,
        add_error: Exception | None = None,
        update_error: Exception | None = None,
    ) -> None:
        self.existing = existing
        self.add_error = add_error
        self.update_error = update_error
        self.add_calls = []
        self.update_calls = []

    def list_transactions_by_date(self, transaction_date):
        if (
            self.existing is not None
            and self.existing.transaction_date == transaction_date
        ):
            return [self.existing]
        return []

    def list_transactions(self):
        return [] if self.existing is None else [self.existing]

    def add_transaction(self, **kwargs):
        self.add_calls.append(kwargs)
        if self.add_error is not None:
            raise self.add_error
        return SimpleNamespace(
            display_id="T-0001",
            transaction_date=kwargs["transaction_date"],
        )

    def update_transaction(self, display_id, **kwargs):
        self.update_calls.append((display_id, kwargs))
        if self.update_error is not None:
            raise self.update_error
        return SimpleNamespace(
            display_id=display_id,
            transaction_date=kwargs.get(
                "transaction_date",
                self.existing.transaction_date,
            ),
        )


def transaction_dependencies(
    *,
    accounts=None,
    categories=None,
):
    account_candidates = [ACCOUNT, SECOND_ACCOUNT] if accounts is None else accounts
    category_candidates = (
        [EXPENSE_CATEGORY, SECOND_EXPENSE_CATEGORY]
        if categories is None
        else categories
    )
    return {
        "account_list": lambda: list(account_candidates),
        "account_display_lookup": account_display_lookup,
        "category_list": lambda **kwargs: list(category_candidates),
        "category_display_lookup": category_display_lookup,
    }


def test_account_selection_is_deterministic_normalized_and_non_mutating(
    monkeypatch,
    capsys,
) -> None:
    candidates = [SECOND_ACCOUNT, INACTIVE_ACCOUNT, ACCOUNT]
    original = list(candidates)
    set_inputs(monkeypatch, ["bad", "A-9999", " a-0001 "])

    selected = main.select_active_account(
        candidates,
        display_lookup=account_display_lookup,
    )

    output = capsys.readouterr().out
    assert output.index("A-0002 - Bank") < output.index("A-0001 - Cash")
    assert "A-0003 - Closed" not in output
    assert output.count("Invalid or unavailable account display ID.") == 2
    assert selected is ACCOUNT
    assert candidates == original


def test_category_selection_filters_type_and_inactive_records(
    monkeypatch,
    capsys,
) -> None:
    candidates = [
        SECOND_EXPENSE_CATEGORY,
        INCOME_CATEGORY,
        INACTIVE_CATEGORY,
        EXPENSE_CATEGORY,
    ]
    original = list(candidates)
    set_inputs(monkeypatch, ["c-2"])

    selected = main.select_active_category(
        "expense",
        candidates,
        display_lookup=category_display_lookup,
    )

    output = capsys.readouterr().out
    assert output.index("C-0002 - Transport") < output.index("C-0001 - Food")
    assert "C-0004 - Salary" not in output
    assert "C-0005 - Old Food" not in output
    assert selected is SECOND_EXPENSE_CATEGORY
    assert candidates == original


@pytest.mark.parametrize(
    ("choice", "category", "expected_type"),
    [
        ("1", INCOME_CATEGORY, "income"),
        ("2", EXPENSE_CATEGORY, "expense"),
    ],
)
def test_add_selects_managed_records_for_resulting_type(
    monkeypatch,
    capsys,
    choice,
    category,
    expected_type,
) -> None:
    service = RecordingService()
    received_types = []
    set_inputs(monkeypatch, [choice, "10", "a-1", category.display_id, "Lunch"])
    dependencies = transaction_dependencies(categories=[category])
    dependencies["category_list"] = lambda **kwargs: (
        received_types.append(kwargs["transaction_type"]) or [category]
    )

    main.handle_add_transaction(
        service,
        ACTIVE_DATE,
        **dependencies,
    )

    assert received_types == [expected_type]
    assert service.add_calls == [
        {
            "transaction_date": ACTIVE_DATE,
            "transaction_type": expected_type,
            "amount": "10",
            "category": category.name,
            "account": ACCOUNT.name,
            "description": "Lunch",
            "account_id": ACCOUNT.id,
            "category_id": category.id,
        }
    ]
    output = capsys.readouterr().out
    assert "Available accounts:" in output
    assert f"Available {expected_type} categories:" in output


@pytest.mark.parametrize(
    ("accounts", "categories", "message"),
    [
        (
            [INACTIVE_ACCOUNT],
            [EXPENSE_CATEGORY],
            "No active accounts are available",
        ),
        (
            [ACCOUNT],
            [INACTIVE_CATEGORY],
            "No active expense categories are available",
        ),
    ],
)
def test_add_aborts_when_managed_selection_set_is_empty(
    monkeypatch,
    capsys,
    accounts,
    categories,
    message,
) -> None:
    service = RecordingService()
    inputs = ["2", "10"]
    if accounts:
        inputs.append("a-1")
    set_inputs(monkeypatch, inputs)

    main.handle_add_transaction(
        service,
        ACTIVE_DATE,
        **transaction_dependencies(
            accounts=accounts,
            categories=categories,
        ),
    )

    assert service.add_calls == []
    assert message in capsys.readouterr().out


def test_add_retries_invalid_display_id_and_has_no_free_text_name_prompts(
    monkeypatch,
) -> None:
    service = RecordingService()
    prompts = set_inputs(
        monkeypatch,
        ["2", "10", "invented name", "a-1", "unknown", "c-1", "Lunch"],
    )

    main.handle_add_transaction(
        service,
        ACTIVE_DATE,
        **transaction_dependencies(),
    )

    assert service.add_calls[0]["account_id"] == ACCOUNT.id
    assert service.add_calls[0]["category_id"] == EXPENSE_CATEGORY.id
    assert "invented name" not in service.add_calls[0].values()
    assert all(prompt not in {"Account: ", "Category: "} for prompt in prompts)


def test_add_displays_service_validation_errors(
    monkeypatch,
    capsys,
) -> None:
    service = RecordingService(add_error=ValueError("account became inactive"))
    set_inputs(monkeypatch, ["2", "10", "a-1", "c-1", "Lunch"])

    main.handle_add_transaction(
        service,
        ACTIVE_DATE,
        **transaction_dependencies(),
    )

    assert "Error: account became inactive" in capsys.readouterr().out


def test_update_empty_selections_omit_reference_arguments(
    monkeypatch,
) -> None:
    service = RecordingService(make_transaction())
    prompts = set_inputs(
        monkeypatch,
        ["T-0001", "12", "Dinner", "", "", "", ""],
    )

    main.handle_update_transaction(
        service,
        ACTIVE_DATE,
        **transaction_dependencies(),
    )

    _, updates = service.update_calls[0]
    assert updates == {
        "active_date": ACTIVE_DATE,
        "amount": "12",
        "description": "Dinner",
    }
    managed_prompts = [
        prompt
        for prompt in prompts
        if "account" in prompt.lower() or "category" in prompt.lower()
    ]
    assert managed_prompts
    assert all("display ID" in prompt for prompt in managed_prompts)


@pytest.mark.parametrize(
    ("account_id", "category_id"),
    [
        (None, None),
        (ACCOUNT.id, EXPENSE_CATEGORY.id),
    ],
)
def test_update_links_legacy_or_switches_managed_references(
    monkeypatch,
    account_id,
    category_id,
) -> None:
    service = RecordingService(
        make_transaction(
            account_id=account_id,
            category_id=category_id,
        )
    )
    set_inputs(monkeypatch, ["T-0001", "", "", "", "a-2", "c-2", ""])

    main.handle_update_transaction(
        service,
        ACTIVE_DATE,
        **transaction_dependencies(),
    )

    _, updates = service.update_calls[0]
    assert updates["account_id"] == SECOND_ACCOUNT.id
    assert updates["category_id"] == SECOND_EXPENSE_CATEGORY.id
    assert "account" not in updates
    assert "category" not in updates


def test_update_type_change_lists_new_type_and_passes_compatible_category(
    monkeypatch,
) -> None:
    service = RecordingService(make_transaction())
    received_types = []
    set_inputs(monkeypatch, ["T-0001", "", "", "income", "", "c-4", ""])
    dependencies = transaction_dependencies(categories=[INCOME_CATEGORY])
    dependencies["category_list"] = lambda **kwargs: (
        received_types.append(kwargs["transaction_type"])
        or [INCOME_CATEGORY]
    )

    main.handle_update_transaction(
        service,
        ACTIVE_DATE,
        **dependencies,
    )

    _, updates = service.update_calls[0]
    assert received_types == ["income"]
    assert updates["transaction_type"] == "income"
    assert updates["category_id"] == INCOME_CATEGORY.id


def test_update_type_change_with_empty_category_defers_to_service(
    monkeypatch,
) -> None:
    service = RecordingService(make_transaction())
    set_inputs(monkeypatch, ["T-0001", "", "", "income", "", "", ""])

    main.handle_update_transaction(
        service,
        ACTIVE_DATE,
        **transaction_dependencies(categories=[INCOME_CATEGORY]),
    )

    _, updates = service.update_calls[0]
    assert updates["transaction_type"] == "income"
    assert "category_id" not in updates


def test_update_displays_service_category_compatibility_error(
    monkeypatch,
    capsys,
) -> None:
    service = RecordingService(
        make_transaction(),
        update_error=ValueError("managed category is incompatible"),
    )
    set_inputs(monkeypatch, ["T-0001", "", "", "income", "", "", ""])

    main.handle_update_transaction(
        service,
        ACTIVE_DATE,
        **transaction_dependencies(categories=[INCOME_CATEGORY]),
    )

    assert (
        "Error: managed category is incompatible"
        in capsys.readouterr().out
    )


def test_update_without_active_options_preserves_inactive_history(
    monkeypatch,
    capsys,
) -> None:
    service = RecordingService(
        make_transaction(
            account="Closed snapshot",
            category="Old Food snapshot",
            account_id=INACTIVE_ACCOUNT.id,
            category_id=INACTIVE_CATEGORY.id,
        )
    )
    set_inputs(monkeypatch, ["T-0001", "12", "", "", ""])

    main.handle_update_transaction(
        service,
        ACTIVE_DATE,
        **transaction_dependencies(accounts=[], categories=[]),
    )

    _, updates = service.update_calls[0]
    assert updates == {
        "active_date": ACTIVE_DATE,
        "amount": "12",
    }
    output = capsys.readouterr().out
    assert "Current account: Closed snapshot" in output
    assert "Current category: Old Food snapshot" in output
    assert "Current account will remain unchanged" in output
    assert "Current category will remain unchanged" in output


def test_update_without_active_options_preserves_missing_history(
    monkeypatch,
) -> None:
    service = RecordingService(
        make_transaction(
            account_id="123e4567-e89b-12d3-a456-426614174099",
            category_id="123e4567-e89b-12d3-a456-426614174098",
        )
    )
    set_inputs(monkeypatch, ["T-0001", "12", "", "", ""])

    main.handle_update_transaction(
        service,
        ACTIVE_DATE,
        **transaction_dependencies(accounts=[], categories=[]),
    )

    _, updates = service.update_calls[0]
    assert updates == {
        "active_date": ACTIVE_DATE,
        "amount": "12",
    }
