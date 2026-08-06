"""Secure password hashing and strength validation."""

from __future__ import annotations

import re

from passlib.context import CryptContext


class PasswordHasher:
    """Hash and verify passwords using Argon2 with bcrypt fallback."""

    def __init__(self, algorithm: str = "argon2") -> None:
        """Initialise the password hasher.

        Args:
            algorithm: Preferred scheme (``argon2`` or ``bcrypt``).
        """
        schemes = ["argon2", "bcrypt"]
        if algorithm == "bcrypt":
            schemes = ["bcrypt", "argon2"]
        elif algorithm != "argon2":
            raise ValueError(f"Unsupported password algorithm: {algorithm}")
        self._algorithm = algorithm
        self._context = CryptContext(
            schemes=schemes,
            default=schemes[0],
            deprecated=["bcrypt"] if schemes[0] == "argon2" else ["argon2"],
        )

    def hash_password(self, plain_password: str) -> str:
        """Hash a plaintext password.

        Args:
            plain_password: Password in clear text.

        Returns:
            Encoded password hash string.
        """
        return self._context.hash(plain_password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against a stored hash.

        Args:
            plain_password: Password in clear text.
            hashed_password: Previously hashed password.

        Returns:
            ``True`` on match; ``False`` on mismatch (never raises).
        """
        try:
            return bool(self._context.verify(plain_password, hashed_password))
        except Exception:  # noqa: BLE001
            return False

    def needs_rehash(self, hashed_password: str) -> bool:
        """Return whether a hash should be upgraded to the preferred scheme.

        Args:
            hashed_password: Previously hashed password.

        Returns:
            ``True`` if the hash uses a deprecated algorithm/parameters.
        """
        try:
            return bool(self._context.needs_update(hashed_password))
        except Exception:  # noqa: BLE001
            return True


def validate_password_strength(
    password: str,
    min_length: int = 12,
) -> tuple[bool, list[str]]:
    """Validate password complexity rules.

    Args:
        password: Candidate password.
        min_length: Minimum allowed length.

    Returns:
        Tuple of ``(is_valid, failure_messages)``.
    """
    failures: list[str] = []
    if len(password) < min_length:
        failures.append(f"Password must be at least {min_length} characters")
    if not re.search(r"[A-Z]", password):
        failures.append("Password must contain an uppercase letter")
    if not re.search(r"[a-z]", password):
        failures.append("Password must contain a lowercase letter")
    if not re.search(r"\d", password):
        failures.append("Password must contain a digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        failures.append("Password must contain a special character")
    return (len(failures) == 0, failures)
