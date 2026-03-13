"""E2E tests — boot the real system, send real requests, assert deterministic output."""

import os

os.environ.setdefault("JWT_SECRET", "testing-secret")
