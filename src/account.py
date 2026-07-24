"""Account model."""

from dataclasses import dataclass
import unicodedata


@dataclass
class Account:
    """Represents a user-managed financial account."""

    id: str
    display_id: str
    name: str
    is_active: bool = True


def canonicalize_account_name(name: str) -> str:
    """Return the persisted Unicode-normalized representation of a name."""
    return unicodedata.normalize("NFC", name)


def account_name_key(name: str) -> str:
    """Return the comparison key used for account-name uniqueness."""
    return canonicalize_account_name(name).casefold()
