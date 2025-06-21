from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pydantic import BaseModel, Field, validator

# Import for timezone detection
try:
    from zoneinfo import ZoneInfo
    import time
    import platform

    def get_system_timezone() -> str:
        """Get system timezone using zoneinfo (Python 3.9+)."""
        if platform.system() == "Windows":
            # Windows requires special handling
            import subprocess

            result = subprocess.run(["tzutil", "/g"], capture_output=True, text=True)
            if result.returncode == 0:
                windows_tz = result.stdout.strip()
                # Map Windows timezone to IANA (simplified mapping)
                # In production, use a proper mapping library
                tz_map = {
                    "Eastern Standard Time": "America/New_York",
                    "Central Standard Time": "America/Chicago",
                    "Mountain Standard Time": "America/Denver",
                    "Pacific Standard Time": "America/Los_Angeles",
                    # Add more mappings as needed
                }
                return tz_map.get(windows_tz, "UTC")
        else:
            # Unix-like systems
            import os

            if os.path.exists("/etc/timezone"):
                with open("/etc/timezone", "r") as f:
                    return f.read().strip()
            elif os.path.exists("/etc/localtime"):
                # Try to resolve the symlink
                import pathlib

                tz_path = pathlib.Path("/etc/localtime").resolve()
                tz_str = str(tz_path)
                if "/zoneinfo/" in tz_str:
                    return tz_str.split("/zoneinfo/")[-1]
        return "UTC"  # Default fallback

except ImportError:
    # Fallback for Python < 3.9 or if zoneinfo not available
    try:
        from tzlocal import get_localzone

        def get_system_timezone() -> str:
            """Get system timezone using tzlocal."""
            try:
                return str(get_localzone())
            except Exception:
                return "UTC"

    except ImportError:
        # Ultimate fallback
        def get_system_timezone() -> str:
            """Fallback when no timezone library is available."""
            return "UTC"


# Import Protocol data models
from ..models import Protocol, ProtocolStep


# Utility Enums and Functions
class TimeOfDay(Enum):
    """Time of day categories."""

    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"

    @classmethod
    def from_hour(cls, hour: int) -> TimeOfDay:
        """Determine time of day from hour (0-23)."""
        if 5 <= hour < 12:
            return cls.MORNING
        elif 12 <= hour < 17:
            return cls.AFTERNOON
        elif 17 <= hour < 21:
            return cls.EVENING
        else:
            return cls.NIGHT


def get_time_of_day(timestamp: datetime, tz_str: Optional[str] = None) -> TimeOfDay:
    """
    Get time of day from a timestamp.

    Args:
        timestamp: UTC datetime object
        tz_str: Optional timezone string to convert to local time

    Returns:
        TimeOfDay enum value
    """
    if tz_str and tz_str != "UTC":
        try:
            # Convert to local timezone if provided
            local_tz = ZoneInfo(tz_str)
            local_time = timestamp.astimezone(local_tz)
            return TimeOfDay.from_hour(local_time.hour)
        except Exception:
            pass

    return TimeOfDay.from_hour(timestamp.hour)


def get_day_of_week(timestamp: datetime, tz_str: Optional[str] = None) -> str:
    """
    Get day of week from a timestamp.

    Args:
        timestamp: UTC datetime object
        tz_str: Optional timezone string to convert to local time

    Returns:
        Day name (e.g., "Monday", "Tuesday")
    """
    if tz_str and tz_str != "UTC":
        try:
            # Convert to local timezone if provided
            local_tz = ZoneInfo(tz_str)
            local_time = timestamp.astimezone(local_tz)
            return local_time.strftime("%A")
        except Exception:
            pass

    return timestamp.strftime("%A")


# Data Models
class ExecutionMetadata(BaseModel):
    """Metadata for protocol execution."""

    device: Optional[str] = None
    location: Optional[str] = None
    user: Optional[str] = None
    source: Optional[str] = None
    execution_result: Optional[Union[str, Dict[str, Any]]] = None
    latency_ms: Optional[float] = None

    @validator("execution_result", pre=True)
    def normalize_execution_result(cls, v):
        """Normalize execution_result to always be a dict."""
        if v is None:
            return None
        if isinstance(v, str):
            return {"status": v}
        return v


