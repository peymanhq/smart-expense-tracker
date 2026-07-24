import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

import account_storage
from account import Account
from account_storage import (
    get_next_account_display_id,
    load_accounts,
    save_accounts,
)
from json_storage import StorageError


@pytest.fixture
def account_paths(tmp_path: Path) -> tuple[Path, Path]:
    return (
        tmp_path / "nested" / "accounts.json",
        tmp_path / "nested" / "accounts_state.json",
    )


def make_account(
    display_id: str = "A-0001",
    *,
    is_active: bool = True,
) -> Account:
    return Account(
        id=str(uuid5(NAMESPACE_URL, display_id)),
        display_id=display_id,
        name="Cash",
        is_active=is_active,
    )


def test_save_accounts_persists_single_atomic_document(
    account_paths: tuple[Path, Path],
) -> None:
    account = make_account()

    save_accounts([account], *account_paths)

    raw_accounts = json.loads(account_paths[0].read_text(encoding="utf-8"))
    assert raw_accounts == {
        "metadata": {"next_display_id": 2},
        "accounts": [
            {
                "id": str(uuid5(NAMESPACE_URL, "A-0001")),
                "display_id": "A-0001",
                "name": "Cash",
                "is_active": True,
            }
        ],
    }
    assert not account_paths[1].exists()


def test_load_accounts(account_paths: tuple[Path, Path]) -> None:
    accounts = [make_account(), make_account("A-0002", is_active=False)]
    save_accounts(accounts, *account_paths)

    assert load_accounts(account_paths[0]) == accounts


def test_missing_and_empty_accounts_file_load_as_empty(
    account_paths: tuple[Path, Path],
) -> None:
    assert load_accounts(account_paths[0]) == []

    account_paths[0].parent.mkdir(parents=True)
    account_paths[0].write_text(" \n", encoding="utf-8")
    assert load_accounts(account_paths[0]) == []


def test_malformed_account_json_raises_without_changing_file(
    account_paths: tuple[Path, Path],
) -> None:
    malformed = '[{"id":'
    account_paths[0].parent.mkdir(parents=True)
    account_paths[0].write_text(malformed, encoding="utf-8")

    with pytest.raises(StorageError, match="malformed JSON"):
        load_accounts(account_paths[0])

    assert account_paths[0].read_text(encoding="utf-8") == malformed


def test_invalid_utf8_raises_controlled_storage_error(
    account_paths: tuple[Path, Path],
) -> None:
    account_paths[0].parent.mkdir(parents=True)
    account_paths[0].write_bytes(b"\xff")

    with pytest.raises(StorageError, match="Could not read account data"):
        load_accounts(account_paths[0])


@pytest.mark.parametrize(
    "invalid_document, expected_message",
    [
        (42, "JSON object or a legacy JSON list"),
        ({}, "exactly metadata and accounts"),
        (
            {"metadata": {"next_display_id": True}, "accounts": []},
            "positive integer",
        ),
        (
            {
                "metadata": {"next_display_id": 1},
                "accounts": [make_account().__dict__],
            },
            "behind stored account IDs",
        ),
    ],
)
def test_invalid_account_document_structure_raises_storage_error(
    account_paths: tuple[Path, Path],
    invalid_document,
    expected_message,
) -> None:
    account_paths[0].parent.mkdir(parents=True)
    account_paths[0].write_text(
        json.dumps(invalid_document),
        encoding="utf-8",
    )

    with pytest.raises(StorageError, match=expected_message):
        load_accounts(account_paths[0])


def test_lock_setup_failure_raises_controlled_storage_error(
    account_paths: tuple[Path, Path],
    monkeypatch,
) -> None:
    original_mkdir = Path.mkdir

    def fail_account_directory(path, *args, **kwargs) -> None:
        if path == account_paths[0].parent:
            raise OSError("permission denied")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_account_directory)

    with pytest.raises(StorageError, match="Could not lock account data"):
        with account_storage.account_file_lock(account_paths[0]):
            pass


def test_persisted_state_prevents_display_id_reuse_when_list_shrinks(
    account_paths: tuple[Path, Path],
) -> None:
    save_accounts([make_account("A-0003")], *account_paths)
    save_accounts([], *account_paths)

    assert get_next_account_display_id(*account_paths) == "A-0004"


