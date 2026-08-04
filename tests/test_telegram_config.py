import pytest

from telegram_config import (
    TelegramConfig,
    TelegramConfigurationError,
    load_telegram_config,
)


def test_load_telegram_config_returns_validated_configuration() -> None:
    config = load_telegram_config(
        {
            "TELEGRAM_BOT_TOKEN": "  test-token  ",
            "TELEGRAM_ALLOWED_USER_ID": "123456789",
        }
    )

    assert config == TelegramConfig(
        bot_token="test-token",
        allowed_user_id=123456789,
    )


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
) -> None:
    with pytest.raises(TelegramConfigurationError) as error:
        load_telegram_config(environment)

    assert str(error.value) == expected_message
