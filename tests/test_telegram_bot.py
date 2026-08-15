from datetime import date
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from telegram.ext import Application

import telegram_bot
from telegram_config import TelegramConfig, TelegramConfigurationError


def make_config(workspace: Path) -> TelegramConfig:
    return TelegramConfig(
        bot_token="123456:test-token",
        allowed_user_id=123456789,
        workspace_root=workspace,
        timezone=ZoneInfo("Asia/Baghdad"),
    )


def test_create_bot_application_registers_runtime_without_polling(
    tmp_path: Path,
) -> None:
    application = telegram_bot.create_bot_application(
        make_config(tmp_path),
        today_provider=lambda: date(2026, 8, 4),
    )

    assert isinstance(application, Application)
    assert len(application.handlers[0]) == 6
    assert (tmp_path / "data" / "smart_expense_tracker.sqlite3").is_file()


def test_main_runs_long_polling_with_all_update_types(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    application = Mock()
    monkeypatch.setattr(telegram_bot, "load_telegram_config", lambda: config)
    monkeypatch.setattr(
        telegram_bot,
        "create_bot_application",
        lambda loaded: application,
    )

    telegram_bot.main()

    application.run_polling.assert_called_once_with(
        allowed_updates=telegram_bot.Update.ALL_TYPES
    )


def test_main_fails_before_runtime_for_invalid_configuration(
    monkeypatch,
    capsys,
) -> None:
    def fail_configuration():
        raise TelegramConfigurationError("configuration failed")

    create_application = Mock()
    monkeypatch.setattr(telegram_bot, "load_telegram_config", fail_configuration)
    monkeypatch.setattr(telegram_bot, "create_bot_application", create_application)

    with pytest.raises(SystemExit) as error:
        telegram_bot.main()

    assert error.value.code == 2
    assert "Telegram configuration error: configuration failed" in capsys.readouterr().err
    create_application.assert_not_called()
