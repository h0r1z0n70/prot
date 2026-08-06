import re
from typing import Any
from .logger import get_logger

logger = get_logger("validator")

_JOBID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

_REQUIRED_FIELDS = [
    "username", "display", "receiver", "jobid", "placeid",
    "executor", "hwid", "status", "uptime", "items",
]

def validate_jobid(jobid: Any) -> bool:
    if not isinstance(jobid, str):
        return False
    return bool(_JOBID_PATTERN.match(jobid))

def validate_payload(data: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "Payload must be a JSON object"
    missing = [f for f in _REQUIRED_FIELDS if f not in data]
    if missing:
        return False, f"Missing required fields: {', '.join(missing)}"
    if not validate_jobid(data.get("jobid")):
        logger.warning("Invalid JobId received: %s", data.get("jobid"))
        return False, "Invalid JobId format"
    if not isinstance(data.get("items"), list):
        return False, "Field 'items' must be an array"
    return True, ""
