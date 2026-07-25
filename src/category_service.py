"""Business operations for standalone category management."""

from dataclasses import dataclass, replace
from pathlib import Path

from category import Category, canonicalize_category_name, category_name_key
from category_storage import (
    CATEGORIES_FILE,
    CATEGORY_STATE_FILE,
    category_file_lock,
    get_next_category_display_id,
    load_categories,
    save_categories,
)
from id_generator import (
    generate_category_display_id,
    generate_category_id,
    parse_category_display_id,
)
from validators import validate_required_text


@dataclass(frozen=True)
class CategoryOperationResult:
    """Outcome returned by a mutating category operation."""

    success: bool
    message: str
    category: Category | None = None


def _clean_transaction_type(transaction_type: str) -> str | None:
    if not isinstance(transaction_type, str):
        return None
    cleaned = transaction_type.strip().lower()
    return cleaned if cleaned in {"income", "expense"} else None


def _clean_category_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Category name must be text.")
    return canonicalize_category_name(validate_required_text(name, "Category name"))


def _has_duplicate_active_name(
    categories: list[Category],
    name: str,
    transaction_type: str,
    *,
    excluded_category: Category | None = None,
) -> bool:
    normalized_name = category_name_key(name)
    return any(
        category is not excluded_category
        and category.is_active
        and category.transaction_type == transaction_type
        and category_name_key(category.name) == normalized_name
        for category in categories
    )


def _find_category_by_display_id(
    categories: list[Category],
    display_id: str,
) -> Category | None:
    if not isinstance(display_id, str):
        return None
    number = parse_category_display_id(display_id)
    if number is None:
        return None
    normalized_display_id = generate_category_display_id(number)
    return next(
        (
            category
            for category in categories
            if category.display_id == normalized_display_id
        ),
        None,
    )


def list_categories(
    categories_file: Path = CATEGORIES_FILE,
    state_file: Path = CATEGORY_STATE_FILE,
) -> list[Category]:
    """Return categories ordered by transaction type and display ID."""
    return sorted(
        load_categories(categories_file, state_file),
        key=lambda category: (
            category.transaction_type,
            parse_category_display_id(category.display_id) or 0,
        ),
    )


def add_category(
    name: str,
    transaction_type: str,
    categories_file: Path = CATEGORIES_FILE,
    state_file: Path = CATEGORY_STATE_FILE,
) -> CategoryOperationResult:
    """Validate, create, and persist a standalone category."""
    try:
        cleaned_name = _clean_category_name(name)
    except ValueError as error:
        return CategoryOperationResult(False, str(error))

    cleaned_type = _clean_transaction_type(transaction_type)
    if cleaned_type is None:
        return CategoryOperationResult(False, "Invalid transaction type.")

    with category_file_lock(categories_file):
        categories = load_categories(categories_file, state_file)
        if _has_duplicate_active_name(
            categories,
            cleaned_name,
            cleaned_type,
        ):
            return CategoryOperationResult(
                False,
                "An active category with this name and transaction type "
                "already exists.",
            )

        category = Category(
            id=generate_category_id(),
            display_id=get_next_category_display_id(
                categories_file,
                state_file,
            ),
            name=cleaned_name,
            transaction_type=cleaned_type,
        )
        categories.append(category)
        save_categories(categories, categories_file, state_file)
        return CategoryOperationResult(
            True,
            "Category added successfully.",
            category,
        )


def rename_category(
    display_id: str,
    new_name: str,
    categories_file: Path = CATEGORIES_FILE,
    state_file: Path = CATEGORY_STATE_FILE,
) -> CategoryOperationResult:
    """Rename the category matching a normalized exact display ID."""
    with category_file_lock(categories_file):
        categories = load_categories(categories_file, state_file)
        category = _find_category_by_display_id(categories, display_id)
        if category is None:
            return CategoryOperationResult(False, "Category not found.")

        try:
            cleaned_name = _clean_category_name(new_name)
        except ValueError as error:
            return CategoryOperationResult(False, str(error), category)

        if category.is_active and _has_duplicate_active_name(
            categories,
            cleaned_name,
            category.transaction_type,
            excluded_category=category,
        ):
            return CategoryOperationResult(
                False,
                "An active category with this name and transaction type "
                "already exists.",
                category,
            )

        renamed_category = replace(category, name=cleaned_name)
        categories[categories.index(category)] = renamed_category
        save_categories(categories, categories_file, state_file)
        return CategoryOperationResult(
            True,
            "Category renamed successfully.",
            renamed_category,
        )


def activate_category(
    display_id: str,
    categories_file: Path = CATEGORIES_FILE,
    state_file: Path = CATEGORY_STATE_FILE,
) -> CategoryOperationResult:
    """Activate the category matching a normalized exact display ID."""
    with category_file_lock(categories_file):
        categories = load_categories(categories_file, state_file)
        category = _find_category_by_display_id(categories, display_id)
        if category is None:
            return CategoryOperationResult(False, "Category not found.")
        if category.is_active:
            return CategoryOperationResult(
                False,
                "Category is already active.",
                category,
            )
        if _has_duplicate_active_name(
            categories,
            category.name,
            category.transaction_type,
            excluded_category=category,
        ):
            return CategoryOperationResult(
                False,
                "An active category with this name and transaction type "
                "already exists.",
                category,
            )

        activated_category = replace(category, is_active=True)
        categories[categories.index(category)] = activated_category
        save_categories(categories, categories_file, state_file)
        return CategoryOperationResult(
            True,
            "Category activated successfully.",
            activated_category,
        )


def deactivate_category(
    display_id: str,
    categories_file: Path = CATEGORIES_FILE,
    state_file: Path = CATEGORY_STATE_FILE,
) -> CategoryOperationResult:
    """Deactivate the category matching a normalized exact display ID."""
    with category_file_lock(categories_file):
        categories = load_categories(categories_file, state_file)
        category = _find_category_by_display_id(categories, display_id)
        if category is None:
            return CategoryOperationResult(False, "Category not found.")
        if not category.is_active:
            return CategoryOperationResult(
                False,
                "Category is already inactive.",
                category,
            )

        deactivated_category = replace(category, is_active=False)
        categories[categories.index(category)] = deactivated_category
        save_categories(categories, categories_file, state_file)
        return CategoryOperationResult(
            True,
            "Category deactivated successfully.",
            deactivated_category,
        )
