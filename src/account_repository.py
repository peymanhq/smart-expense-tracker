"""Account persistence contract and JSON-backed implementation."""

from dataclasses import replace
from pathlib import Path
from typing import Protocol

from account import Account, account_name_key
from account_storage import (
    ACCOUNT_STATE_FILE,
    ACCOUNTS_FILE,
    account_file_lock,
    get_next_account_display_id,
    load_accounts,
    save_accounts,
)
from id_generator import (
    generate_account_display_id,
    parse_account_display_id,
)


class AccountRepositoryConflictError(ValueError):
    """Raised when an Account mutation conflicts with persisted state."""


class AccountRepositoryNotFoundError(LookupError):
    """Raised when an Account disappears before replacement."""


class AccountRepositoryRecordChangedError(AccountRepositoryConflictError):
    """Raised when an Account changed after it was read by the service."""


class AccountRepository(Protocol):
    """Persistence operations required by Account business workflows."""

    def list_all(self) -> list[Account]:
        """Return all Accounts as a detached collection."""
        ...

    def get_by_id(self, account_id: str) -> Account | None:
        """Return one Account by its internal UUID."""
        ...

    def get_by_display_id(self, display_id: str) -> Account | None:
        """Return one Account by normalized display ID."""
        ...

    def create(self, account_id: str, name: str) -> Account:
        """Atomically allocate a display ID and persist an active Account."""
        ...

    def replace(self, expected: Account, replacement: Account) -> Account:
        """Atomically replace an unchanged persisted Account."""
        ...


def _find_by_display_id(
    accounts: list[Account],
    display_id: str,
) -> Account | None:
    if not isinstance(display_id, str):
        return None
    number = parse_account_display_id(display_id)
    if number is None:
        return None
    normalized = generate_account_display_id(number)
    return next(
        (
            account
            for account in accounts
            if account.display_id == normalized
        ),
        None,
    )


def _has_duplicate_active_name(
    accounts: list[Account],
    candidate: Account,
) -> bool:
    candidate_key = account_name_key(candidate.name)
    return candidate.is_active and any(
        account.id != candidate.id
        and account.is_active
        and account_name_key(account.name) == candidate_key
        for account in accounts
    )


class JsonAccountRepository:
    """Account repository backed by the existing JSON document."""

    def __init__(
        self,
        accounts_file: Path = ACCOUNTS_FILE,
        state_file: Path = ACCOUNT_STATE_FILE,
    ) -> None:
        self._accounts_file = accounts_file
        self._state_file = state_file

    def list_all(self) -> list[Account]:
        return list(load_accounts(self._accounts_file))

    def get_by_id(self, account_id: str) -> Account | None:
        return next(
            (
                account
                for account in self.list_all()
                if account.id == account_id
            ),
            None,
        )

    def get_by_display_id(self, display_id: str) -> Account | None:
        return _find_by_display_id(self.list_all(), display_id)

    def create(self, account_id: str, name: str) -> Account:
        with account_file_lock(self._accounts_file):
            accounts = load_accounts(self._accounts_file)
            account = Account(
                id=account_id,
                display_id=get_next_account_display_id(
                    self._accounts_file,
                    self._state_file,
                ),
                name=name,
            )
            if _has_duplicate_active_name(accounts, account):
                raise AccountRepositoryConflictError(
                    "An active Account with this name already exists."
                )
            accounts.append(account)
            save_accounts(
                accounts,
                self._accounts_file,
                self._state_file,
            )
            return account

    def replace(self, expected: Account, replacement: Account) -> Account:
        with account_file_lock(self._accounts_file):
            accounts = load_accounts(self._accounts_file)
            current = next(
                (
                    account
                    for account in accounts
                    if account.id == expected.id
                ),
                None,
            )
            if current is None:
                raise AccountRepositoryNotFoundError(expected.id)
            if current != expected:
                raise AccountRepositoryRecordChangedError(expected.id)

            persisted = replace(
                replacement,
                id=current.id,
                display_id=current.display_id,
            )
            if _has_duplicate_active_name(accounts, persisted):
                raise AccountRepositoryConflictError(
                    "An active Account with this name already exists."
                )
            accounts[accounts.index(current)] = persisted
            save_accounts(
                accounts,
                self._accounts_file,
                self._state_file,
            )
            return persisted
