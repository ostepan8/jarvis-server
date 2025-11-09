"""Circuit breaker pattern implementation for handling repeated failures.

This module provides a circuit breaker to prevent cascading failures when
external services are down or experiencing issues.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Optional, TYPE_CHECKING

from ..core.errors import ServiceUnavailableError

if TYPE_CHECKING:
    from ..logging import JarvisLogger


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"      # Failures detected, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures.
    
    The circuit breaker monitors failures and "opens" when a threshold
    is reached, preventing further requests to a failing service. After
    a timeout, it enters "half-open" state to test if the service has
    recovered.
    
    States:
        - CLOSED: Normal operation, all requests pass through
        - OPEN: Too many failures, requests are immediately rejected
        - HALF_OPEN: Testing recovery, limited requests allowed
    
    Attributes:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before testing recovery
        half_open_max_calls: Max calls allowed in half-open state
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        logger: Optional["JarvisLogger"] = None,
        name: str = "default",
    ):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying again
            half_open_max_calls: Number of test calls in half-open state
            logger: Optional logger for recording state changes
            name: Name of this circuit breaker (for logging)
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.logger = logger
        self.name = name
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self._state == CircuitState.OPEN
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED
    
    async def call(
        self,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a function through the circuit breaker.
        
        Args:
            func: Function to execute (can be sync or async)
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of the function call
            
        Raises:
            ServiceUnavailableError: If circuit is open
            Exception: Any exception raised by the function
        """
        # Check if we should allow this call
        await self._check_and_update_state()
        
        if self._state == CircuitState.OPEN:
            raise ServiceUnavailableError(
                f"Circuit breaker '{self.name}' is open - service unavailable",
                details={
                    "circuit_name": self.name,
                    "state": self._state.value,
                    "failure_count": self._failure_count,
                },
                retry_after=int(self.recovery_timeout),
            )
        
        if self._state == CircuitState.HALF_OPEN:
            async with self._lock:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise ServiceUnavailableError(
                        f"Circuit breaker '{self.name}' is testing recovery - please wait",
                        details={
                            "circuit_name": self.name,
                            "state": self._state.value,
                        },
                        retry_after=5,
                    )
                self._half_open_calls += 1
        
        # Execute the function
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Success! Record it
            await self._on_success()
            return result
            
        except Exception as exc:
            # Failure! Record it
            await self._on_failure()
            raise
    
    async def _check_and_update_state(self) -> None:
        """Check if state should transition based on timeout."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    await self._transition_to_half_open()
    
    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Success in half-open state - close the circuit
                await self._transition_to_closed()
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                if self._failure_count > 0:
                    self._failure_count = 0
    
    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                # Failed during recovery test - reopen circuit
                await self._transition_to_open()
            
            elif self._state == CircuitState.CLOSED:
                # Check if we should open the circuit
                if self._failure_count >= self.failure_threshold:
                    await self._transition_to_open()
    
    async def _transition_to_open(self) -> None:
        """Transition circuit to OPEN state."""
        old_state = self._state
        self._state = CircuitState.OPEN
        self._half_open_calls = 0
        
        if self.logger:
            self.logger.log(
                "WARNING",
                f"Circuit breaker '{self.name}' opened",
                {
                    "circuit_name": self.name,
                    "old_state": old_state.value,
                    "new_state": self._state.value,
                    "failure_count": self._failure_count,
                    "recovery_timeout": self.recovery_timeout,
                }
            )
    
    async def _transition_to_half_open(self) -> None:
        """Transition circuit to HALF_OPEN state."""
        old_state = self._state
        self._state = CircuitState.HALF_OPEN
        self._half_open_calls = 0
        
        if self.logger:
            self.logger.log(
                "INFO",
                f"Circuit breaker '{self.name}' entering half-open state",
                {
                    "circuit_name": self.name,
                    "old_state": old_state.value,
                    "new_state": self._state.value,
                }
            )
    
    async def _transition_to_closed(self) -> None:
        """Transition circuit to CLOSED state."""
        old_state = self._state
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
        
        if self.logger:
            self.logger.log(
                "INFO",
                f"Circuit breaker '{self.name}' closed - service recovered",
                {
                    "circuit_name": self.name,
                    "old_state": old_state.value,
                    "new_state": self._state.value,
                }
            )
    
    async def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            self._last_failure_time = None
            
            if self.logger:
                self.logger.log(
                    "INFO",
                    f"Circuit breaker '{self.name}' manually reset",
                    {"circuit_name": self.name}
                )
    
    def get_stats(self) -> dict[str, Any]:
        """Get current circuit breaker statistics.
        
        Returns:
            Dict with current state, failure count, etc.
        """
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self._last_failure_time,
            "recovery_timeout": self.recovery_timeout,
            "half_open_calls": self._half_open_calls if self._state == CircuitState.HALF_OPEN else 0,
        }


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers.
    
    This class provides a centralized way to create and access circuit
    breakers for different services.
    """
    
    def __init__(self, logger: Optional["JarvisLogger"] = None):
        """Initialize circuit breaker registry.
        
        Args:
            logger: Optional logger for all circuit breakers
        """
        self.logger = logger
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
    
    async def get_breaker(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> CircuitBreaker:
        """Get or create a circuit breaker by name.
        
        Args:
            name: Unique name for the circuit breaker
            failure_threshold: Number of failures before opening
            recovery_timeout: Seconds to wait before testing recovery
            
        Returns:
            CircuitBreaker instance
        """
        if name not in self._breakers:
            async with self._lock:
                # Double-check after acquiring lock
                if name not in self._breakers:
                    self._breakers[name] = CircuitBreaker(
                        failure_threshold=failure_threshold,
                        recovery_timeout=recovery_timeout,
                        logger=self.logger,
                        name=name,
                    )
        
        return self._breakers[name]
    
    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all circuit breakers.
        
        Returns:
            Dict mapping breaker names to their stats
        """
        return {
            name: breaker.get_stats()
            for name, breaker in self._breakers.items()
        }
    
    async def reset_all(self) -> None:
        """Reset all circuit breakers to closed state."""
        for breaker in self._breakers.values():
            await breaker.reset()

