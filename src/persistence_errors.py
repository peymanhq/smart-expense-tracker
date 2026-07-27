"""Backend-neutral persistence errors."""


class StorageError(Exception):
    """Raised when application data cannot be safely loaded or saved."""
