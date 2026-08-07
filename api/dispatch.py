from __future__ import annotations
import os
import time
import hmac
import hashlib
import re
from typing import Any
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from lib.crypto import decrypt_payload
from lib.validator import validate_payload
from lib.sessions import SessionStore
from lib.supabase_client import lookup_token
from lib.discord import post_message, patch_message, COLOR_INGAME
from lib.logger import get_logger

logger = get_logger("api.dispatch")
router = APIRouter()

class _RateLimiter:
    def __init__(self, max_req: int = 10, window: int = 60):
        self.max_req = max_req
        self.window = window
        self._store: dict[str, list[float]] = {}
        self._blocked: dict[str, float] = {}
        self._strike: dict[str, int] = {}

    def is_allowed(self, identifier: str) -> tuple[bool, str]:
        now = time.time()
        blocked_until = self._blocked.get(identifier, 0)
        if now < blocked_until:
            return False, f"Blocked for {int(blocked_until - now)}s"
        timestamps = self._store.get(identifier, [])
        alive = [t for t in timestamps if now - t < self.window]
        if len(alive) >= self.max_req:
            strikes = self._strike.get(identifier, 0) + 1
            self._strike[identifier] = strikes
            block_duration = [60, 300, 3600][min(strikes - 1, 2)]
            self._blocked[identifier] = now + block_duration
            logger.warning("Rate abuse | ident=%s strike=%d block=%ds", identifier, strikes, block_duration)
            return False, "Rate limit exceeded"
        alive.append(now)
        self._store[identifier] = alive
        return True, ""

_limiter = _RateLimiter(
    max_req=int(os.environ.get("RATE_LIMIT_MAX", "10")),
    window=int(os.environ.get("RATE_LIMIT_WINDOW", "60")),
)

_TOKEN_PREFIX = "horizon$scripts-"

def _validate_token_format(token: str) -> bool:
    if not token.startswith(_TOKEN_PREFIX):
        return False
    uuid_part = token[len(_TOKEN_PREFIX):]
    return bool(re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        uuid_part, re.IGNORECASE
    ))

@router.post("/api/v3/dispatch")
async def dispatch(payload: dict[str, Any], request: Request) -> JSONResponse:
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )
    hwid_header = request.headers.get("x-hwid", client_ip)
    ident = f"{hwid_header}:{client_ip}"

    allowed, reason = _limiter.is_allowed(ident)
    if not allowed:
        logger.warning("Rate limited | ident=%s reason=%s", ident, reason)
        return JSONResponse({"error": reason}, status_code=429)

    token = payload.get("token", "")
    if not isinstance(token, str) or not _validate_token_format(token):
        logger.warning("Bad token format | ident=%s", ident)
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    token_data = lookup_token(token)
    if not token_data:
        logger.warning("Token lookup failed | ident=%s", ident)
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    webhook_url = token_data["webhook_url"]

    encrypted = payload.get("payload")
    if not encrypted or not isinstance(encrypted, str):
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    session_id = payload.get("session_id")
    decryption_key = None
    if session_id and isinstance(session_id, str):
        store = SessionStore()
        session_data = store.get_session(session_id)
        if session_data:
            decryption_key = session_data.get("session_key")

    try:
        data = decrypt_payload(encrypted, key=decryption_key)
    except ValueError:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    valid, err = validate_payload(data)
    if not valid:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    store = SessionStore()
    jobid: str = data["jobid"]

    session, created = store.upsert(
        jobid=jobid,
        username=data["username"],
        display=data["display"],
        executor=data["executor"],
        hwid=data["hwid"],
        placeid=data["placeid"],
        receiver=data["receiver"],
        items=data.get("items", {}),
        joined_at=data.get("joined_at", time.time()),
        webhook_url=webhook_url,
    )

    if created:
        msg_id = post_message(session, webhook_url)
        if msg_id:
            store.set_message_id(jobid, msg_id)
            return JSONResponse({
                "success": True,
                "action": "created",
                "jobid": jobid,
                "message_id": msg_id,
            })
        return JSONResponse({"error": "Webhook delivery failed"}, status_code=502)

    if session.current_status == "left":
        session.current_status = "ingame"
        session._left_patched = False

    ok = patch_message(session, COLOR_INGAME, webhook_url)
    if not ok:
        return JSONResponse({"error": "Webhook delivery failed"}, status_code=502)

    return JSONResponse({
        "success": True,
        "action": "updated",
        "jobid": jobid,
        "message_id": session.discord_message_id,
        "status": session.current_status,
    })
