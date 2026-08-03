import builtins

import pytest

import main
from category import Category
from category_service import CategoryOperationResult
from json_storage import StorageError


def test_main_menu_dispatch_opens_category_management(monkeypatch) -> None:
    choices = iter(["6", "", "0"])
    called = False

    def fake_category_menu() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(builtins, "input", lambda prompt: next(choices))
    monkeypatch.setitem(main.MENU_ACTIONS, "6", fake_category_menu)
    monkeypatch.setenv("SMART_EXPENSE_TRACKER_BACKEND", "json")

    main.main()

    assert called is True


def test_add_category_uses_numbered_transaction_type_choice(
    monkeypatch,
    capsys,
) -> None:
    choices = iter(["2", "Food"])
    received = None

    def fake_add(name: str, transaction_type: str) -> CategoryOperationResult:
        nonlocal received
        received = (name, transaction_type)
        return CategoryOperationResult(True, "Category added successfully.")

    monkeypatch.setattr(builtins, "input", lambda prompt: next(choices))
    monkeypatch.setattr(main, "add_category", fake_add)

    main.handle_add_category()

    assert received == ("Food", "expense")
    assert "Category added successfully." in capsys.readouterr().out


def test_invalid_type_choice_is_handled_without_calling_service(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(builtins, "input", lambda prompt: "9")
    monkeypatch.setattr(
        main,
        "add_category",
        lambda *args: pytest.fail("service should not be called"),
    )

    main.handle_add_category()

    assert "Invalid transaction type choice." in capsys.readouterr().out


def test_view_categories_prints_id_name_type_and_status(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        main,
        "list_categories",
        lambda: [
            Category(
                id="uuid-1",
                display_id="C-0001",
                name="Food",
                transaction_type="expense",
                is_active=False,
            )
        ],
    )

    main.handle_view_categories()

    assert "C-0001 | Food | Expense | Inactive" in capsys.readouterr().out


def test_category_menu_back_returns_without_pause(monkeypatch) -> None:
    prompts = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return "6"

    monkeypatch.setattr(builtins, "input", fake_input)

    main.category_management_menu()

    assert prompts == ["\n===>Choose an option: "]


def test_category_menu_displays_service_failure_without_crashing(
    monkeypatch,
    capsys,
) -> None:
    choices = iter(["1", "", "6"])
    monkeypatch.setattr(builtins, "input", lambda prompt: next(choices))
    monkeypatch.setattr(
        main,
        "handle_add_category",
        lambda: print("Invalid transaction type."),
    )

    main.category_management_menu()

    assert "Invalid transaction type." in capsys.readouterr().out


def test_category_menu_displays_storage_error_consistently(
    monkeypatch,
    capsys,
) -> None:
    choices = iter(["2", "", "6"])

    def fail_view() -> None:
        raise StorageError("disk unavailable")

    monkeypatch.setattr(builtins, "input", lambda prompt: next(choices))
    monkeypatch.setattr(main, "handle_view_categories", fail_view)

    main.category_management_menu()

    assert "Storage error: disk unavailable" in capsys.readouterr().out
