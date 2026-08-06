"""Encrypted secure storage for pipeline outputs."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from dfat.infrastructure.storage.local_storage import LocalFileStorage

_SALT_SIZE = 16
_PBKDF2_ITERATIONS = 480_000


class SecureStorage(LocalFileStorage):
    """Local storage extension that encrypts outputs with Fernet/PBKDF2."""

    def write_encrypted(
        self,
        file_path: Path,
        data: bytes,
        passphrase: str,
    ) -> Path:
        """Encrypt and write data to a path within the storage base.

        Args:
            file_path: Destination path.
            data: Plaintext bytes to encrypt.
            passphrase: Passphrase used to derive the Fernet key.

        Returns:
            Path to the written ciphertext file (salt || token).
        """
        salt = os.urandom(_SALT_SIZE)
        fernet = Fernet(self._derive_key(passphrase, salt))
        token = fernet.encrypt(data)
        return self.write_file(file_path, salt + token)

    def read_encrypted(self, file_path: Path, passphrase: str) -> bytes:
        """Read and decrypt an encrypted file.

        Args:
            file_path: Path to the encrypted file.
            passphrase: Passphrase used during encryption.

        Returns:
            Decrypted plaintext bytes.

        Raises:
            ValueError: If the file is too short to contain salt + token.
        """
        payload = self.read_file(file_path)
        if len(payload) <= _SALT_SIZE:
            raise ValueError(f"Encrypted file is truncated: {file_path}")
        salt = payload[:_SALT_SIZE]
        token = payload[_SALT_SIZE:]
        fernet = Fernet(self._derive_key(passphrase, salt))
        return fernet.decrypt(token)

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        """Derive a url-safe Fernet key from a passphrase and salt.

        Args:
            passphrase: User-supplied passphrase.
            salt: Random salt bytes.

        Returns:
            Base64 url-safe 32-byte key for Fernet.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_PBKDF2_ITERATIONS,
        )
        return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
