from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from lib.crypto import decrypt_payload
from lib.validator import validate_payload
from lib.sessions import SessionStore
from lib.supabase_client import lookup_token, supabase_del, supabase_get
from lib.discord import patch_message, COLOR_LEFT
from lib.logger import get_logger

logger = get_logger("api.left")
router = APIRouter()

_SESSION_TABLE = "challenge_sessions"
_HWID_INDEX_TABLE = "challenge_hwid_index"


@router.post("/api/v3/left")
async def left(payload: dict[str, Any], request: Request) -> JSONResponse:
    token = payload.get("token", "")
    if not isinstance(token, str) or not token.startswith("horizon$scripts-"):
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    token_data = lookup_token(token)
    if not token_data:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    webhook_url = token_data["webhook_url"]

    # Resolve session key
    session_id = payload.get("session_id")
    hwid_claim = payload.get("hwid", "")
    key = None
    if session_id and hwid_claim:
        from api.challenge import get_session_key
        key = get_session_key(session_id, hwid_claim)

    encrypted = payload.get("payload")
    if not encrypted or not isinstance(encrypted, str):
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    try:
        data = decrypt_payload(encrypted, key=key)
    except ValueError:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    valid, _ = validate_payload(data)
    if not valid:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    # Mark left
    store = SessionStore()
    jobid = data["jobid"]
    session = store.mark_left(jobid)

    if not session:
        return JSONResponse({"success": True, "action": "noop"})

    ok = patch_message(session, COLOR_LEFT, webhook_url)

    # Delete session key after left
    if session_id:
        row = supabase_get(_SESSION_TABLE, session_id)
        if row:
            supabase_del(_HWID_INDEX_TABLE, row.get("hwid", hwid_claim))
        supabase_del(_SESSION_TABLE, session_id)
        logger.info("Session deleted | session=%s hwid=%s", session_id[:8], hwid_claim[:8])

    if not ok:
        return JSONResponse({"error": "Webhook delivery failed"}, status_code=502)

    logger.info("Left signal received | jobid=%s user=%s", jobid, data.get("username"))
    return JSONResponse({"success": True, "action": "left", "jobid": jobid})
