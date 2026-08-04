"""Foreground long-polling runtime for the Smart Expense Tracker bot."""

from collections.abc import Callable
from datetime import date, datetime
import sys
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler

from application import build_application
from telegram_application import TelegramApplicationService
from telegram_config import (
    TelegramConfig,
    TelegramConfigurationError,
    load_telegram_config,
)
from telegram_handlers import TelegramHandlers


def timezone_today(timezone: ZoneInfo) -> date:
    return datetime.now(timezone).date()


def create_bot_application(
    config: TelegramConfig,
    *,
    today_provider: Callable[[], date] | None = None,
) -> Application:
    """Compose SQLite services and register the Telegram adapter."""
    configured_today = (
        (lambda: timezone_today(config.timezone))
        if today_provider is None
        else today_provider
    )
    application_services = build_application(
        config.workspace_root,
        backend="sqlite",
        today_provider=configured_today,
    )
    telegram_service = TelegramApplicationService(
        application_services,
        configured_today,
    )
    handlers = TelegramHandlers(
        telegram_service,
        allowed_user_id=config.allowed_user_id,
    )
    application = Application.builder().token(config.bot_token).build()
    application.add_handler(handlers.conversation_handler())
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help))
    application.add_handler(CommandHandler("cancel", handlers.cancel))
    application.add_handler(CommandHandler("balance", handlers.balance))
    application.add_handler(CommandHandler("summary", handlers.summary))
    return application


def main() -> None:
    """Load configuration and run the bot until an operating-system signal."""
    try:
        config = load_telegram_config()
    except TelegramConfigurationError as error:
        print(f"Telegram configuration error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    application = create_bot_application(config)
    application.run_polling(allowed_updates=Update.ALL_TYPES)
