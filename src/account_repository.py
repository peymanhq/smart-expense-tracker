"""Account persistence contract."""

from typing import Protocol

from account import Account


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
