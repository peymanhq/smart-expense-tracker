"""Category persistence contract and JSON-backed implementation."""

from dataclasses import replace
from pathlib import Path
from typing import Protocol

from category import Category, category_name_key
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
    parse_category_display_id,
)


class CategoryRepositoryConflictError(ValueError):
    """Raised when a Category mutation conflicts with persisted state."""


class CategoryRepositoryNotFoundError(LookupError):
    """Raised when a Category disappears before replacement."""


class CategoryRepositoryRecordChangedError(CategoryRepositoryConflictError):
    """Raised when a Category changed after it was read by the service."""


class CategoryRepository(Protocol):
    """Persistence operations required by Category business workflows."""

    def list_all(self) -> list[Category]:
        """Return all Categories as a detached collection."""
        ...

    def get_by_id(self, category_id: str) -> Category | None:
        """Return one Category by its internal UUID."""
        ...

    def get_by_display_id(self, display_id: str) -> Category | None:
        """Return one Category by normalized display ID."""
        ...

    def create(
        self,
        category_id: str,
        name: str,
        transaction_type: str,
    ) -> Category:
        """Atomically allocate a display ID and persist an active Category."""
        ...

    def replace(
        self,
        expected: Category,
        replacement: Category,
    ) -> Category:
        """Atomically replace an unchanged persisted Category."""
        ...


def _find_by_display_id(
    categories: list[Category],
    display_id: str,
) -> Category | None:
    if not isinstance(display_id, str):
        return None
    number = parse_category_display_id(display_id)
    if number is None:
        return None
    normalized = generate_category_display_id(number)
    return next(
        (
            category
            for category in categories
            if category.display_id == normalized
        ),
        None,
    )


def _has_duplicate_active_name(
    categories: list[Category],
    candidate: Category,
) -> bool:
    candidate_key = category_name_key(candidate.name)
    return candidate.is_active and any(
        category.id != candidate.id
        and category.is_active
        and category.transaction_type == candidate.transaction_type
        and category_name_key(category.name) == candidate_key
        for category in categories
    )


class JsonCategoryRepository:
    """Category repository backed by the existing JSON files."""

    def __init__(
        self,
        categories_file: Path = CATEGORIES_FILE,
        state_file: Path = CATEGORY_STATE_FILE,
    ) -> None:
        self._categories_file = categories_file
        self._state_file = state_file

    def list_all(self) -> list[Category]:
        return list(
            load_categories(
                self._categories_file,
                self._state_file,
            )
        )

    def get_by_id(self, category_id: str) -> Category | None:
        return next(
            (
                category
                for category in self.list_all()
                if category.id == category_id
            ),
            None,
        )

    def get_by_display_id(self, display_id: str) -> Category | None:
        return _find_by_display_id(self.list_all(), display_id)

    def create(
        self,
        category_id: str,
        name: str,
        transaction_type: str,
    ) -> Category:
        with category_file_lock(self._categories_file):
            categories = load_categories(
                self._categories_file,
                self._state_file,
            )
            category = Category(
                id=category_id,
                display_id=get_next_category_display_id(
                    self._categories_file,
                    self._state_file,
                ),
                name=name,
                transaction_type=transaction_type,
            )
            if _has_duplicate_active_name(categories, category):
                raise CategoryRepositoryConflictError(
                    "An active Category with this name and transaction type "
                    "already exists."
                )
            categories.append(category)
            save_categories(
                categories,
                self._categories_file,
                self._state_file,
            )
            return category

    def replace(
        self,
        expected: Category,
        replacement: Category,
    ) -> Category:
        with category_file_lock(self._categories_file):
            categories = load_categories(
                self._categories_file,
                self._state_file,
            )
            current = next(
                (
                    category
                    for category in categories
                    if category.id == expected.id
                ),
                None,
            )
            if current is None:
                raise CategoryRepositoryNotFoundError(expected.id)
            if current != expected:
                raise CategoryRepositoryRecordChangedError(expected.id)

            persisted = replace(
                replacement,
                id=current.id,
                display_id=current.display_id,
                transaction_type=current.transaction_type,
            )
            if _has_duplicate_active_name(categories, persisted):
                raise CategoryRepositoryConflictError(
                    "An active Category with this name and transaction type "
                    "already exists."
                )
            categories[categories.index(current)] = persisted
            save_categories(
                categories,
                self._categories_file,
                self._state_file,
            )
            return persisted
