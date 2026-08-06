from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from lib.sessions import SessionStore
from lib.logger import get_logger

logger = get_logger("api.health")
router = APIRouter()

_BOOT_TIME = datetime.utcnow()
_LAST_CLEANUP = _BOOT_TIME

@router.get("/api/v3/health")
async def health() -> JSONResponse:
    store = SessionStore()
    now = datetime.utcnow()
    uptime_seconds = (now - _BOOT_TIME).total_seconds()
    sessions = store.get_all()
    statuses = {"starting": 0, "ingame": 0, "left": 0}
    for s in sessions.values():
        statuses[s.current_status] = statuses.get(s.current_status, 0) + 1
    return JSONResponse({
        "service": "Horizon Protector v3",
        "status": "healthy",
        "active_sessions": store.count(),
        "session_breakdown": statuses,
        "uptime_seconds": round(uptime_seconds, 2),
        "last_cleanup": _LAST_CLEANUP.isoformat() + "Z",
        "timestamp": now.isoformat() + "Z",
    })

@router.get("/api/v3/sessions")
async def list_sessions() -> JSONResponse:
    store = SessionStore()
    out: list[dict[str, Any]] = []
    for jobid, s in store.get_all().items():
        out.append({
            "jobid": s.jobid,
            "username": s.username,
            "display": s.display,
            "executor": s.executor,
            "placeid": s.placeid,
            "receiver": s.receiver,
            "first_seen": s.first_seen.isoformat() + "Z",
            "last_seen": s.last_seen.isoformat() + "Z",
            "current_status": s.current_status,
            "uptime": s.uptime,
            "discord_message_id": s.discord_message_id,
        })
    return JSONResponse({"count": len(out), "sessions": out})
