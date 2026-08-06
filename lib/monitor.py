from __future__ import annotations
import threading
import time
from datetime import datetime
from typing import Optional
from .logger import get_logger
from .sessions import SessionStore
from .discord import patch_message, COLOR_LEFT

logger = get_logger("monitor")

_monitor_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def _monitor_loop() -> None:
    store = SessionStore()
    while not _stop_event.is_set():
        time.sleep(1.0)
        now = datetime.utcnow()
        for jobid, session in store.get_all().items():
            elapsed = (now - session.last_seen).total_seconds()
            if elapsed > 5.0 and session.current_status != "left":
                sess = store.mark_left(jobid)
                if sess:
                    ok = patch_message(sess, COLOR_LEFT, sess.webhook_url)
                    if ok:
                        logger.info("Patched LEFT | jobid=%s elapsed=%.1fs", jobid, elapsed)
                    else:
                        logger.error("Failed to patch LEFT | jobid=%s", jobid)
        if int(time.time()) % 10 == 0:
            store.prune_stale(max_age_seconds=300.0)


def start_monitor() -> None:
    global _monitor_thread
    if _monitor_thread is not None and _monitor_thread.is_alive():
        return
    _stop_event.clear()
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
    _monitor_thread.start()
    logger.info("Heartbeat monitor started")


def stop_monitor() -> None:
    _stop_event.set()
    if _monitor_thread:
        _monitor_thread.join(timeout=2.0)
        logger.info("Heartbeat monitor stopped")
