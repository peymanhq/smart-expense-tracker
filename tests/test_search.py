from datetime import date, datetime, timezone

import pytest

from search import (
    filter_transactions,
    find_transaction_by_display_id,
    search_transactions,
)
from transaction import Transaction


def make_transaction(
    display_number: int,
    transaction_date: date,
    *,
    transaction_type: str = "expense",
    category: str = "Food",
    account: str = "Cash",
    description: str = "Lunch",
    created_at: datetime | None = None,
) -> Transaction:
    return Transaction(
        id=f"uuid-{display_number}",
        display_id=f"T-{display_number:04d}",
        type=transaction_type,
        amount=float(display_number),
        category=category,
        account=account,
        description=description,
        transaction_date=transaction_date,
        created_at=created_at,
    )


def test_find_transaction_by_display_id_is_exact_and_normalized() -> None:
    transaction = make_transaction(1, date(2026, 7, 24))

    assert find_transaction_by_display_id([transaction], " t-0001 ") is transaction
    assert find_transaction_by_display_id([transaction], "T-000") is None
    assert find_transaction_by_display_id([transaction], "") is None


def test_exact_date_matches_only_financial_date_and_can_be_empty() -> None:
    previous = make_transaction(1, date(2026, 7, 19))
    matching = make_transaction(2, date(2026, 7, 20))
    later = make_transaction(3, date(2026, 7, 21))

    assert filter_transactions(
        [previous, matching, later],
        transaction_date=date(2026, 7, 20),
    ) == [matching]
    assert filter_transactions(
        [previous, matching, later],
        transaction_date=date(2026, 7, 18),
    ) == []


@pytest.mark.parametrize(
    ("criteria", "matching_value"),
    [
        ({"transaction_type": "expense"}, {}),
        ({"account": "Cash"}, {}),
        ({"category": "Food"}, {}),
    ],
)
def test_exact_date_composes_with_existing_filters(
    criteria,
    matching_value,
) -> None:
    matching = make_transaction(1, date(2026, 7, 20), **matching_value)
    wrong_date = make_transaction(2, date(2026, 7, 19), **matching_value)
    nonmatching = make_transaction(
        3,
        date(2026, 7, 20),
        transaction_type="income",
        category="Salary",
        account="Bank",
    )

    assert filter_transactions(
        [nonmatching, wrong_date, matching],
        transaction_date=date(2026, 7, 20),
        **criteria,
    ) == [matching]


def test_date_range_is_inclusive_same_day_multi_day_and_empty() -> None:
    start = make_transaction(1, date(2026, 7, 1))
    middle = make_transaction(2, date(2026, 7, 15))
    end = make_transaction(3, date(2026, 7, 31))
    outside = make_transaction(4, date(2026, 6, 30))
    transactions = [outside, start, middle, end]

    assert filter_transactions(
        transactions,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    ) == [end, middle, start]
    assert filter_transactions(
        transactions,
        start_date=date(2026, 7, 15),
        end_date=date(2026, 7, 15),
    ) == [middle]
    assert filter_transactions(
        transactions,
        start_date=date(2026, 7, 16),
        end_date=date(2026, 7, 30),
    ) == []


def test_one_sided_date_ranges_are_supported() -> None:
    earlier = make_transaction(1, date(2026, 7, 1))
    later = make_transaction(2, date(2026, 7, 20))

    assert filter_transactions(
        [earlier, later],
        start_date=date(2026, 7, 10),
    ) == [later]
    assert filter_transactions(
        [earlier, later],
        end_date=date(2026, 7, 10),
    ) == [earlier]


@pytest.mark.parametrize(
    "criteria",
    [
        {
            "start_date": date(2026, 7, 20),
            "end_date": date(2026, 7, 19),
        },
        {
            "transaction_date": date(2026, 7, 20),
            "start_date": date(2026, 7, 1),
        },
        {"transaction_date": "2026-07-20"},
        {"start_date": datetime(2026, 7, 20, tzinfo=timezone.utc)},
    ],
)
def test_invalid_or_ambiguous_date_criteria_are_rejected(criteria) -> None:
    with pytest.raises(ValueError):
        filter_transactions([], **criteria)


def test_all_filters_use_and_semantics() -> None:
    matching = make_transaction(
        1,
        date(2026, 7, 20),
        category="Food",
        account="Cash",
        description="Team lunch",
    )
    near_matches = [
        make_transaction(2, date(2026, 7, 20), category="Travel"),
        make_transaction(3, date(2026, 7, 20), account="Bank"),
        make_transaction(4, date(2026, 7, 20), description="Dinner"),
        make_transaction(
            5,
            date(2026, 7, 20),
            transaction_type="income",
        ),
        make_transaction(6, date(2026, 6, 30)),
    ]

    assert filter_transactions(
        [*near_matches, matching],
        transaction_type="EXPENSE",
        category="food",
        account="cash",
        description="lunch",
        text_query="team",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    ) == [matching]


def test_order_is_newest_date_then_numeric_display_id() -> None:
    old_high_id = make_transaction(10, date(2026, 7, 19))
    new_high_id = make_transaction(11, date(2026, 7, 20))
    new_low_id = make_transaction(2, date(2026, 7, 20))

    assert filter_transactions(
        [old_high_id, new_high_id, new_low_id],
    ) == [new_low_id, new_high_id, old_high_id]


def test_search_uses_transaction_date_not_record_timestamp() -> None:
    financial_match = make_transaction(
        1,
        date(2026, 7, 20),
        created_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    timestamp_match_only = make_transaction(
        2,
        date(2026, 7, 25),
        created_at=None,
    )

    assert search_transactions(
        [timestamp_match_only, financial_match],
        "",
        transaction_date=date(2026, 7, 20),
    ) == [financial_match]
