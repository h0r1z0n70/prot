from __future__ import annotations
import base64
import hashlib
import json
import os
from typing import Any
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.exceptions import InvalidTag
from .logger import get_logger

logger = get_logger("crypto")

_RAW_KEY = os.environ.get("WEBHOOK_KEY", "").encode()
_MASTER_KEY: bytes = _RAW_KEY if len(_RAW_KEY) == 32 else hashlib.sha256(_RAW_KEY).digest()


def decrypt_payload(encrypted_b64: str, key: bytes | None = None) -> dict[str, Any]:
    actual_key = key if key is not None else _MASTER_KEY
    try:
        raw = base64.b64decode(encrypted_b64, validate=True)
    except Exception as exc:
        raise ValueError("Malformed Base64 payload") from exc
    if len(raw) < 28:
        raise ValueError("Payload too short")
    nonce, ciphertext = raw[:12], raw[12:]
    try:
        plaintext = ChaCha20Poly1305(actual_key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise ValueError("Invalid authentication tag") from exc
    try:
        return json.loads(plaintext.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Decrypted payload is not valid JSON") from exc
