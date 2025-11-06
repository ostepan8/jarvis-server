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
                tz_map = {
                    "Eastern Standard Time": "America/New_York",
                    "Central Standard Time": "America/Chicago",
                    "Mountain Standard Time": "America/Denver",
                    "Pacific Standard Time": "America/Los_Angeles",
                }
                return tz_map.get(windows_tz, "UTC")
        else:
            # Unix-like systems
            import os

            if os.path.exists("/etc/timezone"):
                with open("/etc/timezone", "r") as f:
                    return f.read().strip()
            elif os.path.exists("/etc/localtime"):
                import pathlib

                tz_path = pathlib.Path("/etc/localtime").resolve()
                tz_str = str(tz_path)
                if "/zoneinfo/" in tz_str:
                    return tz_str.split("/zoneinfo/")[-1]
        return "UTC"  # Default fallback

except ImportError:

    def get_system_timezone() -> str:
        return "UTC"


# Import Protocol data models
from ..models import Protocol, ProtocolStep


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
    """Clean log entry for protocol execution - essential fields only."""

    protocol_name: str
    protocol_id: str
    extracted_args: Dict[str, Any] = Field(default_factory=dict)
    trigger_phrase: Optional[str] = None
    matched_phrase: Optional[str] = None
    timestamp_utc: datetime
    time_zone: str
    success: bool
    latency_ms: Optional[float] = None

    # Optional metadata
    user: Optional[str] = None
    device: Optional[str] = None
    location: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# Logger implementation
