from fastapi import Request
from tzlocal import get_localzone_name

def detect_timezone(request: Request) -> str:
    """Determine the user's timezone.

    Priority:
    1. ``X-Timezone`` header provided by the client.
    2. The server's local timezone.
    """
    return request.headers.get("X-Timezone") or get_localzone_name()
