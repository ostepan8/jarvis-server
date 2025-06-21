from __future__ import annotations

from typing import Any, Dict
from pymongo import MongoClient
import asyncio


class ProtocolUsageLogger:
    """Write protocol execution logs to MongoDB."""

    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "jarvis") -> None:
        self.client = MongoClient(mongo_uri)
        self.collection = self.client[db_name]["protocol_usage_history"]
        # Ensure indexes for common queries
        self.collection.create_index("protocol_name")
        self.collection.create_index("day_of_week")
        self.collection.create_index("hour")

    async def log_usage(self, log_doc: Dict[str, Any]) -> None:
        """Insert a log document."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.collection.insert_one, log_doc)

from datetime import datetime


def _time_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


REQUIRED_FIELDS = [
    "protocol_name",
    "protocol_id",
    "arguments",
    "steps",
    "timestamp",
    "day_of_week",
    "hour",
    "time_of_day",
    "device",
    "location",
    "trigger_phrase_used",
    "user",
    "source",
    "execution_result",
    "latency_ms",
]


def generate_protocol_log(protocol, arguments: Dict[str, Any], trigger_phrase: str | None, metadata: Dict[str, Any] | None) -> Dict[str, Any]:
    """Create a log document for protocol execution."""
    metadata = metadata or {}
    now = datetime.utcnow()
    hour = now.hour
    log_doc = {
        "protocol_name": protocol.name,
        "protocol_id": protocol.id,
        "arguments": arguments or {},
        "steps": [
            {"agent": s.agent, "function": s.function, "parameters": s.parameters}
            for s in getattr(protocol, "steps", [])
        ],
        "timestamp": now,
        "day_of_week": now.strftime("%A"),
        "hour": hour,
        "time_of_day": _time_of_day(hour),
        "device": metadata.get("device"),
        "location": metadata.get("location"),
        "trigger_phrase_used": trigger_phrase,
        "user": metadata.get("user"),
        "source": metadata.get("source"),
        "execution_result": metadata.get("execution_result"),
        "latency_ms": metadata.get("latency_ms"),
    }
    # Ensure all fields exist
    for field in REQUIRED_FIELDS:
        log_doc.setdefault(field, None)
    return log_doc
