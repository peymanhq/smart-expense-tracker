import pytest

from id_generator import (
    calculate_next_account_display_id,
    calculate_next_category_display_id,
    calculate_next_display_id,
    generate_account_display_id,
    generate_category_display_id,
    generate_display_id,
    parse_account_display_id,
    parse_category_display_id,
    parse_display_id,
)


def test_display_id_generation_and_parsing() -> None:
    assert generate_display_id(1) == "T-0001"
    assert generate_display_id(42) == "T-0042"
    assert parse_display_id(" t-0042 ") == 42
    assert parse_display_id("invalid") is None


def test_legacy_next_display_id_uses_highest_valid_id() -> None:
    assert calculate_next_display_id(["T-0002", "invalid", "T-0007"]) == 8


def test_display_id_number_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        generate_display_id(0)


def test_account_display_id_generation_parsing_and_sequence() -> None:
    assert generate_account_display_id(1) == "A-0001"
    assert parse_account_display_id(" a-0042 ") == 42
    assert parse_account_display_id("T-0042") is None
    assert calculate_next_account_display_id(["A-0002", "A-0007"]) == 8


def test_category_display_id_generation_parsing_and_sequence() -> None:
    assert generate_category_display_id(1) == "C-0001"
    assert parse_category_display_id(" c-0042 ") == 42
    assert parse_category_display_id("A-0042") is None
    assert calculate_next_category_display_id(["C-0002", "C-0007"]) == 8
