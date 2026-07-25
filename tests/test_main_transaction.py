import builtins
from datetime import date, datetime, timezone
from functools import partial

import pytest

import main
from account import Account
from category import Category
from id_generator import (
    parse_account_display_id,
    parse_category_display_id,
)
from transaction_repository import JsonTransactionRepository
from transaction_service import TransactionService


TODAY = date(2026, 7, 25)
PAST_DATE = date(2026, 7, 20)
NOW = datetime(2026, 7, 25, 9, 15, tzinfo=timezone.utc)
ACCOUNT_ID = "123e4567-e89b-12d3-a456-426614174000"
CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174001"
ACCOUNT = Account(ACCOUNT_ID, "A-0001", "Cash")
EXPENSE_CATEGORY = Category(
    CATEGORY_ID,
    "C-0001",
    "Food",
    "expense",
)


def account_display_lookup(value: str) -> Account | None:
    return ACCOUNT if parse_account_display_id(value) == 1 else None


def category_display_lookup(value: str) -> Category | None:
    return EXPENSE_CATEGORY if parse_category_display_id(value) == 1 else None


@pytest.fixture
def service(tmp_path) -> TransactionService:
    return TransactionService(
        JsonTransactionRepository(
            tmp_path / "data" / "transactions.json"
        ),
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
        account_lookup=lambda account_id: (
            ACCOUNT if account_id == ACCOUNT.id else None
        ),
        category_lookup=lambda category_id: (
            EXPENSE_CATEGORY
            if category_id == EXPENSE_CATEGORY.id
            else None
        ),
    )


def add_transaction(
    service: TransactionService,
    transaction_date: date,
    *,
    description: str = "Lunch",
):
    return service.add_transaction(
        transaction_date=transaction_date,
        transaction_type="expense",
        amount=10,
        category="Food",
        account="Cash",
        description=description,
    )


def set_inputs(monkeypatch, values):
    prompts = []
    responses = iter(values)

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    monkeypatch.setattr(builtins, "input", fake_input)
    return prompts


def update_without_replacement_options(
    service,
    active_date: date,
) -> None:
    main.handle_update_transaction(
        service,
        active_date,
        account_list=lambda: [],
        category_list=lambda **kwargs: [],
    )


def test_runtime_service_uses_public_managed_uuid_lookups() -> None:
    account_lookup = main.TRANSACTION_SERVICE._account_lookup
    category_lookup = main.TRANSACTION_SERVICE._category_lookup

    assert isinstance(account_lookup, partial)
    assert account_lookup.func is main.get_account_by_id
    assert account_lookup.keywords == {
        "accounts_file": main.ACCOUNTS_FILE,
    }
    assert isinstance(category_lookup, partial)
    assert category_lookup.func is main.get_category_by_id
    assert category_lookup.keywords == {
        "categories_file": main.CATEGORIES_FILE,
        "state_file": main.CATEGORY_STATE_FILE,
    }

    account_list = main.TRANSACTION_ACTIVE_ACCOUNT_LIST
    account_display_lookup = main.TRANSACTION_ACCOUNT_DISPLAY_LOOKUP
    category_list = main.TRANSACTION_ACTIVE_CATEGORY_LIST
    category_display_lookup = main.TRANSACTION_CATEGORY_DISPLAY_LOOKUP

    assert isinstance(account_list, partial)
    assert account_list.func is main.list_accounts
    assert account_list.keywords == {
        "accounts_file": main.ACCOUNTS_FILE,
        "active_only": True,
    }
    assert isinstance(account_display_lookup, partial)
    assert account_display_lookup.func is main.get_account_by_display_id
    assert account_display_lookup.keywords == {
        "accounts_file": main.ACCOUNTS_FILE,
    }
    assert isinstance(category_list, partial)
    assert category_list.func is main.list_categories
    assert category_list.keywords == {
        "categories_file": main.CATEGORIES_FILE,
        "state_file": main.CATEGORY_STATE_FILE,
        "active_only": True,
    }
    assert isinstance(category_display_lookup, partial)
    assert category_display_lookup.func is main.get_category_by_display_id
    assert category_display_lookup.keywords == {
        "categories_file": main.CATEGORIES_FILE,
        "state_file": main.CATEGORY_STATE_FILE,
    }


def test_workspace_defaults_to_today_and_displays_active_date(
    service,
    monkeypatch,
    capsys,
) -> None:
    received_dates = []
    set_inputs(monkeypatch, ["2", "", "0"])
    monkeypatch.setattr(
        main,
        "handle_view_transactions",
        lambda selected_service, active_date: received_dates.append(active_date),
    )

    main.transaction_management_menu(service, lambda: TODAY)

    assert received_dates == [TODAY]
    assert "Active date: 2026-07-25" in capsys.readouterr().out


