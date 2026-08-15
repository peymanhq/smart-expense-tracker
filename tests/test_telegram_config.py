from pathlib import Path

import pytest

from telegram_config import (
    TelegramConfig,
    TelegramConfigurationError,
    load_telegram_config,
)


def test_load_telegram_config_returns_validated_configuration(
    tmp_path: Path,
) -> None:
    config = load_telegram_config(
        {
            "TELEGRAM_BOT_TOKEN": "  test-token  ",
            "TELEGRAM_ALLOWED_USER_ID": "123456789",
            "SMART_EXPENSE_TRACKER_WORKSPACE": str(tmp_path),
        }
    )

    assert config.bot_token == "test-token"
    assert config.allowed_user_id == 123456789
    assert config.workspace_root == tmp_path.resolve()
    assert config.timezone.key == "Asia/Baghdad"
    assert "test-token" not in repr(config)


@pytest.mark.parametrize(
    ("environment", "expected_message"),
    [
        (
            {"TELEGRAM_ALLOWED_USER_ID": "123456789"},
            "TELEGRAM_BOT_TOKEN is required.",
        ),
        (
            {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_ALLOWED_USER_ID": "",
            },
            "TELEGRAM_ALLOWED_USER_ID is required.",
        ),
        (
            {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_ALLOWED_USER_ID": "not-a-number",
            },
            "TELEGRAM_ALLOWED_USER_ID must be an integer.",
        ),
        (
            {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_ALLOWED_USER_ID": "0",
            },
            "TELEGRAM_ALLOWED_USER_ID must be a positive integer.",
        ),
        (
            {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_ALLOWED_USER_ID": "-10",
            },
            "TELEGRAM_ALLOWED_USER_ID must be a positive integer.",
        ),
    ],
)
def test_load_telegram_config_rejects_invalid_environment(
    environment: dict[str, str],
    expected_message: str,
    tmp_path: Path,
) -> None:
    environment.setdefault("SMART_EXPENSE_TRACKER_WORKSPACE", str(tmp_path))
    with pytest.raises(TelegramConfigurationError) as error:
        load_telegram_config(environment)

    assert str(error.value) == expected_message


def test_load_telegram_config_requires_workspace(tmp_path: Path) -> None:
    environment = {
        "TELEGRAM_BOT_TOKEN": "test-token",
        "TELEGRAM_ALLOWED_USER_ID": "123456789",
    }

    with pytest.raises(
        TelegramConfigurationError,
        match="SMART_EXPENSE_TRACKER_WORKSPACE is required",
    ):
        load_telegram_config(environment)


@pytest.mark.parametrize("workspace_kind", ["missing", "file"])
def test_load_telegram_config_rejects_non_directory_workspace(
    tmp_path: Path,
    workspace_kind: str,
) -> None:
    workspace = tmp_path / workspace_kind
    if workspace_kind == "file":
        workspace.write_text("not a directory", encoding="utf-8")

    with pytest.raises(
        TelegramConfigurationError,
        match="must identify an existing directory",
    ):
        load_telegram_config(
            {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_ALLOWED_USER_ID": "123456789",
                "SMART_EXPENSE_TRACKER_WORKSPACE": str(workspace),
            }
        )


@pytest.mark.parametrize("timezone", ["", "Invalid/Timezone"])
def test_load_telegram_config_rejects_invalid_timezone(
    tmp_path: Path,
    timezone: str,
) -> None:
    with pytest.raises(TelegramConfigurationError, match="TELEGRAM_TIMEZONE"):
        load_telegram_config(
            {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_ALLOWED_USER_ID": "123456789",
                "SMART_EXPENSE_TRACKER_WORKSPACE": str(tmp_path),
                "TELEGRAM_TIMEZONE": timezone,
            }
        )


def test_load_telegram_config_accepts_explicit_timezone(tmp_path: Path) -> None:
    config = load_telegram_config(
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_ALLOWED_USER_ID": "123456789",
            "SMART_EXPENSE_TRACKER_WORKSPACE": str(tmp_path),
            "TELEGRAM_TIMEZONE": "UTC",
        }
    )

    assert config.timezone.key == "UTC"
