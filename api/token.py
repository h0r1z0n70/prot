from __future__ import annotations
import sys, os
from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse
from lib.supabase_client import register_token, revoke_token
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.crypto import decrypt_payload
from lib.validator import validate_payload
from lib.sessions import SessionStore
from lib.supabase_client import lookup_token
from lib.discord import post_message, patch_message, COLOR_INGAME
from lib.logger import get_logger

logger = get_logger("api.token")
router = APIRouter()

_ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")


def _check_admin(secret: str | None) -> bool:
    if not _ADMIN_SECRET:
        return False
    if not secret:
        return False
    # Constant-time compare to prevent timing attacks
    import hmac
    return hmac.compare_digest(secret.encode(), _ADMIN_SECRET.encode())


@router.post("/api/v3/token/register")
async def token_register(
    body: dict,
    request: Request,
    x_admin_secret: str | None = Header(default=None),
) -> JSONResponse:
    """
    Admin-only: create a new horizon$scripts token.
    Body: { "webhook_url": "...", "username": "..." }
    Returns the raw token ONE TIME — it is never stored.
    """
    if not _check_admin(x_admin_secret):
        logger.warning("Unauthorized token/register attempt from %s", request.client)
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    webhook_url = body.get("webhook_url", "").strip()
    username = body.get("username", "").strip()

    if not webhook_url or not username:
        return JSONResponse({"error": "webhook_url and username required"}, status_code=400)

    if "discord.com/api/webhooks/" not in webhook_url:
        return JSONResponse({"error": "Invalid Discord webhook URL"}, status_code=400)

    token = register_token(webhook_url, username)
    if not token:
        return JSONResponse({"error": "Failed to register token"}, status_code=500)

    return JSONResponse({
        "token": token,
        "note": "Store this token securely. It will not be shown again.",
        "username": username,
    })


@router.post("/api/v3/token/revoke")
async def token_revoke(
    body: dict,
    request: Request,
    x_admin_secret: str | None = Header(default=None),
) -> JSONResponse:
    """Admin-only: revoke a token immediately."""
    if not _check_admin(x_admin_secret):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    token = body.get("token", "").strip()
    if not token:
        return JSONResponse({"error": "token required"}, status_code=400)

    ok = revoke_token(token)
    if not ok:
        return JSONResponse({"error": "Revoke failed or token not found"}, status_code=404)

    return JSONResponse({"success": True, "message": "Token revoked"})