class ProtocolLogEntry(BaseModel):
    """Clean log entry for protocol execution - only essential fields."""

    protocol_name: str
    protocol_id: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Dict[str, Any]] = Field(
        default_factory=list
    )  # Store as dicts for MongoDB
    timestamp_utc: datetime  # UTC timestamp
    time_zone: str  # IANA format timezone, e.g., "America/New_York"
    device: Optional[str] = None
    location: Optional[str] = None
    trigger_phrase_used: Optional[str] = None
    user: Optional[str] = None
    source: Optional[str] = None
    execution_result: Optional[Union[str, Dict[str, Any]]] = None
    latency_ms: Optional[float] = None

    class Config:
        """Pydantic configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# Logger implementation
@dataclass
class ProtocolUsageLogger:
    """
    Async MongoDB logger for protocol execution tracking.

    Clean schema design - stores only essential fields and computes
    derived values at runtime when needed.
    """

    mongo_uri: str = "mongodb://localhost:27017"
    db_name: str = "jarvis"
    collection_name: str = "protocol_usage_history"
    connection_timeout_ms: int = 5000
    max_pool_size: int = 10

    # Internal state
    _client: Optional[AsyncIOMotorClient] = field(default=None, init=False)
    _collection: Optional[AsyncIOMotorCollection] = field(default=None, init=False)
    _logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger(__name__), init=False
    )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """
        Establish connection to MongoDB and create indexes.

        Raises:
            ConnectionError: If unable to connect to MongoDB
        """
        try:
            self._client = AsyncIOMotorClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=self.connection_timeout_ms,
                maxPoolSize=self.max_pool_size,
            )

            # Test connection
            await self._client.admin.command("ping")

            self._collection = self._client[self.db_name][self.collection_name]

            # Create indexes for efficient querying
            await self._create_indexes()

            self._logger.info(f"Connected to MongoDB at {self.mongo_uri}")

        except Exception as e:
            self._logger.error(f"Failed to connect to MongoDB: {e}")
            raise ConnectionError(f"MongoDB connection failed: {e}") from e

    async def _create_indexes(self) -> None:
        """Create indexes for common query patterns."""
        indexes = [
            ("protocol_name", 1),
            ("timestamp_utc", -1),
            ("time_zone", 1),
            ("user", 1),
            ("device", 1),
            ([("protocol_name", 1), ("timestamp_utc", -1)], None),
            ([("user", 1), ("timestamp_utc", -1)], None),
            ([("time_zone", 1), ("timestamp_utc", -1)], None),
        ]

        for index in indexes:
            if isinstance(index, tuple) and len(index) == 2:
                keys, _ = index
                await self._collection.create_index(keys)
            else:
                await self._collection.create_index(index)

    async def close(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._logger.info("Closed MongoDB connection")

    def generate_log_entry(
        self,
        protocol: Protocol,
        arguments: Dict[str, Any],
        trigger_phrase: Optional[str] = None,
        metadata: Optional[ExecutionMetadata] = None,
    ) -> ProtocolLogEntry:
        """
        Generate a clean log entry for protocol execution.

        Args:
            protocol: The protocol being executed
            arguments: Arguments passed to the protocol
            trigger_phrase: Optional trigger phrase that initiated execution
            metadata: Optional execution metadata

        Returns:
            ProtocolLogEntry: Clean log entry ready for storage
        """
        metadata = metadata or ExecutionMetadata()

        # Get current UTC timestamp
        now_utc = datetime.now(timezone.utc)

        # Automatically detect system timezone
        system_timezone = get_system_timezone()

        # Convert ProtocolStep objects to dicts for MongoDB storage
        steps_as_dicts = [
            {
                "agent": step.agent,
                "function": step.function,
                "parameters": step.parameters,
                "parameter_mappings": step.parameter_mappings,
            }
            for step in protocol.steps
        ]

        # Create clean log entry with timezone
        return ProtocolLogEntry(
            protocol_name=protocol.name,
            protocol_id=protocol.id,
            arguments=arguments or {},
            steps=steps_as_dicts,
            timestamp_utc=now_utc,
            time_zone=system_timezone,  # Automatically detected
            device=metadata.device,
            location=metadata.location,
            trigger_phrase_used=trigger_phrase,
            user=metadata.user,
            source=metadata.source,
            execution_result=metadata.execution_result,
            latency_ms=metadata.latency_ms,
        )

    async def log_usage(self, log_doc: Dict[str, Any]) -> str:
        """
        Log protocol usage to MongoDB.

        Args:
            log_doc: Log document to insert

        Returns:
            str: The inserted document ID

        Raises:
            RuntimeError: If insert fails
        """
        # Auto-connect if not connected
        if self._collection is None:
            try:
                await self.connect()
            except Exception as e:
                raise RuntimeError(f"Failed to auto-connect to MongoDB: {e}")

        try:
            result = await self._collection.insert_one(log_doc)
            self._logger.debug(
                f"Logged protocol usage: {log_doc.get('protocol_name', 'Unknown')} (ID: {result.inserted_id})"
            )
            return str(result.inserted_id)

        except Exception as e:
            self._logger.error(f"Failed to log protocol usage: {e}")
            raise RuntimeError(f"Failed to log protocol usage: {e}") from e

    async def log_usage_structured(
        self,
        protocol: Protocol,
        arguments: Dict[str, Any],
        trigger_phrase: Optional[str] = None,
        metadata: Optional[Union[ExecutionMetadata, Dict[str, Any]]] = None,
    ) -> str:
        """
        Log protocol usage with structured parameters.

        Args:
            protocol: The protocol being executed
            arguments: Arguments passed to the protocol
            trigger_phrase: Optional trigger phrase that initiated execution
            metadata: Optional execution metadata

        Returns:
            str: The inserted document ID
        """
        # Convert metadata dict to ExecutionMetadata if needed
        if isinstance(metadata, dict):
            metadata = ExecutionMetadata(**metadata)

        log_entry = self.generate_log_entry(
            protocol, arguments, trigger_phrase, metadata
        )
        return await self.log_usage(log_entry.dict())

    async def get_usage_stats(
        self,
        protocol_name: Optional[str] = None,
        user: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get usage statistics for protocols with runtime-computed time analysis.

        Args:
            protocol_name: Filter by protocol name
            user: Filter by user
            days: Number of days to look back

        Returns:
            Dict containing usage statistics with computed time breakdowns
        """
        if self._collection is None:
            raise RuntimeError("Logger not connected.")

        from datetime import timedelta

        # Build filter
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        match_filter = {"timestamp_utc": {"$gte": cutoff}}

        if protocol_name:
            match_filter["protocol_name"] = protocol_name
        if user:
            match_filter["user"] = user

        # Aggregation pipeline - compute time fields at query time
        pipeline = [
            {"$match": match_filter},
            {
                "$project": {
                    "protocol_name": 1,
                    "user": 1,
                    "timestamp_utc": 1,
                    "time_zone": 1,
                    "latency_ms": 1,
                    "day_of_week": {"$dayOfWeek": "$timestamp_utc"},
                    "hour": {"$hour": "$timestamp_utc"},
                    "date": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$timestamp_utc",
                        }
                    },
                }
            },
            {
                "$group": {
                    "_id": {
                        "protocol": "$protocol_name",
                        "day_of_week": "$day_of_week",
                        "hour": "$hour",
                        "time_zone": "$time_zone",
                    },
                    "count": {"$sum": 1},
                    "avg_latency": {"$avg": "$latency_ms"},
                }
            },
            {"$sort": {"count": -1}},
        ]

        results = await self._collection.aggregate(pipeline).to_list(None)

        # Get total count
        total_count = await self._collection.count_documents(match_filter)

        # Compute time of day distribution with timezone awareness
        time_distribution = {}
        timezone_distribution = {}

        for result in results:
            hour = result["_id"]["hour"]
            tz = result["_id"].get("time_zone", "UTC")

            # Track timezone distribution
            if tz not in timezone_distribution:
                timezone_distribution[tz] = 0
            timezone_distribution[tz] += result["count"]

            # For time of day, we could convert to local time if needed
            time_of_day = TimeOfDay.from_hour(hour).value
            if time_of_day not in time_distribution:
                time_distribution[time_of_day] = 0
            time_distribution[time_of_day] += result["count"]

        return {
            "total_executions": total_count,
            "usage_by_time": results,
            "time_of_day_distribution": time_distribution,
            "timezone_distribution": timezone_distribution,
            "filter_applied": match_filter,
        }

    async def get_recent_logs(
        self,
        limit: int = 100,
        protocol_name: Optional[str] = None,
        user: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent logs with computed time fields using stored timezone.

        Args:
            limit: Maximum number of logs to return
            protocol_name: Filter by protocol name
            user: Filter by user

        Returns:
            List of log entries with computed time fields
        """
        if self._collection is None:
            raise RuntimeError("Logger not connected.")

        # Build filter
        match_filter = {}
        if protocol_name:
            match_filter["protocol_name"] = protocol_name
        if user:
            match_filter["user"] = user

        # Query logs
        cursor = (
            self._collection.find(match_filter).sort("timestamp_utc", -1).limit(limit)
        )
        logs = await cursor.to_list(None)

        # Add computed fields to each log
        for log in logs:
            timestamp = log["timestamp_utc"]
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

            # Use stored timezone for local time computations
            tz_str = log.get("time_zone", "UTC")

            # Add computed time fields for display purposes only
            log["_computed"] = {
                "day_of_week": get_day_of_week(timestamp, tz_str),
                "hour": timestamp.hour,
                "time_of_day": get_time_of_day(timestamp, tz_str).value,
                "local_time": None,
            }

            # Try to compute local time if timezone is available
            if tz_str and tz_str != "UTC":
                try:
                    local_tz = ZoneInfo(tz_str)
                    local_time = timestamp.astimezone(local_tz)
                    log["_computed"]["local_time"] = local_time.isoformat()
                    log["_computed"]["hour"] = local_time.hour
                except Exception:
                    pass

        return logs


# Backwards compatible function
def generate_protocol_log(
    protocol: Protocol,
    arguments: Dict[str, Any],
    trigger_phrase: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Legacy function for generating protocol logs.
    Updated to use clean schema with timezone.
    """
    # Convert metadata dict to ExecutionMetadata object
    exec_metadata = None
    if metadata:
        exec_metadata = ExecutionMetadata(**metadata)

    # Create a temporary logger instance just for generation
    logger = ProtocolUsageLogger()
    log_entry = logger.generate_log_entry(
        protocol, arguments, trigger_phrase, exec_metadata
    )

    # Convert back to dict for backwards compatibility
    return log_entry.dict()


# Convenience functions
@asynccontextmanager
async def create_logger(
    mongo_uri: str = "mongodb://localhost:27017",
    db_name: str = "jarvis",
) -> ProtocolUsageLogger:
    """
    Create and yield a connected ProtocolUsageLogger.

    Example:
        async with create_logger() as logger:
            await logger.log_usage_structured(protocol, args)
    """
    logger = ProtocolUsageLogger(
        mongo_uri=mongo_uri,
        db_name=db_name,
    )
    await logger.connect()
    try:
        yield logger
    finally:
        await logger.close()


# Example usage
if __name__ == "__main__":

    async def example_usage():
        """Demonstrate clean logger usage with timezone support."""

        # Create a protocol using your existing class
        protocol = Protocol(
            id="test_123",
            name="test_protocol",
            description="A test protocol",
            trigger_phrases=["run test", "test protocol"],
            steps=[
                ProtocolStep(
                    agent="test_agent",
                    function="test_function",
                    parameters={"param": "value"},
                )
            ],
        )

        # Using context manager
        async with create_logger() as logger:
            # Log with clean schema (timezone is detected automatically)
            metadata = ExecutionMetadata(
                device="laptop",
                user="john_doe",
                latency_ms=123.45,
                execution_result="success",
            )

            doc_id = await logger.log_usage_structured(
                protocol=protocol,
                arguments={"test": "value"},
                trigger_phrase="run test",
                metadata=metadata,
            )
            print(f"Logged with ID: {doc_id}")

            # Get usage stats (with runtime-computed time analysis)
            stats = await logger.get_usage_stats(days=7)
            print(f"Stats: {stats}")
            print(f"Timezone distribution: {stats.get('timezone_distribution', {})}")

            # Get recent logs with computed fields using timezone
            recent = await logger.get_recent_logs(limit=5)
            for log in recent:
                computed = log.get("_computed", {})
                print(
                    f"Protocol: {log['protocol_name']}, "
                    f"UTC Time: {log['timestamp_utc']}, "
                    f"Timezone: {log.get('time_zone', 'UTC')}, "
                    f"Local Time: {computed.get('local_time', 'N/A')}, "
                    f"Day: {computed.get('day_of_week')}, "
                    f"Time of Day: {computed.get('time_of_day')}"
                )

    # Run example
    asyncio.run(example_usage())
