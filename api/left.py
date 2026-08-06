from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from lib.crypto import decrypt_payload
from lib.validator import validate_payload
from lib.sessions import SessionStore
from lib.supabase_client import lookup_token
from lib.discord import patch_message, COLOR_LEFT
from lib.logger import get_logger

logger = get_logger("api.left")
router = APIRouter()


@router.post("/api/v3/left")
async def left(payload: dict[str, Any], request: Request) -> JSONResponse:
    token = payload.get("token", "")
    if not isinstance(token, str) or not token.startswith("horizon$scripts-"):
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    token_data = lookup_token(token)
    if not token_data:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    webhook_url = token_data["webhook_url"]

    encrypted = payload.get("payload")
    if not encrypted or not isinstance(encrypted, str):
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    try:
        data = decrypt_payload(encrypted)
    except ValueError:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    valid, _ = validate_payload(data)
    if not valid:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    store = SessionStore()
    jobid = data["jobid"]
    session = store.mark_left(jobid)

    if not session:
        return JSONResponse({"success": True, "action": "noop"})

    ok = patch_message(session, COLOR_LEFT, webhook_url)
    if not ok:
        return JSONResponse({"error": "Webhook delivery failed"}, status_code=502)

    logger.info("Left signal received | jobid=%s user=%s", jobid, data.get("username"))
    return JSONResponse({"success": True, "action": "left", "jobid": jobid})
