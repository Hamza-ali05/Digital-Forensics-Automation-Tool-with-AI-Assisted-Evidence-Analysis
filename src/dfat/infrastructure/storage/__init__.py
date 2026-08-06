"""DFAT Storage — Local read-only evidence access and secure output workspace."""

from dfat.infrastructure.storage.local_storage import LocalFileStorage
from dfat.infrastructure.storage.secure_storage import SecureStorage

__all__ = [
    "LocalFileStorage",
    "SecureStorage",
]
