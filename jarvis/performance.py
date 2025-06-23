import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import contextvars


PERF_TRACKING_ENV = os.getenv("PERF_TRACKING", "false").lower() == "true"
_current_tracker: contextvars.ContextVar["PerfTracker | None"] = contextvars.ContextVar(
    "current_perf_tracker", default=None
)


@dataclass
class PerfEvent:
    name: str
    start: float
    end: float
    duration: float
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PerfTracker:
    enabled: bool = PERF_TRACKING_ENV
    interaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    events: List[PerfEvent] = field(default_factory=list)
    start_ts: float = field(default_factory=time.time)
    end_ts: float | None = None
    _token: contextvars.Token | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        self.start_ts = time.time()
        self._token = _current_tracker.set(self)

    def stop(self) -> None:
        if not self.enabled:
            return
        self.end_ts = time.time()
        if self._token is not None:
            _current_tracker.reset(self._token)

    @asynccontextmanager
    async def timer(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        if not self.enabled:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            end = time.perf_counter()
            self.events.append(
                PerfEvent(name=name, start=start, end=end, duration=end - start, metadata=metadata)
            )

    def summary(self) -> Dict[str, Any]:
        timings = {ev.name: round(ev.duration, 4) for ev in self.events}
        ordered = dict(sorted(timings.items(), key=lambda i: i[1], reverse=True))
        return {
            "interaction_id": self.interaction_id,
            "timings": ordered,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def save(self, path: str = "perf_logs.jsonl") -> None:
        if not self.enabled:
            return
        data = self.summary()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")


def get_tracker() -> Optional[PerfTracker]:
    return _current_tracker.get()


def track_async(name: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            tracker = get_tracker()
            if tracker and tracker.enabled:
                async with tracker.timer(name):
                    return await func(*args, **kwargs)
            return await func(*args, **kwargs)

        return wrapper

    return decorator
