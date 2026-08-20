"""Dataset intelligence exception hierarchy."""

from __future__ import annotations

from dfat.core.exceptions import DFATError


class DatasetError(DFATError):
    """Base exception for dataset intelligence failures."""


class DatasetNotFoundError(DatasetError):
    """Raised when a dataset record or path cannot be found."""


class DatasetValidationError(DatasetError):
    """Raised when dataset validation fails."""


class DatasetPreprocessingError(DatasetError):
    """Raised when preprocessing a dataset fails."""


class DatasetIndexingError(DatasetError):
    """Raised when dataset indexing fails."""


class UnsupportedDatasetFormatError(DatasetError):
    """Raised when a dataset format is unsupported."""


class DatasetCorruptedError(DatasetError):
    """Raised when a dataset appears corrupted or unreadable."""
