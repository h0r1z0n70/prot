from __future__ import annotations
import os
import time
import hashlib
import hmac
from typing import Optional
import requests
from .logger import get_logger

logger = get_logger("supabase")

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
_SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
_TABLE = "webhook_tokens"

# In-memory cache: token_hash -> {webhook_url, username, fetched_at}
_cache: dict[str, dict] = {}
_CACHE_TTL = 60  # seconds


def _headers() -> dict:
    return {
        "apikey": _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _hash_token(token: str) -> str:
    """SHA-256 the token so the raw value is never stored in memory logs."""
    return hashlib.sha256(token.encode()).hexdigest()


def lookup_token(token: str) -> Optional[dict]:
    """
    Given a horizon$scripts-<uuid> token, return {webhook_url, username}
    or None if not found / invalid.

    Flow:
      1. Check in-memory cache (TTL 60s) — avoids Supabase hammering.
      2. Query Supabase by token_hash (never store raw token in DB).
      3. Return result or None.
    """
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        logger.error("Supabase env vars not configured")
        return None

    token_hash = _hash_token(token)
    now = time.time()

    cached = _cache.get(token_hash)
    if cached and now - cached["fetched_at"] < _CACHE_TTL:
        return {"webhook_url": cached["webhook_url"], "username": cached["username"]}

    url = (
        f"{_SUPABASE_URL}/rest/v1/{_TABLE}"
        f"?token_hash=eq.{token_hash}"
        f"&select=webhook_url,username,revoked"
    )
    try:
        resp = requests.get(url, headers=_headers(), timeout=5)
    except requests.RequestException as exc:
        logger.error("Supabase lookup failed: %s", exc)
        return None

    if resp.status_code != 200:
        logger.error("Supabase returned %d: %s", resp.status_code, resp.text)
        return None

    rows = resp.json()
    if not rows:
        logger.warning("Token not found | hash=%s", token_hash[:12])
        return None

    row = rows[0]
    if row.get("revoked"):
        logger.warning("Revoked token used | hash=%s", token_hash[:12])
        return None

    _cache[token_hash] = {
        "webhook_url": row["webhook_url"],
        "username": row["username"],
        "fetched_at": now,
    }
    return {"webhook_url": row["webhook_url"], "username": row["username"]}


def register_token(webhook_url: str, username: str) -> Optional[str]:
    """
    Create a new horizon$scripts-<uuid> token, store only its hash in Supabase.
    Returns the raw token (shown once, never stored).
    """
    import uuid
    raw_token = f"horizon$scripts-{uuid.uuid4()}"
    token_hash = _hash_token(raw_token)

    url = f"{_SUPABASE_URL}/rest/v1/{_TABLE}"
    payload = {
        "token_hash": token_hash,
        "webhook_url": webhook_url,
        "username": username,
        "revoked": False,
    }
    try:
        resp = requests.post(url, json=payload, headers={**_headers(), "Prefer": "return=minimal"}, timeout=5)
    except requests.RequestException as exc:
        logger.error("Supabase insert failed: %s", exc)
        return None

    if resp.status_code not in (200, 201):
        logger.error("Supabase insert failed %d: %s", resp.status_code, resp.text)
        return None

    logger.info("Token registered | hash=%s user=%s", token_hash[:12], username)
    return raw_token


def revoke_token(token: str) -> bool:
    """Mark a token as revoked. Cache entry is also cleared."""
    token_hash = _hash_token(token)
    url = (
        f"{_SUPABASE_URL}/rest/v1/{_TABLE}"
        f"?token_hash=eq.{token_hash}"
    )
    try:
        resp = requests.patch(url, json={"revoked": True}, headers=_headers(), timeout=5)
    except requests.RequestException as exc:
        logger.error("Supabase revoke failed: %s", exc)
        return False

    _cache.pop(token_hash, None)
    return resp.status_code in (200, 204)
