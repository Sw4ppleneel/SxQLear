from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Sentinel prefix so we can tell an encrypted value apart from a legacy
# plaintext value already sitting in someone's memory.db (see migration
# 0002_encrypt_connection_secrets). Never used as a real secret's content.
ENCRYPTED_PREFIX = "enc::v1::"


class SecretBox:
    """
    Encrypts connection secrets (passwords, API keys) at rest.

    Local-first design: the key lives on disk next to memory.db, not in a
    remote KMS. This still turns "read the SQLite file" into "read the SQLite
    file AND the key file" for an attacker, and keeps secrets out of casual
    inspection (backups, `sqlite3 memory.db .dump`, screen-shares).
    """

    def __init__(self, key_path: Path) -> None:
        self._key_path = key_path
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        if self._key_path.exists():
            return self._key_path.read_bytes()

        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        # Write with restrictive permissions from the start — avoid a window
        # where the key is briefly world-readable.
        fd = os.open(self._key_path, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        try:
            os.write(fd, key)
        finally:
            os.close(fd)
        logger.info("Generated new secret-encryption key at %s", self._key_path)
        return key

    def encrypt(self, plaintext: str) -> str:
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return ENCRYPTED_PREFIX + base64.urlsafe_b64encode(token).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not self.is_encrypted(value):
            # Legacy plaintext value from before encryption was introduced.
            # Decrypt-on-read call sites treat this as already-plaintext.
            return value
        raw = base64.urlsafe_b64decode(value[len(ENCRYPTED_PREFIX):].encode("ascii"))
        try:
            return self._fernet.decrypt(raw).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError(
                "Could not decrypt stored secret — the encryption key at "
                f"{self._key_path} may have changed or the value is corrupt."
            ) from exc

    @staticmethod
    def is_encrypted(value: str) -> bool:
        return value.startswith(ENCRYPTED_PREFIX)


_box: SecretBox | None = None


def get_secret_box() -> SecretBox:
    global _box
    if _box is None:
        from config import settings

        _box = SecretBox(settings.data_dir / "key")
    return _box
