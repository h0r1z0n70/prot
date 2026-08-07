from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import hmac
import hashlib
import secrets
from typing import Any
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import lookup_token
from lib.logger import get_logger

logger = get_logger("api.challenge")
router = APIRouter()

_MASTER_KEY = os.environ.get("WEBHOOK_KEY", "").encode()
if len(_MASTER_KEY) != 32:
    _MASTER_KEY = hashlib.sha256(_MASTER_KEY).digest()

_sessions: dict[str, dict] = {}
_SESSION_TTL = 3600


def _cleanup():
    now = time.time()
    stale = [k for k, v in _sessions.items() if v["expires_at"] < now]
    for k in stale:
        del _sessions[k]


def get_session_key(session_id: str, hwid: str) -> bytes | None:
    sess = _sessions.get(session_id)
    if not sess:
        return None
    if time.time() > sess["expires_at"]:
        del _sessions[session_id]
        return None
    if not hmac.compare_digest(sess["hwid"], hwid):
        return None
    return sess["session_key"]


@router.post("/api/v3/challenge")
async def challenge(body: dict[str, Any], request: Request) -> JSONResponse:
    token = body.get("token", "")
    hwid  = body.get("hwid", "")

    if not isinstance(token, str) or not token.startswith("horizon$scripts-"):
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    if not hwid or not isinstance(hwid, str):
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    token_data = lookup_token(token)
    if not token_data:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    _cleanup()

    session_id  = secrets.token_hex(16)
    raw_session = secrets.token_bytes(32)

    binding = hmac.new(_MASTER_KEY, (session_id + hwid).encode(), hashlib.sha256).digest()
    encrypted_key = bytes(a ^ b for a, b in zip(raw_session, binding))

    _sessions[session_id] = {
        "session_key": raw_session,
        "hwid": hwid,
        "expires_at": time.time() + _SESSION_TTL,
    }

    import base64
    logger.info("Challenge issued | session=%s hwid=%s", session_id[:8], hwid[:8])

    return JSONResponse({
        "session_id":    session_id,
        "encrypted_key": base64.b64encode(encrypted_key).decode(),
        "binding":       base64.b64encode(binding).decode(),
    })
