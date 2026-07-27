"""Business operations for account management."""

from dataclasses import dataclass, replace
from uuid import UUID

from account import (
    Account,
    account_name_key,
    canonicalize_account_name,
)
from account_repository import (
    AccountRepository,
    AccountRepositoryConflictError,
    AccountRepositoryNotFoundError,
    AccountRepositoryRecordChangedError,
)
from id_generator import generate_account_id, parse_account_display_id
from validators import validate_required_text


@dataclass(frozen=True)
class AccountOperationResult:
    """Outcome returned by a mutating account operation."""

    success: bool
    message: str
    account: Account | None = None


def _has_duplicate_active_name(
    accounts: list[Account],
    name: str,
    *,
    excluded_account: Account | None = None,
) -> bool:
    normalized_name = account_name_key(name)
    return any(
        account != excluded_account
        and account.is_active
        and account_name_key(account.name) == normalized_name
        for account in accounts
    )


class AccountService:
    """Apply Account business rules through an injected repository."""

    def __init__(self, repository: AccountRepository) -> None:
        self._repository = repository

    def list_accounts(self, *, active_only: bool = False) -> list[Account]:
        """Return Accounts in ascending numeric display-ID order."""
        accounts = self._repository.list_all()
        if active_only:
            accounts = [account for account in accounts if account.is_active]
        return sorted(
            accounts,
            key=lambda account: (
                parse_account_display_id(account.display_id) or 0
            ),
        )

    def get_account_by_id(self, account_id: str) -> Account | None:
        """Return an active or inactive Account by canonical internal UUID."""
        if not isinstance(account_id, str):
            return None
        try:
            parsed_id = UUID(account_id)
        except (ValueError, AttributeError):
            return None
        if str(parsed_id) != account_id:
            return None
        return self._repository.get_by_id(account_id)

    def get_account_by_display_id(
        self,
        display_id: str,
    ) -> Account | None:
        """Return an Account by normalized display ID."""
        if not isinstance(display_id, str):
            return None
        return self._repository.get_by_display_id(display_id)

    def add_account(self, name: str) -> AccountOperationResult:
        """Validate and persist a new Account."""
        try:
            cleaned_name = canonicalize_account_name(
                validate_required_text(name, "Account name")
            )
        except ValueError as error:
            return AccountOperationResult(False, str(error))

        if _has_duplicate_active_name(
            self._repository.list_all(),
            cleaned_name,
        ):
            return AccountOperationResult(
                False,
                "An active account with this name already exists.",
            )
        try:
            account = self._repository.create(
                generate_account_id(),
                cleaned_name,
            )
        except AccountRepositoryConflictError:
            return AccountOperationResult(
                False,
                "An active account with this name already exists.",
            )
        return AccountOperationResult(
            True,
            "Account added successfully.",
            account,
        )

    def rename_account(
        self,
        display_id: str,
        new_name: str,
    ) -> AccountOperationResult:
        """Rename the Account matching a normalized display ID."""
        while True:
            account = self.get_account_by_display_id(display_id)
            if account is None:
                return AccountOperationResult(False, "Account not found.")
            try:
                cleaned_name = canonicalize_account_name(
                    validate_required_text(new_name, "Account name")
                )
            except ValueError as error:
                return AccountOperationResult(False, str(error), account)

            if account.is_active and _has_duplicate_active_name(
                self._repository.list_all(),
                cleaned_name,
                excluded_account=account,
            ):
                return AccountOperationResult(
                    False,
                    "An active account with this name already exists.",
                    account,
                )
            try:
                renamed = self._repository.replace(
                    account,
                    replace(account, name=cleaned_name),
                )
            except AccountRepositoryRecordChangedError:
                continue
            except AccountRepositoryNotFoundError:
                return AccountOperationResult(False, "Account not found.")
            except AccountRepositoryConflictError:
                return AccountOperationResult(
                    False,
                    "An active account with this name already exists.",
                    account,
                )
            return AccountOperationResult(
                True,
                "Account renamed successfully.",
                renamed,
            )

    def deactivate_account(
        self,
        display_id: str,
    ) -> AccountOperationResult:
        """Deactivate the Account matching a normalized display ID."""
        while True:
            account = self.get_account_by_display_id(display_id)
            if account is None:
                return AccountOperationResult(False, "Account not found.")
            if not account.is_active:
                return AccountOperationResult(
                    False,
                    "Account is already inactive.",
                    account,
                )
            try:
                deactivated = self._repository.replace(
                    account,
                    replace(account, is_active=False),
                )
            except AccountRepositoryRecordChangedError:
                continue
            except AccountRepositoryNotFoundError:
                return AccountOperationResult(False, "Account not found.")
            return AccountOperationResult(
                True,
                "Account deactivated successfully.",
                deactivated,
            )

    def activate_account(
        self,
        display_id: str,
    ) -> AccountOperationResult:
        """Activate the Account matching a normalized display ID."""
        while True:
            account = self.get_account_by_display_id(display_id)
            if account is None:
                return AccountOperationResult(False, "Account not found.")
            if account.is_active:
                return AccountOperationResult(
                    False,
                    "Account is already active.",
                    account,
                )
            if _has_duplicate_active_name(
                self._repository.list_all(),
                account.name,
                excluded_account=account,
            ):
                return AccountOperationResult(
                    False,
                    "An active account with this name already exists.",
                    account,
                )
            try:
                activated = self._repository.replace(
                    account,
                    replace(account, is_active=True),
                )
            except AccountRepositoryRecordChangedError:
                continue
            except AccountRepositoryNotFoundError:
                return AccountOperationResult(False, "Account not found.")
            except AccountRepositoryConflictError:
                return AccountOperationResult(
                    False,
                    "An active account with this name already exists.",
                    account,
                )
            return AccountOperationResult(
                True,
                "Account activated successfully.",
                activated,
            )


def list_accounts(
    repository: AccountRepository,
    *,
    active_only: bool = False,
) -> list[Account]:
    return AccountService(repository).list_accounts(active_only=active_only)


def get_account_by_id(
    account_id: str,
    repository: AccountRepository,
) -> Account | None:
    return AccountService(repository).get_account_by_id(account_id)


def get_account_by_display_id(
    display_id: str,
    repository: AccountRepository,
) -> Account | None:
    return AccountService(repository).get_account_by_display_id(display_id)


def add_account(
    name: str,
    repository: AccountRepository,
) -> AccountOperationResult:
    return AccountService(repository).add_account(name)


def rename_account(
    display_id: str,
    new_name: str,
    repository: AccountRepository,
) -> AccountOperationResult:
    return AccountService(repository).rename_account(display_id, new_name)


def deactivate_account(
    display_id: str,
    repository: AccountRepository,
) -> AccountOperationResult:
    return AccountService(repository).deactivate_account(display_id)


def activate_account(
    display_id: str,
    repository: AccountRepository,
) -> AccountOperationResult:
    return AccountService(repository).activate_account(display_id)