def test_reopening_workspace_resets_local_date_to_today(
    service,
    monkeypatch,
) -> None:
    received_dates = []
    choices = iter(
        [
            "5",
            "",
            "2",
            "",
            "0",
            "2",
            "",
            "0",
        ]
    )
    monkeypatch.setattr(builtins, "input", lambda prompt: next(choices))
    monkeypatch.setattr(
        main,
        "handle_change_active_date",
        lambda selected_service, active_date: PAST_DATE,
    )
    monkeypatch.setattr(
        main,
        "handle_view_transactions",
        lambda selected_service, active_date: received_dates.append(active_date),
    )

    main.transaction_management_menu(service, lambda: TODAY)
    main.transaction_management_menu(service, lambda: TODAY)

    assert received_dates == [PAST_DATE, TODAY]


def test_active_date_survives_transaction_actions(
    service,
    monkeypatch,
) -> None:
    received_dates = []
    set_inputs(
        monkeypatch,
        ["5", "", "1", "", "2", "", "3", "", "4", "", "0"],
    )
    monkeypatch.setattr(
        main,
        "handle_change_active_date",
        lambda selected_service, active_date: PAST_DATE,
    )
    for handler_name in (
        "handle_add_transaction",
        "handle_view_transactions",
        "handle_update_transaction",
        "handle_delete_transaction",
    ):
        monkeypatch.setattr(
            main,
            handler_name,
            lambda selected_service, active_date: received_dates.append(
                active_date
            ),
        )

    main.transaction_management_menu(service, lambda: TODAY)

    assert received_dates == [PAST_DATE] * 4


def test_add_uses_active_date_without_date_or_clock_prompts(
    service,
    monkeypatch,
    capsys,
) -> None:
    prompts = set_inputs(
        monkeypatch,
        ["2", "10", " a-1 ", " c-1 ", "Lunch"],
    )

    main.handle_add_transaction(
        service,
        PAST_DATE,
        account_list=lambda: [ACCOUNT],
        account_display_lookup=account_display_lookup,
        category_list=lambda **kwargs: [EXPENSE_CATEGORY],
        category_display_lookup=category_display_lookup,
    )

    created = service.list_transactions_by_date(PAST_DATE)
    assert len(created) == 1
    assert created[0].display_id == "T-0001"
    assert all("Date:" not in prompt for prompt in prompts)
    assert all("timestamp" not in prompt.lower() for prompt in prompts)
    assert "Transaction T-0001 added for 2026-07-20." in capsys.readouterr().out


def test_view_only_displays_active_date_and_date_specific_empty_state(
    service,
    capsys,
) -> None:
    add_transaction(service, TODAY, description="Today only")
    add_transaction(service, PAST_DATE, description="Past only")

    main.handle_view_transactions(service, PAST_DATE)
    output = capsys.readouterr().out
    assert "Past only" in output
    assert "Today only" not in output

    main.handle_view_transactions(service, date(2026, 7, 19))
    assert (
        "No transactions found for 2026-07-19."
        in capsys.readouterr().out
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-07-25", TODAY),
        ("2026-07-20", PAST_DATE),
    ],
)
def test_change_active_date_accepts_today_past_and_empty_dates(
    service,
    monkeypatch,
    value,
    expected,
) -> None:
    set_inputs(monkeypatch, [value])

    assert main.handle_change_active_date(service, TODAY) == expected


@pytest.mark.parametrize(
    "value",
    ["2026-07-26", "25-07-2026", "2026-02-30", ""],
)
def test_failed_date_change_preserves_active_date(
    service,
    monkeypatch,
    value,
    capsys,
) -> None:
    set_inputs(monkeypatch, [value])

    assert main.handle_change_active_date(service, PAST_DATE) == PAST_DATE
    assert capsys.readouterr().out


def test_browse_dates_shows_counts_pluralization_and_selects(
    service,
    monkeypatch,
    capsys,
) -> None:
    add_transaction(service, PAST_DATE)
    add_transaction(service, TODAY)
    add_transaction(service, TODAY)
    set_inputs(monkeypatch, ["2"])

    selected = main.handle_browse_transaction_dates(
        service,
        date(2026, 7, 19),
    )

    output = capsys.readouterr().out
    assert "1. 2026-07-25 — 2 transactions" in output
    assert "2. 2026-07-20 — 1 transaction" in output
    assert selected == PAST_DATE


@pytest.mark.parametrize("selection", ["x", "9", "0", ""])
def test_invalid_or_cancelled_browse_preserves_active_date(
    service,
    monkeypatch,
    selection,
) -> None:
    add_transaction(service, PAST_DATE)
    set_inputs(monkeypatch, [selection])

    assert main.handle_browse_transaction_dates(
        service,
        TODAY,
    ) == TODAY


def test_empty_date_browser_does_not_artificially_add_today(
    service,
    capsys,
) -> None:
    assert main.handle_browse_transaction_dates(service, TODAY) == TODAY
    assert "No transaction dates found." in capsys.readouterr().out


def test_update_can_remain_on_date_and_preserves_identity(
    service,
    monkeypatch,
    capsys,
) -> None:
    original = add_transaction(service, PAST_DATE)
    set_inputs(
        monkeypatch,
        [
            original.display_id,
            "25",
            "Dinner",
            "",
            "",
        ],
    )

    update_without_replacement_options(service, PAST_DATE)

    updated = service.list_transactions_by_date(PAST_DATE)[0]
    assert updated.id == original.id
    assert updated.display_id == original.display_id
    assert updated.created_at == original.created_at
    assert updated.amount == 25
    assert updated.description == "Dinner"
    assert "Transaction T-0001 updated." in capsys.readouterr().out


