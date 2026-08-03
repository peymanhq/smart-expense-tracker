import json
import os
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import storage
from storage import StorageError
from transaction import Transaction


ACCOUNT_ID = "123e4567-e89b-12d3-a456-426614174000"
CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174001"


@pytest.fixture(autouse=True)
def use_temporary_data_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "DATA_FILE", tmp_path / "data" / "transactions.json")


def make_transaction(
    display_id: str = "T-0001",
    transaction_id: str = "uuid-1",
) -> Transaction:
    return Transaction(
        id=transaction_id,
        display_id=display_id,
        type="expense",
        amount=10.0,
        category="Food",
        account="Cash",
        description="Lunch",
        transaction_date=date(2026, 7, 24),
        created_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
    )


def make_record(**overrides) -> dict:
    record = {
        "id": "uuid-1",
        "display_id": "T-0001",
        "type": "expense",
        "amount": 10.0,
        "category": "Food",
        "account": "Cash",
        "description": "Lunch",
        "transaction_date": "2026-07-24",
        "created_at": "2026-07-24T09:15:00+00:00",
        "updated_at": "2026-07-24T09:15:00+00:00",
    }
    record.update(overrides)
    return record


def write_raw_document(data) -> str:
    content = json.dumps(data, indent=2)
    storage.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    storage.DATA_FILE.write_text(content, encoding="utf-8")
    return content


def test_save_and_load_transactions_with_metadata() -> None:
    transaction = make_transaction()
    storage.save_transaction(transaction)

    assert storage.load_transactions() == [transaction]
    document = json.loads(storage.DATA_FILE.read_text(encoding="utf-8"))
    assert document["metadata"]["next_display_id"] == 2
    assert document["schema_version"] == 4
    assert document["transactions"][0]["amount"] == "10"
    assert document["transactions"][0]["id"] == "uuid-1"
    assert document["transactions"][0]["account_id"] is None
    assert document["transactions"][0]["category_id"] is None


def test_schema_four_reference_ids_round_trip() -> None:
    transaction = replace(
        make_transaction(),
        account_id=ACCOUNT_ID,
        category_id=CATEGORY_ID,
    )

    storage.save_transaction(transaction)

    document = json.loads(storage.DATA_FILE.read_text(encoding="utf-8"))
    stored = document["transactions"][0]
    assert document["schema_version"] == 4
    assert stored["category"] == "Food"
    assert stored["category_id"] == CATEGORY_ID
    assert stored["account"] == "Cash"
    assert stored["account_id"] == ACCOUNT_ID
    assert storage.load_transactions() == [transaction]


def test_schema_three_explicit_null_references_load_as_none() -> None:
    write_raw_document(
        {
            "schema_version": 3,
            "metadata": {"next_display_id": 2},
            "transactions": [
                make_record(account_id=None, category_id=None),
            ],
        }
    )

    loaded = storage.load_transactions()[0]

    assert loaded.account_id is None
    assert loaded.category_id is None


def test_date_and_utc_timestamp_serialization_round_trip() -> None:
    transaction = make_transaction()

    storage.save_transaction(transaction)

    document = json.loads(storage.DATA_FILE.read_text(encoding="utf-8"))
    stored = document["transactions"][0]
    assert stored["transaction_date"] == "2026-07-24"
    assert stored["created_at"] == "2026-07-24T09:15:00+00:00"
    assert stored["updated_at"] == "2026-07-24T09:15:00+00:00"
    assert storage.load_transactions() == [transaction]


def test_legacy_date_and_missing_timestamps_load_without_invention() -> None:
    record = make_record()
    record["date"] = record.pop("transaction_date")
    record.pop("created_at")
    record.pop("updated_at")
    write_raw_document([record])

    loaded = storage.load_transactions()[0]

    assert loaded.transaction_date == date(2026, 7, 24)
    assert loaded.created_at is None
    assert loaded.updated_at is None
    assert loaded.id == "uuid-1"
    assert loaded.display_id == "T-0001"
    assert loaded.account_id is None
    assert loaded.category_id is None


