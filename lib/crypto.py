from __future__ import annotations
import base64
import hashlib
import json
import os
import struct
from typing import Any
from .logger import get_logger

logger = get_logger("crypto")

_RAW_KEY = os.environ.get("WEBHOOK_KEY", "").encode()
_MASTER_KEY: bytes = _RAW_KEY if len(_RAW_KEY) == 32 else hashlib.sha256(_RAW_KEY).digest()


def _chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    constants = b"expa" + b"nd 3" + b"2-by" + b"te k"
    state = list(struct.unpack("<16I",
        constants +
        key[:32] +
        struct.pack("<I", counter) +
        nonce[:12]
    ))
    working = list(state)

    def rotl(v, n): return ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF
    def qr(a, b, c, d):
        working[a] = (working[a] + working[b]) & 0xFFFFFFFF; working[d] = rotl(working[d] ^ working[a], 16)
        working[c] = (working[c] + working[d]) & 0xFFFFFFFF; working[b] = rotl(working[b] ^ working[c], 12)
        working[a] = (working[a] + working[b]) & 0xFFFFFFFF; working[d] = rotl(working[d] ^ working[a], 8)
        working[c] = (working[c] + working[d]) & 0xFFFFFFFF; working[b] = rotl(working[b] ^ working[c], 7)

    for _ in range(10):
        qr(0,4,8,12); qr(1,5,9,13); qr(2,6,10,14); qr(3,7,11,15)
        qr(0,5,10,15); qr(1,6,11,12); qr(2,7,8,13); qr(3,4,9,14)

    output = [(working[i] + state[i]) & 0xFFFFFFFF for i in range(16)]
    return struct.pack("<16I", *output)


def _chacha20_encrypt(key: bytes, nonce: bytes, plaintext: bytes, counter: int = 1) -> bytes:
    out = bytearray()
    for i in range(0, len(plaintext), 64):
        block = _chacha20_block(key, counter + i // 64, nonce)
        chunk = plaintext[i:i+64]
        out.extend(b ^ k for b, k in zip(chunk, block))
    return bytes(out)


def decrypt_payload(encrypted_b64: str, key: bytes | None = None) -> dict[str, Any]:
    actual_key = key if key is not None else _MASTER_KEY
    try:
        raw = base64.b64decode(encrypted_b64, validate=True)
    except Exception as exc:
        raise ValueError("Malformed Base64 payload") from exc
    if len(raw) < 13:
        raise ValueError("Payload too short")
    nonce = raw[:12]
    for ciphertext in [raw[12:-16], raw[12:]]:
        try:
            plaintext = _chacha20_encrypt(actual_key, nonce, ciphertext, counter=1)
            return json.loads(plaintext.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    raise ValueError("Decryption failed")
