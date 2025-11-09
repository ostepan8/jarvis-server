"""Response logger for interaction tracking and analytics.

This module provides centralized logging of user interactions, responses,
and system performance metrics.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..protocols.loggers import InteractionLogger


class ResponseLogger:
    """Centralized logger for user interactions and responses.
    
    This class handles logging of all user-system interactions, including
    request metadata, response data, performance metrics, and error tracking.
    """
    
    def __init__(self, interaction_logger: "InteractionLogger"):
        """Initialize response logger.
        
        Args:
            interaction_logger: MongoDB logger for interaction data
        """
        self.interaction_logger = interaction_logger
    
    async def log_successful_interaction(
        self,
        user_input: str,
        response: str,
        intent: Optional[str] = None,
        capability: Optional[str] = None,
        protocol_executed: Optional[str] = None,
        agent_results: Optional[Any] = None,
        tool_calls: Optional[Any] = None,
        latency_ms: float = 0.0,
        user_id: Optional[int] = None,
        device: Optional[str] = None,
        location: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        """Log a successful user interaction.
        
        Args:
            user_input: The user's request
            response: The system's response
            intent: Classified intent (optional)
            capability: Capability that was invoked (optional)
            protocol_executed: Protocol name if one was executed (optional)
            agent_results: Results from agent execution (optional)
            tool_calls: Tool calls made during execution (optional)
            latency_ms: Response time in milliseconds
            user_id: ID of the user making the request
            device: Device identifier
            location: User location
            source: Request source (cli, api, etc.)
        """
        asyncio.create_task(
            self.interaction_logger.log_interaction(
                user_input=user_input,
                response=response,
                intent=intent,
                capability=capability,
                protocol_executed=protocol_executed,
                agent_results=agent_results,
                tool_calls=tool_calls,
                latency_ms=latency_ms,
                success=True,
                user_id=user_id,
                device=device,
                location=location,
                source=source,
            )
        )
    
    async def log_failed_interaction(
        self,
        user_input: str,
        error_message: str,
        intent: Optional[str] = None,
        capability: Optional[str] = None,
        protocol_executed: Optional[str] = None,
        latency_ms: float = 0.0,
        user_id: Optional[int] = None,
        device: Optional[str] = None,
        location: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        """Log a failed user interaction.
        
        Args:
            user_input: The user's request
            error_message: Error message describing the failure
            intent: Classified intent (optional)
            capability: Capability that was attempted (optional)
            protocol_executed: Protocol name if one was attempted (optional)
            latency_ms: Time before failure in milliseconds
            user_id: ID of the user making the request
            device: Device identifier
            location: User location
            source: Request source (cli, api, etc.)
        """
        asyncio.create_task(
            self.interaction_logger.log_interaction(
                user_input=user_input,
                response=error_message,
                intent=intent,
                capability=capability,
                protocol_executed=protocol_executed,
                latency_ms=latency_ms,
                success=False,
                user_id=user_id,
                device=device,
                location=location,
                source=source,
            )
        )
    
    async def close(self) -> None:
        """Close the interaction logger."""
        if self.interaction_logger:
            await self.interaction_logger.close()


class RequestTimer:
    """Context manager for timing requests.
    
    Simple utility to track request latency.
    """
    
    def __init__(self):
        self.start_time: float = 0.0
        self.end_time: float = 0.0
    
    def start(self) -> "RequestTimer":
        """Start timing."""
        self.start_time = time.time()
        return self
    
    def stop(self) -> float:
        """Stop timing and return elapsed milliseconds."""
        self.end_time = time.time()
        return self.elapsed_ms()
    
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return (time.time() - self.start_time) * 1000
    
    def __enter__(self) -> "RequestTimer":
        """Context manager entry."""
        return self.start()
    
    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.stop()

