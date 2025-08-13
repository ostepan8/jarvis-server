from fastapi import Request
from tzlocal import get_localzone_name
import json
import re

def detect_timezone(request: Request) -> str:
    """Determine the user's timezone.

    Priority:
    1. ``X-Timezone`` header provided by the client.
    2. The server's local timezone.
    """
    return request.headers.get("X-Timezone") or get_localzone_name()


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