def test_update_can_move_date_and_future_move_is_rejected(
    service,
    monkeypatch,
    capsys,
) -> None:
    original = add_transaction(service, PAST_DATE)
    set_inputs(
        monkeypatch,
        [original.display_id, "", "", "", "2026-07-25"],
    )
    update_without_replacement_options(service, PAST_DATE)
    output = capsys.readouterr().out
    assert "updated and moved from 2026-07-20 to 2026-07-25" in output
    assert service.list_transactions_by_date(PAST_DATE) == []

    set_inputs(
        monkeypatch,
        [original.display_id, "", "", "", "2026-07-26"],
    )
    update_without_replacement_options(service, TODAY)
    assert "cannot be after today" in capsys.readouterr().out
    assert len(service.list_transactions_by_date(TODAY)) == 1


def test_update_outside_active_date_reports_distinct_error(
    service,
    monkeypatch,
    capsys,
) -> None:
    transaction = add_transaction(service, PAST_DATE)
    set_inputs(
        monkeypatch,
        [transaction.display_id, "", "", "", ""],
    )

    update_without_replacement_options(service, TODAY)

    assert (
        "belongs to 2026-07-20, not the active date 2026-07-25"
        in capsys.readouterr().out
    )


def test_update_passes_only_fields_the_user_selected(monkeypatch) -> None:
    received = None

    class FakeService:
        def list_transactions_by_date(self, transaction_date):
            return []

        def list_transactions(self):
            return [
                type(
                    "Existing",
                    (),
                    {
                        "display_id": "T-0042",
                        "type": "expense",
                        "account": "Cash",
                        "category": "Food",
                    },
                )()
            ]

        def update_transaction(self, display_id, **kwargs):
            nonlocal received
            received = (display_id, kwargs)
            return type(
                "Updated",
                (),
                {
                    "display_id": display_id,
                    "transaction_date": PAST_DATE,
                },
            )()

    set_inputs(
        monkeypatch,
        ["T-0042", "25", "", "", ""],
    )

    update_without_replacement_options(FakeService(), PAST_DATE)

    assert received == (
        "T-0042",
        {
            "active_date": PAST_DATE,
            "amount": "25",
        },
    )


def test_delete_confirmation_and_active_date_scope(
    service,
    monkeypatch,
    capsys,
) -> None:
    transaction = add_transaction(service, PAST_DATE)
    set_inputs(monkeypatch, [transaction.display_id, "n"])
    main.handle_delete_transaction(service, PAST_DATE)
    assert service.list_transactions_by_date(PAST_DATE) == [transaction]
    assert "Deletion cancelled." in capsys.readouterr().out

    set_inputs(monkeypatch, [transaction.display_id, "yes"])
    main.handle_delete_transaction(service, TODAY)
    assert (
        "belongs to 2026-07-20, not the active date 2026-07-25"
        in capsys.readouterr().out
    )

    set_inputs(monkeypatch, [transaction.display_id, "y"])
    main.handle_delete_transaction(service, PAST_DATE)
    assert service.list_transactions_by_date(PAST_DATE) == []
    assert (
        "Transaction T-0001 deleted from 2026-07-20."
        in capsys.readouterr().out
    )


def test_return_to_today_re_evaluates_injected_provider(
    service,
    monkeypatch,
    capsys,
) -> None:
    today_calls = 0

    def today_provider():
        nonlocal today_calls
        today_calls += 1
        return TODAY

    set_inputs(monkeypatch, ["7", "", "0"])

    main.transaction_management_menu(service, today_provider)

    assert today_calls == 2
    assert "Active date reset to 2026-07-25." in capsys.readouterr().out


def test_handler_uses_service_creation_path_only(monkeypatch) -> None:
    received = None

    class FakeService:
        def add_transaction(self, **kwargs):
            nonlocal received
            received = kwargs
            return type(
                "Created",
                (),
                {
                    "display_id": "T-0042",
                    "transaction_date": PAST_DATE,
                },
            )()

    set_inputs(monkeypatch, ["1", "100", "a-1", "c-1", "Pay"])

    main.handle_add_transaction(
        FakeService(),
        PAST_DATE,
        account_list=lambda: [ACCOUNT],
        account_display_lookup=account_display_lookup,
        category_list=lambda **kwargs: [
            Category(
                CATEGORY_ID,
                "C-0001",
                "Salary",
                "income",
            )
        ],
        category_display_lookup=lambda value: (
            Category(
                CATEGORY_ID,
                "C-0001",
                "Salary",
                "income",
            )
            if parse_category_display_id(value) == 1
            else None
        ),
    )

    assert received == {
        "transaction_date": PAST_DATE,
        "transaction_type": "income",
        "amount": "100",
        "category": "Salary",
        "account": "Cash",
        "description": "Pay",
        "account_id": ACCOUNT_ID,
        "category_id": CATEGORY_ID,
    }
