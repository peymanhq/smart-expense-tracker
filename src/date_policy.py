"""Shared application policy for transaction search and report dates."""

from dataclasses import dataclass
from datetime import date, datetime

from clock import TodayProvider
from validators import validate_transaction_date


class FutureTransactionDateError(ValueError):
    """Raised when a financial-date query includes a future date."""

    def __init__(self, transaction_date: date, today: date) -> None:
        self.transaction_date = transaction_date
        self.today = today
        super().__init__(
            f"Transaction date {transaction_date.isoformat()} cannot be after "
            f"today ({today.isoformat()})."
        )


@dataclass(frozen=True)
class ValidatedDateQuery:
    """A structurally valid, unambiguous financial-date query."""

    transaction_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None


def _require_date(value: date | None, field_name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError(f"{field_name} must be a datetime.date.")
    return validate_transaction_date(value)


def validate_date_query(
    *,
    transaction_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    today_provider: TodayProvider | None = None,
) -> ValidatedDateQuery:
    """Validate exact/range query shape and, when configured, future policy.

    A range may be closed or one-sided. Exact-date and range criteria cannot be
    combined. No system clock is consulted unless ``today_provider`` is passed.
    """
    transaction_date = _require_date(transaction_date, "transaction_date")
    start_date = _require_date(start_date, "start_date")
    end_date = _require_date(end_date, "end_date")

    if transaction_date is not None and (
        start_date is not None or end_date is not None
    ):
        raise ValueError(
            "Exact transaction date cannot be combined with a date range."
        )
    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise ValueError("Start date cannot be after end date.")

    if today_provider is not None:
        today = _require_date(today_provider(), "Today provider output")
        assert today is not None
        for query_date in (transaction_date, start_date, end_date):
            if query_date is not None and query_date > today:
                raise FutureTransactionDateError(query_date, today)

    return ValidatedDateQuery(
        transaction_date=transaction_date,
        start_date=start_date,
        end_date=end_date,
    )
