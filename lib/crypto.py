from __future__ import annotations
import base64
import hashlib
import json
import os
from typing import Any
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from .logger import get_logger

logger = get_logger("crypto")

_RAW_KEY = os.environ.get("WEBHOOK_KEY", "").encode()
_MASTER_KEY: bytes = _RAW_KEY if len(_RAW_KEY) == 32 else hashlib.sha256(_RAW_KEY).digest()

_NONCE_LEN = 12   # 96-bit GCM nonce, standard/recommended size
_TAG_LEN = 16     # 128-bit GCM auth tag, appended to ciphertext by AESGCM


def encrypt_payload(data: dict[str, Any], key: bytes | None = None) -> str:
    actual_key = key if key is not None else _MASTER_KEY
    nonce = os.urandom(_NONCE_LEN)
    plaintext = json.dumps(data, separators=(",", ":")).encode("utf-8")
    aesgcm = AESGCM(actual_key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext, None)  # tag is appended automatically
    return base64.b64encode(nonce + ciphertext_and_tag).decode("ascii")


def decrypt_payload(encrypted_b64: str, key: bytes | None = None) -> dict[str, Any]:
    actual_key = key if key is not None else _MASTER_KEY
    try:
        raw = base64.b64decode(encrypted_b64, validate=True)
    except Exception as exc:
        raise ValueError("Malformed Base64 payload") from exc

    if len(raw) < _NONCE_LEN + _TAG_LEN:
        raise ValueError("Payload too short")

    nonce = raw[:_NONCE_LEN]
    ciphertext_and_tag = raw[_NONCE_LEN:]

    try:
        aesgcm = AESGCM(actual_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
        return json.loads(plaintext.decode("utf-8"))
    except InvalidTag as exc:
        raise ValueError("Decryption failed: authentication tag mismatch") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Decryption failed: malformed plaintext") from exc
    except Exception as exc:
        raise ValueError("Decryption failed") from exc
