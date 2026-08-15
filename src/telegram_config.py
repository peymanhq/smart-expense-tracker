"""Telegram bot configuration loaded from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_ALLOWED_USER_ID_ENV = "TELEGRAM_ALLOWED_USER_ID"
SMART_EXPENSE_TRACKER_WORKSPACE_ENV = "SMART_EXPENSE_TRACKER_WORKSPACE"
TELEGRAM_TIMEZONE_ENV = "TELEGRAM_TIMEZONE"
DEFAULT_TELEGRAM_TIMEZONE = "Asia/Baghdad"


class TelegramConfigurationError(ValueError):
    """Raised when Telegram environment configuration is missing or invalid."""


@dataclass(frozen=True)
class TelegramConfig:
    """Validated runtime configuration for the single-user Telegram bot."""

    bot_token: str = field(repr=False)
    allowed_user_id: int
    workspace_root: Path
    timezone: ZoneInfo


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

    raw_workspace = source.get(
        SMART_EXPENSE_TRACKER_WORKSPACE_ENV,
        "",
    ).strip()
    if not raw_workspace:
        raise TelegramConfigurationError(
            f"{SMART_EXPENSE_TRACKER_WORKSPACE_ENV} is required."
        )
    workspace_root = Path(raw_workspace).expanduser().resolve()
    if not workspace_root.is_dir():
        raise TelegramConfigurationError(
            f"{SMART_EXPENSE_TRACKER_WORKSPACE_ENV} must identify an "
            "existing directory."
        )

    timezone_name = source.get(
        TELEGRAM_TIMEZONE_ENV,
        DEFAULT_TELEGRAM_TIMEZONE,
    ).strip()
    if not timezone_name:
        raise TelegramConfigurationError(
            f"{TELEGRAM_TIMEZONE_ENV} must not be empty."
        )
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise TelegramConfigurationError(
            f"{TELEGRAM_TIMEZONE_ENV} must be a valid IANA timezone."
        ) from error

    return TelegramConfig(
        bot_token=bot_token,
        allowed_user_id=allowed_user_id,
        workspace_root=workspace_root,
        timezone=timezone,
    )
