from __future__ import annotations
from api.challenge import get_session_key

def resolve_key(session_id: str, hwid: str) -> bytes | None:
    return get_session_key(session_id, hwid)
