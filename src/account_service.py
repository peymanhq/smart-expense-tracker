"""Business operations for account management."""

from dataclasses import dataclass, replace
from pathlib import Path

from account import (
    Account,
    account_name_key,
    canonicalize_account_name,
)
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
    generate_account_id,
    parse_account_display_id,
)
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
        account is not excluded_account
        and account.is_active
        and account_name_key(account.name) == normalized_name
        for account in accounts
    )


def _find_account_by_display_id(
    accounts: list[Account],
    display_id: str,
) -> Account | None:
    if not isinstance(display_id, str):
        return None
    number = parse_account_display_id(display_id)
    if number is None:
        return None
    normalized_display_id = generate_account_display_id(number)
    return next(
        (
            account
            for account in accounts
            if account.display_id == normalized_display_id
        ),
        None,
    )


def add_account(
    name: str,
    accounts_file: Path = ACCOUNTS_FILE,
    state_file: Path = ACCOUNT_STATE_FILE,
) -> AccountOperationResult:
    """Validate, create, and persist an account."""
    try:
        cleaned_name = canonicalize_account_name(
            validate_required_text(name, "Account name")
        )
    except ValueError as error:
        return AccountOperationResult(False, str(error))

    with account_file_lock(accounts_file):
        accounts = load_accounts(accounts_file)
        if _has_duplicate_active_name(accounts, cleaned_name):
            return AccountOperationResult(
                False,
                "An active account with this name already exists.",
            )

        account = Account(
            id=generate_account_id(),
            display_id=get_next_account_display_id(accounts_file, state_file),
            name=cleaned_name,
        )
        accounts.append(account)
        save_accounts(accounts, accounts_file, state_file)
    return AccountOperationResult(True, "Account added successfully.", account)


def rename_account(
    display_id: str,
    new_name: str,
    accounts_file: Path = ACCOUNTS_FILE,
    state_file: Path = ACCOUNT_STATE_FILE,
) -> AccountOperationResult:
    """Rename the account matching a normalized display ID."""
    with account_file_lock(accounts_file):
        accounts = load_accounts(accounts_file)
        account = _find_account_by_display_id(accounts, display_id)
        if account is None:
            return AccountOperationResult(False, "Account not found.")

        try:
            cleaned_name = canonicalize_account_name(
                validate_required_text(new_name, "Account name")
            )
        except ValueError as error:
            return AccountOperationResult(False, str(error), account)

        if account.is_active and _has_duplicate_active_name(
            accounts,
            cleaned_name,
            excluded_account=account,
        ):
            return AccountOperationResult(
                False,
                "An active account with this name already exists.",
                account,
            )

        renamed_account = replace(account, name=cleaned_name)
        accounts[accounts.index(account)] = renamed_account
        save_accounts(accounts, accounts_file, state_file)
        return AccountOperationResult(
            True,
            "Account renamed successfully.",
            renamed_account,
        )


def deactivate_account(
    display_id: str,
    accounts_file: Path = ACCOUNTS_FILE,
    state_file: Path = ACCOUNT_STATE_FILE,
) -> AccountOperationResult:
    """Deactivate the account matching a normalized display ID."""
    with account_file_lock(accounts_file):
        accounts = load_accounts(accounts_file)
        account = _find_account_by_display_id(accounts, display_id)
        if account is None:
            return AccountOperationResult(False, "Account not found.")
        if not account.is_active:
            return AccountOperationResult(
                False,
                "Account is already inactive.",
                account,
            )

        deactivated_account = replace(account, is_active=False)
        accounts[accounts.index(account)] = deactivated_account
        save_accounts(accounts, accounts_file, state_file)
        return AccountOperationResult(
            True,
            "Account deactivated successfully.",
            deactivated_account,
        )


def activate_account(
    display_id: str,
    accounts_file: Path = ACCOUNTS_FILE,
    state_file: Path = ACCOUNT_STATE_FILE,
) -> AccountOperationResult:
    """Activate the account matching a normalized display ID."""
    with account_file_lock(accounts_file):
        accounts = load_accounts(accounts_file)
        account = _find_account_by_display_id(accounts, display_id)
        if account is None:
            return AccountOperationResult(False, "Account not found.")
        if account.is_active:
            return AccountOperationResult(
                False,
                "Account is already active.",
                account,
            )
        if _has_duplicate_active_name(
            accounts,
            account.name,
            excluded_account=account,
        ):
            return AccountOperationResult(
                False,
                "An active account with this name already exists.",
                account,
            )

        activated_account = replace(account, is_active=True)
        accounts[accounts.index(account)] = activated_account
        save_accounts(accounts, accounts_file, state_file)
        return AccountOperationResult(
            True,
            "Account activated successfully.",
            activated_account,
        )
