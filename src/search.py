"""Pure in-memory transaction search and filtering."""

from collections.abc import Iterable
from datetime import date

from date_policy import validate_date_query
from id_generator import parse_display_id
from transaction import Transaction


def _result_order(transaction: Transaction) -> tuple[int, int, str]:
    """Newest financial date first, then ascending numeric display ID."""
    display_number = parse_display_id(transaction.display_id)
    return (
        -transaction.transaction_date.toordinal(),
        display_number if display_number is not None else 2**63 - 1,
        transaction.display_id.casefold(),
    )


def find_transaction_by_display_id(
    transactions: Iterable[Transaction],
    display_id: str,
) -> Transaction | None:
    """Find one transaction by its exact, normalized display ID."""
    normalized_display_id = display_id.strip().casefold()
    if not normalized_display_id:
        return None

    return next(
        (
            transaction
            for transaction in transactions
            if transaction.display_id.strip().casefold() == normalized_display_id
        ),
        None,
    )


def search_transactions(
    transactions: Iterable[Transaction],
    search_key: str,
    *,
    transaction_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Transaction]:
    """Search all legacy text fields and optionally constrain financial dates."""
    search_key = search_key.strip().casefold()

    if not search_key and all(
        value is None for value in (transaction_date, start_date, end_date)
    ):
        return []

    return filter_transactions(
        transactions,
        text_query=search_key or None,
        transaction_date=transaction_date,
        start_date=start_date,
        end_date=end_date,
    )


def filter_transactions(
    transactions: Iterable[Transaction],
    *,
    transaction_type: str | None = None,
    category: str | None = None,
    account: str | None = None,
    description: str | None = None,
    text_query: str | None = None,
    transaction_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Transaction]:
    """Return transactions matching every supplied criterion.

    Ranges are inclusive and may be one-sided. Results are ordered by newest
    ``transaction_date`` first and ascending numeric display ID within a date.
    """
    dates = validate_date_query(
        transaction_date=transaction_date,
        start_date=start_date,
        end_date=end_date,
    )
    normalized_type = (
        transaction_type.strip().casefold()
        if transaction_type is not None
        else None
    )
    normalized_category = (
        category.strip().casefold() if category is not None else None
    )
    normalized_account = (
        account.strip().casefold() if account is not None else None
    )
    normalized_description = (
        description.strip().casefold() if description is not None else None
    )
    normalized_text = (
        text_query.strip().casefold() if text_query is not None else None
    )

    def matches(transaction: Transaction) -> bool:
        if (
            normalized_type is not None
            and transaction.type.casefold() != normalized_type
        ):
            return False
        if (
            normalized_category is not None
            and transaction.category.casefold() != normalized_category
        ):
            return False
        if (
            normalized_account is not None
            and transaction.account.casefold() != normalized_account
        ):
            return False
        if (
            normalized_description is not None
            and normalized_description
            not in transaction.description.casefold()
        ):
            return False
        if dates.transaction_date is not None and (
            transaction.transaction_date != dates.transaction_date
        ):
            return False
        if dates.start_date is not None and (
            transaction.transaction_date < dates.start_date
        ):
            return False
        if dates.end_date is not None and (
            transaction.transaction_date > dates.end_date
        ):
            return False
        if normalized_text is not None:
            searchable_values = (
                transaction.type,
                transaction.category,
                transaction.account,
                transaction.description,
                transaction.transaction_date.isoformat(),
                transaction.id,
                transaction.display_id,
            )
            if not any(
                normalized_text in value.casefold()
                for value in searchable_values
            ):
                return False
        return True

    return sorted(
        (transaction for transaction in transactions if matches(transaction)),
        key=_result_order,
    )
