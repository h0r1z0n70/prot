import base64
import hashlib
import json
import os
from typing import Any
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.exceptions import InvalidTag
from .logger import get_logger

logger = get_logger("crypto")

_RAW_KEY = os.environ.get("WEBHOOK_KEY", "your-32-byte-secret-key-here!!")
_MASTER_KEY = _RAW_KEY.encode() if isinstance(_RAW_KEY, str) else _RAW_KEY
if len(_MASTER_KEY) != 32:
    _MASTER_KEY = hashlib.sha256(_MASTER_KEY).digest()

def decrypt_payload(encrypted_b64: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(encrypted_b64, validate=True)
    except Exception as exc:
        logger.warning("Base64 decode failure: %s", exc)
        raise ValueError("Malformed Base64 payload") from exc
    if len(raw) < 28:
        logger.warning("Payload too short: %d bytes", len(raw))
        raise ValueError("Payload too short to contain nonce + ciphertext")
    nonce = raw[:12]
    ciphertext = raw[12:]
    try:
        cipher = ChaCha20Poly1305(_MASTER_KEY)
        plaintext = cipher.decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        logger.warning("Invalid ChaCha20-Poly1305 authentication tag")
        raise ValueError("Invalid authentication tag") from exc
    try:
        return json.loads(plaintext.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("JSON decode failure after decryption")
        raise ValueError("Decrypted payload is not valid JSON") from exc
