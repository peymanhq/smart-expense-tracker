"""Category model and name normalization helpers."""

from dataclasses import dataclass
import unicodedata


@dataclass
class Category:
    """Represents a standalone income or expense category."""

    id: str
    display_id: str
    name: str
    transaction_type: str
    is_active: bool = True


def canonicalize_category_name(name: str) -> str:
    """Return the persisted Unicode-normalized representation of a name."""
    return unicodedata.normalize("NFC", name)


def category_name_key(name: str) -> str:
    """Return the comparison key used for category-name uniqueness."""
    return canonicalize_category_name(name).casefold()
