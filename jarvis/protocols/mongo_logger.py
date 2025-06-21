"""Backward compatibility wrapper for protocol logging."""
from __future__ import annotations

from typing import Any, Dict

from ..loggers.protocol_logger import (
    ProtocolUsageLogger,
    generate_protocol_log,
)

__all__ = ["ProtocolUsageLogger", "generate_protocol_log"]