def test_current_transaction_date_field_loads() -> None:
    write_raw_document(
        {
            "schema_version": 2,
            "metadata": {"next_display_id": 8},
            "transactions": [make_record(id="preserved-uuid", display_id="T-0007")],
        }
    )

    loaded = storage.load_transactions()[0]

    assert loaded.transaction_date == date(2026, 7, 24)
    assert loaded.id == "preserved-uuid"
    assert loaded.display_id == "T-0007"
    assert loaded.account_id is None
    assert loaded.category_id is None
    assert storage.get_next_display_id() == "T-0008"


def test_matching_legacy_and_current_date_fields_load() -> None:
    write_raw_document(
        {
            "metadata": {"next_display_id": 2},
            "transactions": [make_record(date="2026-07-24")],
        }
    )

    assert storage.load_transactions()[0].transaction_date == date(2026, 7, 24)


def test_conflicting_legacy_and_current_date_fields_raise() -> None:
    write_raw_document(
        {
            "metadata": {"next_display_id": 2},
            "transactions": [make_record(date="2026-07-23")],
        }
    )

    with pytest.raises(StorageError, match="date and transaction_date conflict"):
        storage.load_transactions()


def test_missing_schema_version_is_legacy_version_one() -> None:
    original = write_raw_document(
        {
            "metadata": {"next_display_id": 2},
            "transactions": [make_record()],
        }
    )

    loaded = storage.load_transactions()[0]
    assert loaded.id == "uuid-1"
    assert loaded.account_id is None
    assert loaded.category_id is None
    assert storage.DATA_FILE.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("schema_version", [1, 2, 3])
def test_supported_schema_versions_load_missing_references_without_rewriting(
    schema_version: int,
) -> None:
    original = write_raw_document(
        {
            "schema_version": schema_version,
            "metadata": {"next_display_id": 2},
            "transactions": [make_record()],
        }
    )

    loaded = storage.load_transactions()[0]

    assert loaded.account_id is None
    assert loaded.category_id is None
    assert storage.DATA_FILE.read_text(encoding="utf-8") == original


def test_unsupported_future_schema_version_raises_without_writing() -> None:
    original = write_raw_document(
        {
            "schema_version": 5,
            "metadata": {"next_display_id": 2},
            "transactions": [make_record()],
        }
    )

    with pytest.raises(StorageError, match="Unsupported transaction schema version 5"):
        storage.load_transactions()

    assert storage.DATA_FILE.read_text(encoding="utf-8") == original


def test_read_only_load_does_not_modify_current_document() -> None:
    original = write_raw_document(
        {
            "schema_version": 2,
            "metadata": {"next_display_id": 2},
            "transactions": [make_record()],
        }
    )

    assert len(storage.load_transactions()) == 1

    assert storage.DATA_FILE.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("field", ["account_id", "category_id"])
@pytest.mark.parametrize(
    "value",
    [
        True,
        42,
        [],
        {},
        "",
        "not-a-uuid",
        f" {ACCOUNT_ID}",
        f"{{{ACCOUNT_ID}}}",
    ],
)
def test_invalid_persisted_reference_ids_are_rejected(
    field: str,
    value: object,
) -> None:
    original = write_raw_document(
        {
            "schema_version": 3,
            "metadata": {"next_display_id": 2},
            "transactions": [make_record(**{field: value})],
        }
    )

    with pytest.raises(StorageError, match=f"{field}.*canonical UUID"):
        storage.load_transactions()

    assert storage.DATA_FILE.read_text(encoding="utf-8") == original


def test_deleted_display_id_is_not_reused() -> None:
    storage.save_transaction(make_transaction("T-0001", "uuid-1"))
    storage.save_transaction(make_transaction("T-0002", "uuid-2"))
    storage.save_transaction(make_transaction("T-0003", "uuid-3"))

    assert storage.delete_transaction("T-0003") is True
    assert storage.get_next_display_id() == "T-0004"

    storage.save_transaction(make_transaction(storage.get_next_display_id(), "uuid-4"))
    assert [item.display_id for item in storage.load_transactions()] == [
        "T-0001",
        "T-0002",
        "T-0004",
    ]


