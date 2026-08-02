"""Business operations for standalone category management."""

from dataclasses import dataclass, replace
from uuid import UUID

from category import Category, canonicalize_category_name, category_name_key
from category_repository import (
    CategoryRepository,
    CategoryRepositoryConflictError,
    CategoryRepositoryNotFoundError,
    CategoryRepositoryRecordChangedError,
)
from id_generator import generate_category_id, parse_category_display_id
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
        category != excluded_category
        and category.is_active
        and category.transaction_type == transaction_type
        and category_name_key(category.name) == normalized_name
        for category in categories
    )


class CategoryService:
    """Apply Category business rules through an injected repository."""

    def __init__(self, repository: CategoryRepository) -> None:
        self._repository = repository

    def list_categories(
        self,
        *,
        active_only: bool = False,
        transaction_type: str | None = None,
    ) -> list[Category]:
        """Return filtered Categories in deterministic order."""
        cleaned_type = None
        if transaction_type is not None:
            cleaned_type = _clean_transaction_type(transaction_type)
            if cleaned_type is None:
                raise ValueError("Invalid transaction type.")

        categories = self._repository.list_all()
        if active_only:
            categories = [
                category for category in categories if category.is_active
            ]
        if cleaned_type is not None:
            categories = [
                category
                for category in categories
                if category.transaction_type == cleaned_type
            ]
        return sorted(
            categories,
            key=lambda category: (
                category.transaction_type,
                parse_category_display_id(category.display_id) or 0,
            ),
        )

    def get_category_by_id(self, category_id: str) -> Category | None:
        """Return a Category by canonical internal UUID."""
        if not isinstance(category_id, str):
            return None
        try:
            parsed_id = UUID(category_id)
        except (ValueError, AttributeError):
            return None
        if str(parsed_id) != category_id:
            return None
        return self._repository.get_by_id(category_id)

    def get_category_by_display_id(
        self,
        display_id: str,
    ) -> Category | None:
        """Return a Category by normalized display ID."""
        if not isinstance(display_id, str):
            return None
        return self._repository.get_by_display_id(display_id)

    def add_category(
        self,
        name: str,
        transaction_type: str,
    ) -> CategoryOperationResult:
        """Validate and persist a new Category."""
        try:
            cleaned_name = _clean_category_name(name)
        except ValueError as error:
            return CategoryOperationResult(False, str(error))
        cleaned_type = _clean_transaction_type(transaction_type)
        if cleaned_type is None:
            return CategoryOperationResult(False, "Invalid transaction type.")

        if _has_duplicate_active_name(
            self._repository.list_all(),
            cleaned_name,
            cleaned_type,
        ):
            return CategoryOperationResult(
                False,
                "An active category with this name and transaction type "
                "already exists.",
            )
        try:
            category = self._repository.create(
                generate_category_id(),
                cleaned_name,
                cleaned_type,
            )
        except CategoryRepositoryConflictError:
            return CategoryOperationResult(
                False,
                "An active category with this name and transaction type "
                "already exists.",
            )
        return CategoryOperationResult(
            True,
            "Category added successfully.",
            category,
        )

    def rename_category(
        self,
        display_id: str,
        new_name: str,
    ) -> CategoryOperationResult:
        """Rename the Category matching a normalized display ID."""
        while True:
            category = self.get_category_by_display_id(display_id)
            if category is None:
                return CategoryOperationResult(False, "Category not found.")
            try:
                cleaned_name = _clean_category_name(new_name)
            except ValueError as error:
                return CategoryOperationResult(False, str(error), category)

            if category.is_active and _has_duplicate_active_name(
                self._repository.list_all(),
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
            try:
                renamed = self._repository.replace(
                    category,
                    replace(category, name=cleaned_name),
                )
            except CategoryRepositoryRecordChangedError:
                continue
            except CategoryRepositoryNotFoundError:
                return CategoryOperationResult(False, "Category not found.")
            except CategoryRepositoryConflictError:
                return CategoryOperationResult(
                    False,
                    "An active category with this name and transaction type "
                    "already exists.",
                    category,
                )
            return CategoryOperationResult(
                True,
                "Category renamed successfully.",
                renamed,
            )

    def activate_category(
        self,
        display_id: str,
    ) -> CategoryOperationResult:
        """Activate the Category matching a normalized display ID."""
        while True:
            category = self.get_category_by_display_id(display_id)
            if category is None:
                return CategoryOperationResult(False, "Category not found.")
            if category.is_active:
                return CategoryOperationResult(
                    False,
                    "Category is already active.",
                    category,
                )
            if _has_duplicate_active_name(
                self._repository.list_all(),
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
            try:
                activated = self._repository.replace(
                    category,
                    replace(category, is_active=True),
                )
            except CategoryRepositoryRecordChangedError:
                continue
            except CategoryRepositoryNotFoundError:
                return CategoryOperationResult(False, "Category not found.")
            except CategoryRepositoryConflictError:
                return CategoryOperationResult(
                    False,
                    "An active category with this name and transaction type "
                    "already exists.",
                    category,
                )
            return CategoryOperationResult(
                True,
                "Category activated successfully.",
                activated,
            )

    def deactivate_category(
        self,
        display_id: str,
    ) -> CategoryOperationResult:
        """Deactivate the Category matching a normalized display ID."""
        while True:
            category = self.get_category_by_display_id(display_id)
            if category is None:
                return CategoryOperationResult(False, "Category not found.")
            if not category.is_active:
                return CategoryOperationResult(
                    False,
                    "Category is already inactive.",
                    category,
                )
            try:
                deactivated = self._repository.replace(
                    category,
                    replace(category, is_active=False),
                )
            except CategoryRepositoryRecordChangedError:
                continue
            except CategoryRepositoryNotFoundError:
                return CategoryOperationResult(False, "Category not found.")
            return CategoryOperationResult(
                True,
                "Category deactivated successfully.",
                deactivated,
            )


def list_categories(
    repository: CategoryRepository,
    *,
    active_only: bool = False,
    transaction_type: str | None = None,
) -> list[Category]:
    return CategoryService(repository).list_categories(
        active_only=active_only,
        transaction_type=transaction_type,
    )


def get_category_by_id(
    category_id: str,
    repository: CategoryRepository,
) -> Category | None:
    return CategoryService(repository).get_category_by_id(category_id)


def get_category_by_display_id(
    display_id: str,
    repository: CategoryRepository,
) -> Category | None:
    return CategoryService(repository).get_category_by_display_id(display_id)


def add_category(
    name: str,
    transaction_type: str,
    repository: CategoryRepository,
) -> CategoryOperationResult:
    return CategoryService(repository).add_category(name, transaction_type)


def rename_category(
    display_id: str,
    new_name: str,
    repository: CategoryRepository,
) -> CategoryOperationResult:
    return CategoryService(repository).rename_category(display_id, new_name)


def activate_category(
    display_id: str,
    repository: CategoryRepository,
) -> CategoryOperationResult:
    return CategoryService(repository).activate_category(display_id)


def deactivate_category(
    display_id: str,
    repository: CategoryRepository,
) -> CategoryOperationResult:
    return CategoryService(repository).deactivate_category(display_id)
