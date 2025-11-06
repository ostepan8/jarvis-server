from fastapi import Request
from tzlocal import get_localzone_name
import json
import re
import httpx
from typing import Optional


def detect_timezone(request: Request) -> str:
    """Determine the user's timezone.

    Priority:
    1. ``X-Timezone`` header provided by the client.
    2. The server's local timezone.
    """
    return request.headers.get("X-Timezone") or get_localzone_name()


def get_location_from_ip(timeout: float = 5.0) -> Optional[str]:
    """Get the current location (city name) based on the computer's IP address.

    Uses ipinfo.io API which provides free geolocation based on IP address.
    Returns the city name (e.g., "Chicago") or None if detection fails.

    Args:
        timeout: Request timeout in seconds

    Returns:
        City name string like "Chicago" or None if detection fails
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            # Get public IP address
            ip_response = client.get("https://api.ipify.org?format=json")
            if ip_response.status_code != 200:
                return None

            public_ip = ip_response.json().get("ip")
            if not public_ip:
                return None

            # Get location from IP
            location_response = client.get(f"https://ipinfo.io/{public_ip}/json")
            if location_response.status_code != 200:
                return None

            location_data = location_response.json()
            city = location_data.get("city")

            # Return city name, or fallback to a more specific location string
            if city:
                return city
            elif location_data.get("region") and location_data.get("country"):
                # Fallback: use region if city not available
                return f"{location_data.get('region')}, {location_data.get('country')}"
            else:
                return None

    except Exception:
        # Silently fail - will use default location
        return None


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
