"""Shared HTTP client for Jarvis self-improvement API.

Uses only stdlib urllib — no external dependencies required.
"""

import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse


BASE_URL = os.environ.get("JARVIS_API_URL", "http://localhost:8000/self-improvement")


def request(method: str, path: str, data: dict | None = None, timeout: int = 30) -> dict:
    """Make an HTTP request to the Jarvis self-improvement API.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., "/status")
        data: Optional JSON body for POST requests
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON response as dict

    Raises:
        SystemExit: On connection or HTTP errors (prints error message)
    """
    url = f"{BASE_URL.rstrip('/')}{path}"

    body = None
    headers = {"Content-Type": "application/json"}
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            pass
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Connection error: {exc.reason}", file=sys.stderr)
        print(f"Is the Jarvis server running at {BASE_URL}?", file=sys.stderr)
        sys.exit(1)


def get(path: str, params: dict | None = None, timeout: int = 30) -> dict:
    """Convenience GET request with optional query parameters."""
    if params:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        if query:
            path = f"{path}?{query}"
    return request("GET", path, timeout=timeout)


def post(path: str, data: dict | None = None, timeout: int = 30) -> dict:
    """Convenience POST request."""
    return request("POST", path, data=data or {}, timeout=timeout)
