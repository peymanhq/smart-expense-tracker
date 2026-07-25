from datetime import date

import pytest

from validators import validate_transaction_date


@pytest.mark.parametrize(
    "value",
    [
        "2026-7-5",
        "2026-07-5",
        "2026-7-05",
        "2026-07-05",
    ],
)
def test_transaction_date_normalizes_supported_numeric_forms(
    value: str,
) -> None:
    assert validate_transaction_date(value).isoformat() == "2026-07-05"


def test_transaction_date_accepts_only_real_leap_days() -> None:
    assert validate_transaction_date("2024-2-29") == date(2024, 2, 29)

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        validate_transaction_date("2023-2-29")


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-30",
        "2026-13-01",
        "2026-00-10",
        "2026-07-00",
    ],
)
def test_transaction_date_rejects_impossible_calendar_dates(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        validate_transaction_date(value)


@pytest.mark.parametrize(
    "value",
    [
        "05/07/2026",
        "7/5/2026",
        "05-07-2026",
        "July 5 2026",
        "not-a-date",
        "26-7-5",
        "2026-7",
        "2026-7-5-1",
    ],
)
def test_transaction_date_rejects_unsupported_or_invalid_text(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        validate_transaction_date(value)
