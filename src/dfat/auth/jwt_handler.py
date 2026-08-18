"""JWT access and refresh token handling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from dfat.auth.exceptions import TokenExpiredError, TokenInvalidError


class JWTHandler:
    """Create and validate local JWT access/refresh tokens."""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
        refresh_token_expire_days: int = 7,
    ) -> None:
        """Initialise the JWT handler.

        Args:
            secret_key: HMAC signing secret.
            algorithm: JWT signing algorithm.
            access_token_expire_minutes: Access token lifetime in minutes.
            refresh_token_expire_days: Refresh token lifetime in days.
        """
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_expire = timedelta(minutes=access_token_expire_minutes)
        self._refresh_expire = timedelta(days=refresh_token_expire_days)
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

    def create_access_token(
        self,
        user_id: str,
        username: str,
        role: str,
        jti: Optional[str] = None,
    ) -> str:
        """Create a signed access token.

        Args:
            user_id: Subject user identifier.
            username: Username claim.
            role: Role name claim.
            jti: Optional JWT ID (generated when omitted).

        Returns:
            Encoded JWT string.
        """
        now = datetime.now(UTC)
        payload = {
            "sub": user_id,
            "username": username,
            "role": role,
            "type": "access",
            "jti": jti or str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + self._access_expire).timestamp()),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_refresh_token(
        self,
        user_id: str,
        jti: Optional[str] = None,
    ) -> str:
        """Create a signed refresh token.

        Args:
            user_id: Subject user identifier.
            jti: Optional JWT ID (generated when omitted).

        Returns:
            Encoded JWT string.
        """
        now = datetime.now(UTC)
        payload = {
            "sub": user_id,
            "type": "refresh",
            "jti": jti or str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + self._refresh_expire).timestamp()),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        """Decode and validate a JWT.

        Args:
            token: Encoded JWT string.

        Returns:
            Decoded claims dictionary.

        Raises:
            TokenExpiredError: If the token has expired.
            TokenInvalidError: If the token is malformed or invalid.
        """
        try:
            header = jwt.get_unverified_header(token)
            algorithm = str(header.get("alg") or "")
            if not algorithm or algorithm.lower() == "none":
                raise TokenInvalidError(
                    "Token algorithm is not allowed",
                    context={"alg": algorithm or "missing"},
                )
            if algorithm != self._algorithm:
                raise TokenInvalidError(
                    "Token algorithm is not allowed",
                    context={"alg": algorithm},
                )
            return jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
        except (TokenExpiredError, TokenInvalidError):
            raise
        except ExpiredSignatureError as exc:
            token_type = "access"
            try:
                unverified = jwt.get_unverified_claims(token)
                token_type = str(unverified.get("type", "access"))
            except Exception:  # noqa: BLE001
                pass
            raise TokenExpiredError(token_type=token_type) from exc
        except JWTError as exc:
            raise TokenInvalidError(
                "Token is invalid",
                context={"error": str(exc)},
            ) from exc

    def get_token_jti(self, token: str) -> str:
        """Extract the JTI claim without signature validation.

        Args:
            token: Encoded JWT string.

        Returns:
            JWT ID claim.

        Raises:
            TokenInvalidError: If the JTI claim is missing or unreadable.
        """
        try:
            claims = jwt.get_unverified_claims(token)
        except JWTError as exc:
            raise TokenInvalidError(
                "Unable to read token JTI",
                context={"error": str(exc)},
            ) from exc
        jti = claims.get("jti")
        if not jti:
            raise TokenInvalidError("Token missing jti claim")
        return str(jti)

    def create_token_pair(
        self,
        user_id: str,
        username: str,
        role: str,
    ) -> tuple[str, str, str]:
        """Create an access/refresh token pair sharing one JTI.

        Args:
            user_id: Subject user identifier.
            username: Username claim.
            role: Role name claim.

        Returns:
            Tuple of ``(access_token, refresh_token, jti)``.
        """
        jti = str(uuid4())
        access = self.create_access_token(user_id, username, role, jti=jti)
        refresh = self.create_refresh_token(user_id, jti=jti)
        return access, refresh, jti
