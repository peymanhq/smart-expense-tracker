"""JSON persistence for the Smart Expense Tracker."""

import json
import os
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import local
from typing import Any, Iterator

from id_generator import (
    calculate_next_display_id,
    generate_display_id,
    parse_display_id,
)
from json_storage import StorageError, write_json_atomic
from search import find_transaction_by_display_id
from transaction import Transaction
from validators import (
    parse_utc_datetime,
    validate_optional_uuid,
    validate_transaction_date,
)

DATA_FILE = Path("data") / "transactions.json"
TRANSACTION_SCHEMA_VERSION = 3
_LOCK_STATE = local()


def _lock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _unlock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def transaction_file_lock(
    data_file: Path | None = None,
) -> Iterator[None]:
    """Serialize complete transaction read-modify-write operations."""
    target_file = DATA_FILE if data_file is None else data_file
    lock_path = target_file.with_name(f".{target_file.name}.lock")
    depths = getattr(_LOCK_STATE, "depths", None)
    if depths is None:
        depths = {}
        _LOCK_STATE.depths = depths

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_key = str(lock_path.resolve())
    except OSError as error:
        raise StorageError(f"Could not lock transaction data: {error}") from error

    if lock_key in depths:
        depths[lock_key] += 1
        try:
            yield
        finally:
            depths[lock_key] -= 1
        return

    try:
        with lock_path.open("a+b") as lock_file:
            _lock_file(lock_file)
            depths[lock_key] = 1
            try:
                yield
            finally:
                del depths[lock_key]
                _unlock_file(lock_file)
    except OSError as error:
        raise StorageError(f"Could not lock transaction data: {error}") from error


def _empty_document() -> dict[str, Any]:
    return {
        "schema_version": TRANSACTION_SCHEMA_VERSION,
        "metadata": {"next_display_id": 1},
        "transactions": [],
    }


def _normalize_document(raw_data: Any) -> dict[str, Any]:
    if isinstance(raw_data, list):
        transaction_data = raw_data
        next_display_id = calculate_next_display_id(
            [
                item.get("display_id", "")
                for item in transaction_data
                if isinstance(item, dict)
                and isinstance(item.get("display_id", ""), str)
            ]
        )
        return {
            "schema_version": 1,
            "metadata": {"next_display_id": next_display_id},
            "transactions": transaction_data,
        }

    if not isinstance(raw_data, dict):
        raise StorageError("Transaction data must be a JSON object or legacy list.")

    metadata = raw_data.get("metadata")
    transaction_data = raw_data.get("transactions")
    if not isinstance(metadata, dict) or not isinstance(transaction_data, list):
        raise StorageError(
            "Transaction data must contain metadata and transactions sections."
        )

    schema_version = raw_data.get(
        "schema_version",
        metadata.get("schema_version", 1),
    )
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version < 1
    ):
        raise StorageError("Transaction schema_version must be a positive integer.")
    if schema_version > TRANSACTION_SCHEMA_VERSION:
        raise StorageError(
            f"Unsupported transaction schema version {schema_version}; "
            f"this application supports up to version {TRANSACTION_SCHEMA_VERSION}."
        )

    if (
        "schema_version" in raw_data
        and "schema_version" in metadata
        and raw_data["schema_version"] != metadata["schema_version"]
    ):
        raise StorageError("Conflicting transaction schema_version values.")

    next_display_id = metadata.get("next_display_id")
    if (
        not isinstance(next_display_id, int)
        or isinstance(next_display_id, bool)
        or next_display_id < 1
    ):
        raise StorageError("metadata.next_display_id must be a positive integer.")

    return {
        "schema_version": schema_version,
        "metadata": {"next_display_id": next_display_id},
        "transactions": transaction_data,
    }


def _read_document(data_file: Path | None = None) -> dict[str, Any]:
    target_file = DATA_FILE if data_file is None else data_file
    if not target_file.exists():
        return _empty_document()

    try:
        content = target_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise StorageError(f"Could not read transaction data: {error}") from error

    if not content.strip():
        return _empty_document()

    try:
        return _normalize_document(json.loads(content))
    except json.JSONDecodeError as error:
        raise StorageError(
            f"Transaction data contains malformed JSON at line {error.lineno}, "
            f"column {error.colno}."
        ) from error


