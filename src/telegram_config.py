"""Telegram bot configuration loaded from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_ALLOWED_USER_ID_ENV = "TELEGRAM_ALLOWED_USER_ID"


class TelegramConfigurationError(ValueError):
    """Raised when Telegram environment configuration is missing or invalid."""


@dataclass(frozen=True)
class TelegramConfig:
    """Validated runtime configuration for the single-user Telegram bot."""

    bot_token: str
    allowed_user_id: int


def load_telegram_config(
    environment: Mapping[str, str] | None = None,
) -> TelegramConfig:
    """Load and validate Telegram configuration from an environment mapping."""
    source = os.environ if environment is None else environment

    bot_token = source.get(TELEGRAM_BOT_TOKEN_ENV, "").strip()
    if not bot_token:
        raise TelegramConfigurationError(f"{TELEGRAM_BOT_TOKEN_ENV} is required.")

    raw_user_id = source.get(TELEGRAM_ALLOWED_USER_ID_ENV, "").strip()
    if not raw_user_id:
        raise TelegramConfigurationError(f"{TELEGRAM_ALLOWED_USER_ID_ENV} is required.")

    try:
        allowed_user_id = int(raw_user_id)
    except ValueError as error:
        raise TelegramConfigurationError(
            f"{TELEGRAM_ALLOWED_USER_ID_ENV} must be an integer."
        ) from error

    if allowed_user_id <= 0:
        raise TelegramConfigurationError(
            f"{TELEGRAM_ALLOWED_USER_ID_ENV} must be a positive integer."
        )

    return TelegramConfig(
        bot_token=bot_token,
        allowed_user_id=allowed_user_id,
    )
