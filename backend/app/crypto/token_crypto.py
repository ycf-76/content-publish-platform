"""AES-GCM Token encryption/decryption (Phase 1).

Red lines 7.1 / 3.3: XHS session_data and refresh_token MUST be
AES-GCM encrypted before DB storage. Field names use _encrypted suffix.
Plaintext tokens are NEVER persisted.
"""

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_NONCE_SIZE = 12
_KEY_SIZE = 32


class TokenCrypto:
    """AES-GCM encryptor for XHS tokens and session data."""

    def __init__(self, key: str | None = None) -> None:
        raw_key = key or get_settings().aes_secret_key
        if not raw_key:
            raise ValueError("AES_SECRET_KEY is not set. Generate a 32-byte base64 key.")
        self._aesgcm = AESGCM(self._decode_key(raw_key))

    @staticmethod
    def _decode_key(raw_key: str) -> bytes:
        key_bytes = base64.b64decode(raw_key)
        if len(key_bytes) != _KEY_SIZE:
            raise ValueError(f"AES key must be {_KEY_SIZE} bytes, got {len(key_bytes)}")
        return key_bytes

    @staticmethod
    def generate_key() -> str:
        return base64.b64encode(os.urandom(_KEY_SIZE)).decode("ascii")

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_SIZE)
        ct = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
        return base64.b64encode(nonce + ct).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        raw = base64.b64decode(ciphertext)
        if len(raw) < _NONCE_SIZE:
            raise ValueError("Ciphertext too short: must contain at least the nonce")
        nonce = raw[:_NONCE_SIZE]
        ct = raw[_NONCE_SIZE:]
        return self._aesgcm.decrypt(nonce, ct, associated_data=None).decode("utf-8")

    def encrypt_dict(self, data: dict[str, Any]) -> str:
        return self.encrypt(json.dumps(data, ensure_ascii=False, separators=(",", ":")))

    def decrypt_dict(self, ciphertext: str) -> dict[str, Any]:
        return json.loads(self.decrypt(ciphertext))