def _deserialize_transactions(document: dict[str, Any]) -> list[Transaction]:
    transaction_data = document["transactions"]
    if not all(isinstance(item, dict) for item in transaction_data):
        raise StorageError("Every transaction entry must be a JSON object.")

    transactions = []
    for index, item in enumerate(transaction_data):
        try:
            record = dict(item)
            legacy_date = record.pop("date", None)
            current_date = record.pop("transaction_date", None)

            if legacy_date is None and current_date is None:
                raise ValueError("transaction_date is required.")

            parsed_legacy_date = (
                validate_transaction_date(legacy_date)
                if legacy_date is not None
                else None
            )
            parsed_current_date = (
                validate_transaction_date(current_date)
                if current_date is not None
                else None
            )
            if (
                parsed_legacy_date is not None
                and parsed_current_date is not None
                and parsed_legacy_date != parsed_current_date
            ):
                raise ValueError("date and transaction_date conflict.")

            record["transaction_date"] = (
                parsed_current_date or parsed_legacy_date
            )
            record["created_at"] = parse_utc_datetime(
                record.get("created_at"),
                "created_at",
            )
            record["updated_at"] = parse_utc_datetime(
                record.get("updated_at"),
                "updated_at",
            )
            record["account_id"] = validate_optional_uuid(
                record.get("account_id"),
                "account_id",
            )
            record["category_id"] = validate_optional_uuid(
                record.get("category_id"),
                "category_id",
            )
            transaction = Transaction(**record)
            text_fields = {
                "id": transaction.id,
                "display_id": transaction.display_id,
                "type": transaction.type,
                "category": transaction.category,
                "account": transaction.account,
                "description": transaction.description,
            }
            for field_name, value in text_fields.items():
                if not isinstance(value, str):
                    raise ValueError(f"{field_name} must be text.")
            if (
                not isinstance(transaction.amount, (int, float))
                or isinstance(transaction.amount, bool)
            ):
                raise ValueError("amount must be numeric.")
            transactions.append(transaction)
        except (TypeError, ValueError) as error:
            raise StorageError(
                f"Transaction record at index {index} is invalid: {error}"
            ) from error

    transaction_ids: set[str] = set()
    display_ids: set[str] = set()
    for transaction in transactions:
        if transaction.id in transaction_ids:
            raise StorageError(f"Duplicate transaction id: {transaction.id}.")
        if transaction.display_id in display_ids:
            raise StorageError(
                f"Duplicate transaction display_id: {transaction.display_id}."
            )
        transaction_ids.add(transaction.id)
        display_ids.add(transaction.display_id)

    derived_next_display_id = calculate_next_display_id(
        [transaction.display_id for transaction in transactions]
    )
    if document["metadata"]["next_display_id"] < derived_next_display_id:
        raise StorageError(
            "metadata.next_display_id is behind stored transaction IDs."
        )

    return transactions


def _serialize_transaction(transaction: Transaction) -> dict[str, Any]:
    return {
        "id": transaction.id,
        "display_id": transaction.display_id,
        "type": transaction.type,
        "amount": transaction.amount,
        "category": transaction.category,
        "category_id": transaction.category_id,
        "account": transaction.account,
        "account_id": transaction.account_id,
        "description": transaction.description,
        "transaction_date": transaction.transaction_date.isoformat(),
        "created_at": (
            transaction.created_at.isoformat()
            if transaction.created_at is not None
            else None
        ),
        "updated_at": (
            transaction.updated_at.isoformat()
            if transaction.updated_at is not None
            else None
        ),
    }


def _write_document(
    document: dict[str, Any],
    data_file: Path | None = None,
) -> None:
    # Mutations validate their complete candidate document before the atomic
    # replacement so duplicate identities or regressed counter state can never
    # be persisted and deferred to a later read.
    _deserialize_transactions(document)
    target_file = DATA_FILE if data_file is None else data_file
    current_document = {
        "schema_version": TRANSACTION_SCHEMA_VERSION,
        "metadata": document["metadata"],
        "transactions": document["transactions"],
    }
    write_json_atomic(
        target_file,
        current_document,
        data_name="transaction data",
    )


def get_next_display_id() -> str:
    """Return the next persisted display ID without consuming it."""
    document = _read_document()
    _deserialize_transactions(document)
    return generate_display_id(document["metadata"]["next_display_id"])


def load_transactions() -> list[Transaction]:
    """Load all transactions, treating missing and empty files as empty."""
    return _deserialize_transactions(_read_document())


def save_transaction(transaction: Transaction) -> None:
    """Append one transaction and advance persistent display ID state."""
    with transaction_file_lock():
        document = _read_document()
        transactions = _deserialize_transactions(document)
        transactions.append(transaction)
        document["transactions"] = [
            _serialize_transaction(item) for item in transactions
        ]

        assigned_number = parse_display_id(transaction.display_id)
        if assigned_number is not None:
            document["metadata"]["next_display_id"] = max(
                document["metadata"]["next_display_id"],
                assigned_number + 1,
            )

        _write_document(document)


def save_transactions(transactions: list[Transaction]) -> None:
    """Save a complete transaction list while retaining monotonic ID state."""
    with transaction_file_lock():
        document = _read_document()
        _deserialize_transactions(document)
        document["transactions"] = [
            _serialize_transaction(transaction) for transaction in transactions
        ]
        _write_document(document)


def delete_transaction(display_id: str) -> bool:
    with transaction_file_lock():
        document = _read_document()
        transactions = _deserialize_transactions(document)
        transaction = find_transaction_by_display_id(transactions, display_id)
        if transaction is None:
            return False

        transactions.remove(transaction)
        document["transactions"] = [
            _serialize_transaction(item) for item in transactions
        ]
        _write_document(document)
        return True


def update_transaction(
    display_id: str,
    updated_transaction: Transaction,
) -> bool:
    with transaction_file_lock():
        document = _read_document()
        transactions = _deserialize_transactions(document)
        existing_transaction = find_transaction_by_display_id(
            transactions,
            display_id,
        )
        if existing_transaction is None:
            return False

        preserved_transaction = replace(
            updated_transaction,
            id=existing_transaction.id,
            display_id=existing_transaction.display_id,
            created_at=existing_transaction.created_at,
        )
        index = transactions.index(existing_transaction)
        transactions[index] = preserved_transaction
        document["transactions"] = [
            _serialize_transaction(item) for item in transactions
        ]
        _write_document(document)
        return True