@dataclass
class ProtocolUsageLogger:
    """Async MongoDB logger for protocol execution tracking."""

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

    async def connect(self) -> None:
        """Establish connection to MongoDB and create indexes."""
        try:
            self._client = AsyncIOMotorClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=self.connection_timeout_ms,
                maxPoolSize=self.max_pool_size,
            )

            # Test connection
            await self._client.admin.command("ping")

            self._collection = self._client[self.db_name][self.collection_name]
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
            ("success", 1),
            ("user", 1),
            ("device", 1),
            ("matched_phrase", 1),
            ([("protocol_name", 1), ("timestamp_utc", -1)], None),
            ([("user", 1), ("timestamp_utc", -1)], None),
            ([("time_zone", 1), ("timestamp_utc", -1)], None),
            ([("success", 1), ("timestamp_utc", -1)], None),
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
        extracted_args: Dict[str, Any],
        trigger_phrase: Optional[str] = None,
        matched_phrase: Optional[str] = None,
        success: bool = True,
        latency_ms: Optional[float] = None,
        metadata: Optional[ExecutionMetadata] = None,
    ) -> ProtocolLogEntry:
        """Generate a clean log entry for protocol execution."""

        metadata = metadata or ExecutionMetadata()

        return ProtocolLogEntry(
            protocol_name=protocol.name,
            protocol_id=protocol.id,
            extracted_args=extracted_args or {},
            trigger_phrase=trigger_phrase,
            matched_phrase=matched_phrase,
            timestamp_utc=datetime.now(timezone.utc),
            time_zone=get_system_timezone(),
            success=success,
            latency_ms=latency_ms,
            user=metadata.user,
            device=metadata.device,
            location=metadata.location,
        )

    async def log_usage(self, log_doc: Dict[str, Any]) -> str:
        """Log protocol usage to MongoDB."""
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
        extracted_args: Dict[str, Any],
        trigger_phrase: Optional[str] = None,
        matched_phrase: Optional[str] = None,
        success: bool = True,
        latency_ms: Optional[float] = None,
        metadata: Optional[Union[ExecutionMetadata, Dict[str, Any]]] = None,
    ) -> str:
        """Log protocol usage with structured parameters."""

        # Convert metadata dict to ExecutionMetadata if needed
        if isinstance(metadata, dict):
            metadata = ExecutionMetadata(**metadata)

        log_entry = self.generate_log_entry(
            protocol=protocol,
            extracted_args=extracted_args,
            trigger_phrase=trigger_phrase,
            matched_phrase=matched_phrase,
            success=success,
            latency_ms=latency_ms,
            metadata=metadata,
        )
        return await self.log_usage(log_entry.dict())

    async def get_recent_logs(
        self,
        limit: int = 100,
        protocol_name: Optional[str] = None,
        user: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent logs."""
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
        return logs


# Backwards compatible function - FIXED
def generate_protocol_log(
    protocol: Protocol,
    context: Dict[str, Any],  # This is extracted_args from executor
    trigger_phrase: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    extracted_arguments: Optional[
        Dict[str, Any]
    ] = None,  # Keep for compatibility but use context
    matched_phrase: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate protocol log dict - backwards compatible."""

    # Use context (which is extracted_args from executor) or fall back to extracted_arguments
    extracted_args = context or extracted_arguments or {}

    # Extract success and latency from metadata
    success = True
    latency_ms = None

    if metadata:
        # Check for execution_result to determine success
        exec_result = metadata.get("execution_result")
        if exec_result:
            if isinstance(exec_result, str):
                success = exec_result.lower() not in ["failure", "error", "failed"]
            elif isinstance(exec_result, dict):
                status = exec_result.get("status", "success")
                success = status.lower() not in ["failure", "error", "failed"]

        latency_ms = metadata.get("latency_ms")

        # Get matched_phrase from metadata if not provided
        if not matched_phrase:
            matched_phrase = metadata.get("matched_phrase")

    # Convert other metadata
    exec_metadata = None
    if metadata:
        exec_metadata = ExecutionMetadata(
            device=metadata.get("device"),
            location=metadata.get("location"),
            user=metadata.get("user"),
            source=metadata.get("source"),
            latency_ms=latency_ms,
        )

    logger = ProtocolUsageLogger()
    log_entry = logger.generate_log_entry(
        protocol=protocol,
        extracted_args=extracted_args,
        trigger_phrase=trigger_phrase,
        matched_phrase=matched_phrase,
        success=success,
        latency_ms=latency_ms,
        metadata=exec_metadata,
    )

    return log_entry.dict()


# Interaction Logging Models
class InteractionLogEntry(BaseModel):
    """Log entry for user interactions with Jarvis."""

    user_input: str
    intent: Optional[str] = None
    capability: Optional[str] = None
    protocol_executed: Optional[str] = None
    response: str
    agent_results: List[Dict[str, Any]] = Field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp_utc: datetime
    time_zone: str
    latency_ms: Optional[float] = None
    success: bool = True

    # Metadata
    user_id: Optional[int] = None
    device: Optional[str] = None
    location: Optional[str] = None
    source: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


@dataclass
class InteractionLogger:
    """Async MongoDB logger for user interaction history."""

    mongo_uri: str = "mongodb://localhost:27017"
    db_name: str = "protocol"
    collection_name: str = "interaction_history"
    connection_timeout_ms: int = 5000
    max_pool_size: int = 10

    # Internal state
    _client: Optional[AsyncIOMotorClient] = field(default=None, init=False)
    _collection: Optional[AsyncIOMotorCollection] = field(default=None, init=False)
    _logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger(__name__), init=False
    )

    async def connect(self) -> None:
        """Establish connection to MongoDB and create indexes."""
        try:
            self._client = AsyncIOMotorClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=self.connection_timeout_ms,
                maxPoolSize=self.max_pool_size,
            )

            # Test connection
            await self._client.admin.command("ping")

            self._collection = self._client[self.db_name][self.collection_name]
            await self._create_indexes()

            self._logger.info(f"Connected to MongoDB at {self.mongo_uri}")

        except Exception as e:
            self._logger.error(f"Failed to connect to MongoDB: {e}")
            raise ConnectionError(f"MongoDB connection failed: {e}") from e

    async def _create_indexes(self) -> None:
        """Create indexes for common query patterns."""
        indexes = [
            ("user_id", 1),
            ("timestamp_utc", -1),
            ("intent", 1),
            ("capability", 1),
            ("protocol_executed", 1),
            ([("user_id", 1), ("timestamp_utc", -1)], None),
            ([("intent", 1), ("timestamp_utc", -1)], None),
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

    async def log_interaction(
        self,
        user_input: str,
        response: str,
        intent: Optional[str] = None,
        capability: Optional[str] = None,
        protocol_executed: Optional[str] = None,
        agent_results: Optional[List[Dict[str, Any]]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        latency_ms: Optional[float] = None,
        success: bool = True,
        user_id: Optional[int] = None,
        device: Optional[str] = None,
        location: Optional[str] = None,
        source: Optional[str] = None,
    ) -> str:
        """Log a user interaction to MongoDB."""
        # Auto-connect if not connected
        if self._collection is None:
            try:
                await self.connect()
            except Exception as e:
                self._logger.error(f"Failed to auto-connect to MongoDB: {e}")
                return ""  # Fail silently to not break main flow

        try:
            log_entry = InteractionLogEntry(
                user_input=user_input,
                intent=intent,
                capability=capability,
                protocol_executed=protocol_executed,
                response=response,
                agent_results=agent_results or [],
                tool_calls=tool_calls or [],
                timestamp_utc=datetime.now(timezone.utc),
                time_zone=get_system_timezone(),
                latency_ms=latency_ms,
                success=success,
                user_id=user_id,
                device=device,
                location=location,
                source=source,
            )

            result = await self._collection.insert_one(log_entry.dict())
            self._logger.debug(
                f"Logged interaction: user_id={user_id}, intent={intent} (ID: {result.inserted_id})"
            )
            return str(result.inserted_id)

        except Exception as e:
            self._logger.error(f"Failed to log interaction: {e}")
            return ""  # Fail silently

    async def get_recent_interactions(
        self,
        limit: int = 100,
        user_id: Optional[int] = None,
        intent: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent interactions."""
        if self._collection is None:
            raise RuntimeError("Logger not connected.")

        # Build filter
        match_filter = {}
        if user_id is not None:
            match_filter["user_id"] = user_id
        if intent:
            match_filter["intent"] = intent

        # Query interactions
        cursor = (
            self._collection.find(match_filter).sort("timestamp_utc", -1).limit(limit)
        )
        interactions = await cursor.to_list(None)
        return interactions


# Convenience functions
@asynccontextmanager
async def create_logger(
    mongo_uri: str = "mongodb://localhost:27017",
    db_name: str = "jarvis",
) -> ProtocolUsageLogger:
    """Create and yield a connected ProtocolUsageLogger."""
    logger = ProtocolUsageLogger(mongo_uri=mongo_uri, db_name=db_name)
    await logger.connect()
    try:
        yield logger
    finally:
        await logger.close()


@asynccontextmanager
async def create_interaction_logger(
    mongo_uri: str = "mongodb://localhost:27017",
    db_name: str = "protocol",
) -> InteractionLogger:
    """Create and yield a connected InteractionLogger."""
    logger = InteractionLogger(mongo_uri=mongo_uri, db_name=db_name)
    await logger.connect()
    try:
        yield logger
    finally:
        await logger.close()
