"""Category persistence contract."""

from typing import Protocol

from category import Category


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