def test_save_transaction_rejects_duplicate_identity_without_writing() -> None:
    original = make_transaction()
    storage.save_transaction(original)
    previous_content = storage.DATA_FILE.read_text(encoding="utf-8")

    with pytest.raises(StorageError, match="Duplicate transaction id"):
        storage.save_transaction(
            make_transaction("T-0002", transaction_id=original.id)
        )

    assert storage.DATA_FILE.read_text(encoding="utf-8") == previous_content


def test_bulk_save_rejects_counter_regression_without_writing() -> None:
    storage.save_transaction(make_transaction())
    previous_content = storage.DATA_FILE.read_text(encoding="utf-8")

    with pytest.raises(
        StorageError,
        match="next_display_id is behind stored transaction IDs",
    ):
        storage.save_transactions(
            [
                make_transaction(),
                make_transaction("T-0002", "uuid-2"),
            ]
        )

    assert storage.DATA_FILE.read_text(encoding="utf-8") == previous_content


def test_update_existing_preserves_uuid_and_display_id() -> None:
    original = make_transaction()
    storage.save_transaction(original)
    replacement = replace(
        original,
        id="different-uuid",
        display_id="T-9999",
        amount=25.0,
    )

    assert storage.update_transaction(" t-0001 ", replacement) is True
    updated = storage.load_transactions()[0]
    assert updated.id == original.id
    assert updated.display_id == original.display_id
    assert updated.amount == 25.0


def test_update_missing_returns_false_without_writing(monkeypatch) -> None:
    write_called = False

    def fail_if_called(document) -> None:
        nonlocal write_called
        write_called = True

    monkeypatch.setattr(storage, "_write_document", fail_if_called)

    assert storage.update_transaction("T-9999", make_transaction()) is False
    assert write_called is False


def test_update_propagates_storage_errors(monkeypatch) -> None:
    storage.save_transaction(make_transaction())

    def fail_write(document) -> None:
        raise StorageError("disk full")

    monkeypatch.setattr(storage, "_write_document", fail_write)

    with pytest.raises(StorageError, match="disk full"):
        storage.update_transaction("T-0001", make_transaction())


def test_delete_transaction() -> None:
    storage.save_transaction(make_transaction())

    assert storage.delete_transaction(" t-0001 ") is True
    assert storage.load_transactions() == []
    assert storage.delete_transaction("T-0001") is False


def test_missing_and_empty_files_load_as_empty() -> None:
    assert storage.load_transactions() == []

    storage.DATA_FILE.parent.mkdir(parents=True)
    storage.DATA_FILE.write_text(" \n", encoding="utf-8")
    assert storage.load_transactions() == []
    assert storage.get_next_display_id() == "T-0001"


def test_malformed_json_raises_without_changing_file() -> None:
    malformed = '{"transactions": ['
    storage.DATA_FILE.parent.mkdir(parents=True)
    storage.DATA_FILE.write_text(malformed, encoding="utf-8")

    with pytest.raises(StorageError, match="malformed JSON"):
        storage.load_transactions()

    assert storage.DATA_FILE.read_text(encoding="utf-8") == malformed


def test_invalid_utf8_raises_controlled_storage_error() -> None:
    storage.DATA_FILE.parent.mkdir(parents=True)
    storage.DATA_FILE.write_bytes(b"\xff")

    with pytest.raises(StorageError, match="Could not read transaction data"):
        storage.load_transactions()


@pytest.mark.parametrize(
    "data",
    [
        42,
        {},
        {"metadata": {}, "transactions": []},
        {"metadata": {"next_display_id": 1}, "transactions": ["bad"]},
    ],
)
def test_invalid_json_structure_raises(data) -> None:
    storage.DATA_FILE.parent.mkdir(parents=True)
    storage.DATA_FILE.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(StorageError):
        storage.load_transactions()


