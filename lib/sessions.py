from __future__ import annotations
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from .logger import get_logger

logger = get_logger("sessions")


@dataclass
class Session:
    jobid: str
    username: str
    display: str
    executor: str
    hwid: str
    placeid: str
    receiver: str
    webhook_url: str          # stored per-session, resolved from Supabase at dispatch time
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    current_status: str = "starting"
    uptime: str = ""
    discord_message_id: Optional[str] = None
    _left_patched: bool = field(default=False, repr=False)


class SessionStore:
    _instance: Optional["SessionStore"] = None
    _inst_lock = threading.Lock()

    def __new__(cls) -> "SessionStore":
        if cls._instance is None:
            with cls._inst_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._sessions: dict[str, Session] = {}
                    cls._instance._lock = threading.RLock()
        return cls._instance

    def get(self, jobid: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(jobid)

    def get_all(self) -> dict[str, Session]:
        with self._lock:
            return dict(self._sessions)

    def upsert(self, jobid: str, **kwargs) -> tuple[Session, bool]:
        with self._lock:
            existing = self._sessions.get(jobid)
            if existing:
                existing.last_seen = datetime.utcnow()
                existing.uptime = kwargs.get("uptime", existing.uptime)
                existing.current_status = "ingame"
                existing._left_patched = False
                return existing, False
            session = Session(jobid=jobid, **kwargs)
            self._sessions[jobid] = session
            logger.info("New session | jobid=%s user=%s", jobid, session.username)
            return session, True

    def set_message_id(self, jobid: str, message_id: str) -> None:
        with self._lock:
            sess = self._sessions.get(jobid)
            if sess:
                sess.discord_message_id = message_id

    def mark_left(self, jobid: str) -> Optional[Session]:
        with self._lock:
            sess = self._sessions.get(jobid)
            if sess and not sess._left_patched:
                sess.current_status = "left"
                sess._left_patched = True
                logger.info("Session marked LEFT | jobid=%s", jobid)
                return sess
            return None

    def remove(self, jobid: str) -> None:
        with self._lock:
            if self._sessions.pop(jobid, None):
                logger.info("Session removed | jobid=%s", jobid)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def prune_stale(self, max_age_seconds: float = 300.0) -> int:
        now = datetime.utcnow()
        removed = 0
        with self._lock:
            stale = [
                jid for jid, s in self._sessions.items()
                if (now - s.last_seen).total_seconds() > max_age_seconds
            ]
            for jid in stale:
                del self._sessions[jid]
                removed += 1
        if removed:
            logger.info("Pruned %d stale sessions", removed)
        return removed