def test_legacy_list_and_state_migrate_on_next_save(
    account_paths: tuple[Path, Path],
) -> None:
    account_paths[0].parent.mkdir(parents=True)
    account_paths[0].write_text(
        json.dumps([make_account("A-0003").__dict__]),
        encoding="utf-8",
    )
    account_paths[1].write_text(
        json.dumps({"next_display_id": 7}),
        encoding="utf-8",
    )

    assert get_next_account_display_id(*account_paths) == "A-0007"
    accounts = load_accounts(account_paths[0])
    save_accounts(accounts, *account_paths)

    migrated = json.loads(account_paths[0].read_text(encoding="utf-8"))
    assert migrated["metadata"] == {"next_display_id": 7}
    assert migrated["accounts"][0]["display_id"] == "A-0003"


def test_malformed_legacy_state_raises_controlled_storage_error(
    account_paths: tuple[Path, Path],
) -> None:
    account_paths[0].parent.mkdir(parents=True)
    account_paths[0].write_text(
        json.dumps([make_account().__dict__]),
        encoding="utf-8",
    )
    account_paths[1].write_text("[]", encoding="utf-8")

    with pytest.raises(StorageError, match="Legacy account display-ID state"):
        get_next_account_display_id(*account_paths)


def test_failed_account_write_preserves_complete_previous_document(
    account_paths: tuple[Path, Path],
    monkeypatch,
) -> None:
    save_accounts([make_account()], *account_paths)
    previous_content = account_paths[0].read_text(encoding="utf-8")

    def fail_write(data_file, data, *, data_name) -> None:
        raise StorageError("simulated account write failure")

    monkeypatch.setattr(account_storage, "write_json_atomic", fail_write)

    second_account = make_account("A-0002")
    second_account.name = "Bank"
    with pytest.raises(StorageError, match="simulated account write failure"):
        save_accounts([make_account(), second_account], *account_paths)

    assert account_paths[0].read_text(encoding="utf-8") == previous_content
    assert get_next_account_display_id(*account_paths) == "A-0002"


@pytest.mark.parametrize(
    "invalid_field, invalid_value, expected_message",
    [
        ("id", "not-a-uuid", "valid UUID"),
        ("display_id", "a-0001", "canonical format"),
        ("name", None, "non-empty text"),
        ("name", "  Cash", "outer whitespace"),
        ("is_active", "false", "boolean"),
    ],
)
def test_invalid_account_fields_raise_controlled_storage_error(
    account_paths: tuple[Path, Path],
    invalid_field,
    invalid_value,
    expected_message,
) -> None:
    raw_account = make_account().__dict__.copy()
    raw_account[invalid_field] = invalid_value
    account_paths[0].parent.mkdir(parents=True)
    account_paths[0].write_text(
        json.dumps([raw_account]),
        encoding="utf-8",
    )

    with pytest.raises(StorageError, match=expected_message):
        load_accounts(account_paths[0])


@pytest.mark.parametrize("duplicate_field", ["id", "display_id"])
def test_duplicate_account_identifiers_raise_storage_error(
    account_paths: tuple[Path, Path],
    duplicate_field: str,
) -> None:
    first = make_account()
    second = make_account("A-0002")
    second.name = "Bank"
    setattr(second, duplicate_field, getattr(first, duplicate_field))
    account_paths[0].parent.mkdir(parents=True)
    account_paths[0].write_text(
        json.dumps([first.__dict__, second.__dict__]),
        encoding="utf-8",
    )

    with pytest.raises(StorageError, match=f"Duplicate account {duplicate_field}"):
        load_accounts(account_paths[0])


def test_unicode_equivalent_active_names_raise_storage_error(
    account_paths: tuple[Path, Path],
) -> None:
    first = make_account()
    first.name = "Café"
    second = make_account("A-0002")
    second.name = "Cafe\u0301"
    account_paths[0].parent.mkdir(parents=True)
    account_paths[0].write_text(
        json.dumps([first.__dict__, second.__dict__]),
        encoding="utf-8",
    )

    with pytest.raises(StorageError, match="Duplicate active account name"):
        load_accounts(account_paths[0])