def test_legacy_list_loads_and_migrates_on_next_write() -> None:
    legacy_transaction = make_transaction("T-0007", "legacy-uuid")
    legacy_record = make_record(
        id=legacy_transaction.id,
        display_id=legacy_transaction.display_id,
    )
    legacy_record["date"] = legacy_record.pop("transaction_date")
    legacy_record.pop("created_at")
    legacy_record.pop("updated_at")
    storage.DATA_FILE.parent.mkdir(parents=True)
    storage.DATA_FILE.write_text(
        json.dumps([legacy_record]),
        encoding="utf-8",
    )

    loaded_legacy = storage.load_transactions()[0]
    assert loaded_legacy.id == legacy_transaction.id
    assert loaded_legacy.created_at is None
    assert loaded_legacy.updated_at is None
    assert storage.get_next_display_id() == "T-0008"

    storage.save_transaction(make_transaction("T-0008", "new-uuid"))
    migrated = json.loads(storage.DATA_FILE.read_text(encoding="utf-8"))
    assert migrated["metadata"]["next_display_id"] == 9
    assert migrated["schema_version"] == 4
    assert len(migrated["transactions"]) == 2
    assert "date" not in migrated["transactions"][0]
    assert migrated["transactions"][0]["transaction_date"] == "2026-07-24"
    assert migrated["transactions"][0]["created_at"] is None
    assert migrated["transactions"][0]["updated_at"] is None
    assert migrated["transactions"][0]["account_id"] is None
    assert migrated["transactions"][0]["category_id"] is None
    assert migrated["transactions"][0]["amount"] == "10"


def test_schema_two_mutation_upgrades_with_explicit_null_references() -> None:
    write_raw_document(
        {
            "schema_version": 2,
            "metadata": {"next_display_id": 2},
            "transactions": [make_record()],
        }
    )

    storage.save_transaction(make_transaction("T-0002", "uuid-2"))

    migrated = json.loads(storage.DATA_FILE.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 4
    assert migrated["metadata"]["next_display_id"] == 3
    assert len(migrated["transactions"]) == 2
    assert all(
        transaction["account_id"] is None
        and transaction["category_id"] is None
        for transaction in migrated["transactions"]
    )
    assert all(
        transaction["amount"] == "10"
        for transaction in migrated["transactions"]
    )


def test_schema_four_decimal_text_round_trips_exactly() -> None:
    transaction = replace(make_transaction(), amount=Decimal("0.10"))

    storage.save_transaction(transaction)

    document = json.loads(storage.DATA_FILE.read_text(encoding="utf-8"))
    assert document["transactions"][0]["amount"] == "0.1"
    assert storage.load_transactions()[0].amount == Decimal("0.1")


@pytest.mark.parametrize("amount", [10.0, "10.0", "01", "1e1"])
def test_schema_four_rejects_noncanonical_amounts(amount: object) -> None:
    original = write_raw_document(
        {
            "schema_version": 4,
            "metadata": {"next_display_id": 2},
            "transactions": [make_record(amount=amount)],
        }
    )

    with pytest.raises(StorageError, match="canonical decimal text"):
        storage.load_transactions()

    assert storage.DATA_FILE.read_text(encoding="utf-8") == original


def test_failed_mutation_does_not_partially_migrate_schema_two(
    monkeypatch,
) -> None:
    original = write_raw_document(
        {
            "schema_version": 2,
            "metadata": {"next_display_id": 2},
            "transactions": [make_record()],
        }
    )

    def fail_replace(source, destination) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(StorageError, match="simulated replace failure"):
        storage.save_transaction(make_transaction("T-0002", "uuid-2"))

    assert storage.DATA_FILE.read_text(encoding="utf-8") == original


def test_failed_atomic_replace_preserves_previous_file(monkeypatch) -> None:
    storage.save_transaction(make_transaction())
    previous_content = storage.DATA_FILE.read_text(encoding="utf-8")

    def fail_replace(source, destination) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(StorageError, match="simulated replace failure"):
        storage.save_transaction(make_transaction("T-0002", "uuid-2"))

    assert storage.DATA_FILE.read_text(encoding="utf-8") == previous_content
    assert list(storage.DATA_FILE.parent.glob("*.tmp")) == []


def test_directory_creation_failure_raises_controlled_storage_error(
    monkeypatch,
) -> None:
    original_mkdir = Path.mkdir

    def fail_data_directory(path, *args, **kwargs) -> None:
        if path == storage.DATA_FILE.parent:
            raise OSError("permission denied")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_data_directory)

    with pytest.raises(
        StorageError,
        match="Could not (?:lock|save) transaction data",
    ):
        storage.save_transaction(make_transaction())
