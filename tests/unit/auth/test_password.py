"""Unit tests for password hashing and strength validation."""

from __future__ import annotations

from dfat.auth.password import PasswordHasher, validate_password_strength


def test_hash_and_verify_correct_password(password_hasher: PasswordHasher) -> None:
    """Hashed passwords verify successfully for the original plaintext."""
    # Arrange
    password = "C0mpl3x!Pass#123"

    # Act
    hashed = password_hasher.hash_password(password)

    # Assert
    assert hashed != password
    assert password_hasher.verify_password(password, hashed) is True


def test_verify_incorrect_password(password_hasher: PasswordHasher) -> None:
    """Incorrect passwords return False without raising."""
    # Arrange
    hashed = password_hasher.hash_password("C0mpl3x!Pass#123")

    # Act
    result = password_hasher.verify_password("wrong-password!!", hashed)

    # Assert
    assert result is False


def test_validate_strong_password() -> None:
    """A complex password meeting all rules is accepted."""
    # Arrange / Act
    valid, failures = validate_password_strength("C0mpl3x!Pass#123")

    # Assert
    assert valid is True
    assert failures == []


def test_validate_weak_password_too_short() -> None:
    """Passwords shorter than the minimum length are rejected."""
    # Arrange / Act
    valid, failures = validate_password_strength("Ab1!")

    # Assert
    assert valid is False
    assert any("at least" in message for message in failures)


def test_validate_weak_password_no_special_char() -> None:
    """Passwords without a special character are rejected."""
    # Arrange / Act
    valid, failures = validate_password_strength("ComplexPass1234")

    # Assert
    assert valid is False
    assert any("special" in message.lower() for message in failures)


def test_validate_weak_password_missing_classes() -> None:
    """Passwords missing upper, lower, or digit classes are rejected."""
    # Arrange / Act
    no_upper, f1 = validate_password_strength("complexpass1!")
    no_lower, f2 = validate_password_strength("COMPLEXPASS1!")
    no_digit, f3 = validate_password_strength("ComplexPass!!")

    # Assert
    assert no_upper is False and any("uppercase" in m for m in f1)
    assert no_lower is False and any("lowercase" in m for m in f2)
    assert no_digit is False and any("digit" in m for m in f3)


def test_needs_rehash_bcrypt(password_hasher: PasswordHasher) -> None:
    """A bcrypt-identified hash should be flagged for rehash to Argon2."""
    # Arrange — synthesise a bcrypt-looking hash identifier for needs_update.
    # Avoid hashing via passlib bcrypt (incompatible with newer bcrypt backends).
    bcrypt_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G2oY.placeholder"

    # Act
    needs = password_hasher.needs_rehash(bcrypt_hash)

    # Assert — invalid/legacy bcrypt hashes are treated as needing upgrade
    assert needs is True
