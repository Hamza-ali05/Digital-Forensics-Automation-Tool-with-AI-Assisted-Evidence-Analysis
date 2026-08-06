"""Unit tests for JWTHandler token lifecycle."""

from __future__ import annotations

import pytest

from dfat.auth.exceptions import TokenExpiredError, TokenInvalidError
from dfat.auth.jwt_handler import JWTHandler


def test_create_and_decode_access_token(jwt_handler: JWTHandler) -> None:
    """Access token claims match the create arguments."""
    # Arrange / Act
    token = jwt_handler.create_access_token("user-1", "alice", "admin", jti="jti-1")
    claims = jwt_handler.decode_token(token)

    # Assert
    assert claims["sub"] == "user-1"
    assert claims["username"] == "alice"
    assert claims["role"] == "admin"
    assert claims["type"] == "access"
    assert claims["jti"] == "jti-1"


def test_create_and_decode_refresh_token(jwt_handler: JWTHandler) -> None:
    """Refresh tokens carry type=refresh."""
    # Arrange / Act
    token = jwt_handler.create_refresh_token("user-1", jti="jti-r")
    claims = jwt_handler.decode_token(token)

    # Assert
    assert claims["type"] == "refresh"
    assert claims["sub"] == "user-1"
    assert claims["jti"] == "jti-r"


def test_decode_expired_token() -> None:
    """Expired tokens raise TokenExpiredError."""
    # Arrange — craft a token whose exp is already in the past.
    from datetime import UTC, datetime, timedelta

    from jose import jwt

    now = datetime.now(UTC)
    payload = {
        "sub": "user-1",
        "username": "alice",
        "role": "admin",
        "type": "access",
        "jti": "jti-expired",
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),
    }
    token = jwt.encode(payload, "test-secret-key-not-for-production", algorithm="HS256")
    handler = JWTHandler(secret_key="test-secret-key-not-for-production")

    # Act / Assert
    with pytest.raises(TokenExpiredError):
        handler.decode_token(token)


def test_decode_invalid_token(jwt_handler: JWTHandler) -> None:
    """Malformed tokens raise TokenInvalidError."""
    # Arrange / Act / Assert
    with pytest.raises(TokenInvalidError):
        jwt_handler.decode_token("not-a-real-jwt")


def test_token_pair_different_jtis(jwt_handler: JWTHandler) -> None:
    """Access and refresh tokens in a pair share the same JTI."""
    # Arrange / Act
    access, refresh, jti = jwt_handler.create_token_pair("user-1", "alice", "analyst")
    access_claims = jwt_handler.decode_token(access)
    refresh_claims = jwt_handler.decode_token(refresh)

    # Assert
    assert access_claims["jti"] == jti
    assert refresh_claims["jti"] == jti
    assert access_claims["jti"] == refresh_claims["jti"]


def test_get_token_jti(jwt_handler: JWTHandler) -> None:
    """get_token_jti extracts JTI without requiring a full auth context."""
    # Arrange
    token = jwt_handler.create_access_token("user-1", "alice", "admin", jti="jti-extract")

    # Act
    extracted = jwt_handler.get_token_jti(token)

    # Assert
    assert extracted == "jti-extract"
