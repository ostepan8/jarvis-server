import os
from contextlib import asynccontextmanager

# Default secret for tests; real deployments must provide JWT_SECRET
os.environ.setdefault("JWT_SECRET", "testing-secret")


@asynccontextmanager
async def _noop_lifespan(app):
    """A no-op lifespan that skips real startup/shutdown for tests."""
    yield


def disable_lifespan(app):
    """Replace the real lifespan with a no-op so tests skip initialization."""
    app.router.lifespan_context = _noop_lifespan
