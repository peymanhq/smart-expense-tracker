import builtins

import main


def test_account_management_menu_dispatches_activate_action(monkeypatch) -> None:
    choices = iter(["5", "", "6"])
    activate_called = False
    prompts = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(choices)

    def fake_activate() -> None:
        nonlocal activate_called
        activate_called = True

    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(main, "handle_activate_account", fake_activate)

    main.account_management_menu()

    assert activate_called is True
    assert prompts == [
        "\n===>Choose an option: ",
        "\nPress Enter to return to Account Management...",
        "\n===>Choose an option: ",
    ]
