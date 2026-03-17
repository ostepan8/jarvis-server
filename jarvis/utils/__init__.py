from fastapi import Request
from tzlocal import get_localzone_name
import json
import re
from typing import Any  # noqa: F401 – used by safe_json_dumps


def detect_timezone(request: Request) -> str:
    """Determine the user's timezone.

    Priority:
    1. ``X-Timezone`` header provided by the client.
    2. The server's local timezone.
    """
    return request.headers.get("X-Timezone") or get_localzone_name()


def safe_json_dumps(obj: Any) -> str:
    """Safely serialize *obj* to a JSON string.

    Falls back to ``str(obj)`` when the object is not natively
    JSON-serialisable, trying ``obj.__dict__`` as an intermediate step.
    """
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        if hasattr(obj, "__dict__"):
            try:
                return json.dumps(obj.__dict__)
            except (TypeError, ValueError):
                return str(obj)
        if hasattr(obj, "__name__"):
            return f"<{obj.__class__.__name__}: {obj.__name__}>"
        return f"<{type(obj).__name__}: {str(obj)}>"


def extract_json_from_text(text: str):
    """Extract a JSON object from a text string.

    The text may include a fenced code block such as ````json ...```.
    Returns the parsed JSON dict on success or ``None`` on failure.
    """

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None
