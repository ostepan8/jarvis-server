"""Retryable HTTP client with exponential backoff for external service calls.

This module provides a wrapper around httpx.AsyncClient that automatically
retries failed requests with configurable exponential backoff.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, TYPE_CHECKING
import httpx

if TYPE_CHECKING:
    from ..logging import JarvisLogger
    from ..core.errors import (
        ServiceUnavailableError,
        TimeoutError as JarvisTimeoutError,
    )


class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        retry_on_timeout: Whether to retry on timeout errors
        retry_on_connection_error: Whether to retry on connection errors
        retry_on_status_codes: HTTP status codes that should trigger retries
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        retry_on_timeout: bool = True,
        retry_on_connection_error: bool = True,
        retry_on_status_codes: Optional[set[int]] = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retry_on_timeout = retry_on_timeout
        self.retry_on_connection_error = retry_on_connection_error

        # Default: retry on 5xx server errors and 429 rate limiting
        if retry_on_status_codes is None:
            retry_on_status_codes = {429, 500, 502, 503, 504}
        self.retry_on_status_codes = retry_on_status_codes

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number.

        Uses exponential backoff: delay = base_delay * (exponential_base ** attempt)
        Capped at max_delay.

        Args:
            attempt: The retry attempt number (0-indexed)

        Returns:
            Delay in seconds before next retry
        """
        delay = self.base_delay * (self.exponential_base**attempt)
        return min(delay, self.max_delay)


class RetryableHTTPClient:
    """HTTP client with automatic retry logic and exponential backoff.

    This class wraps httpx.AsyncClient and adds intelligent retry behavior
    for transient failures like network errors, timeouts, and server errors.
    """

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        logger: Optional["JarvisLogger"] = None,
        **httpx_kwargs: Any,
    ):
        """Initialize retryable HTTP client.

        Args:
            retry_config: Configuration for retry behavior (uses defaults if None)
            logger: Optional logger for recording retry attempts
            **httpx_kwargs: Additional keyword arguments passed to httpx.AsyncClient
        """
        self.retry_config = retry_config or RetryConfig()
        self.logger = logger

        # Create underlying httpx client
        self._client = httpx.AsyncClient(**httpx_kwargs)

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with automatic retries.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            **kwargs: Additional arguments passed to httpx request

        Returns:
            httpx.Response object

        Raises:
            ServiceUnavailableError: If all retries are exhausted
            JarvisTimeoutError: If request times out after retries
        """
        last_exception: Optional[Exception] = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Make the request
                response = await self._client.request(method, url, **kwargs)

                # Check if status code should trigger retry
                if response.status_code in self.retry_config.retry_on_status_codes:
                    if attempt < self.retry_config.max_retries:
                        await self._log_and_wait(
                            attempt,
                            f"HTTP {response.status_code}",
                            url,
                        )
                        continue
                    else:
                        # Last attempt, raise the error
                        response.raise_for_status()

                # Success! Return the response
                return response

            except httpx.TimeoutException as exc:
                last_exception = exc
                if (
                    self.retry_config.retry_on_timeout
                    and attempt < self.retry_config.max_retries
                ):
                    await self._log_and_wait(attempt, "Timeout", url)
                    continue
                else:
                    # No more retries or timeout retry disabled - import here to avoid circular dependency
                    from ..core.errors import TimeoutError as JarvisTimeoutError

                    raise JarvisTimeoutError(
                        f"Request to {url} timed out after {attempt + 1} attempts",
                        details={"url": url, "attempts": attempt + 1},
                    )

            except (httpx.ConnectError, httpx.NetworkError) as exc:
                last_exception = exc
                if (
                    self.retry_config.retry_on_connection_error
                    and attempt < self.retry_config.max_retries
                ):
                    await self._log_and_wait(attempt, "Connection error", url)
                    continue
                else:
                    # No more retries - import here to avoid circular dependency
                    from ..core.errors import ServiceUnavailableError

                    raise ServiceUnavailableError(
                        f"Failed to connect to {url} after {attempt + 1} attempts",
                        details={"url": url, "attempts": attempt + 1},
                        retry_after=60,
                    )

            except httpx.HTTPStatusError as exc:
                # Don't retry 4xx client errors (except 429 which is handled above)
                if 400 <= exc.response.status_code < 500:
                    raise

                # Retry 5xx server errors
                last_exception = exc
                if attempt < self.retry_config.max_retries:
                    await self._log_and_wait(
                        attempt,
                        f"HTTP {exc.response.status_code}",
                        url,
                    )
                    continue
                else:
                    # Import here to avoid circular dependency
                    from ..core.errors import ServiceUnavailableError

                    raise ServiceUnavailableError(
                        f"Service error from {url}: {exc.response.status_code}",
                        details={
                            "url": url,
                            "status_code": exc.response.status_code,
                            "attempts": attempt + 1,
                        },
                        retry_after=30,
                    )

        # Should not reach here, but just in case
        # Import here to avoid circular dependency
        from ..core.errors import ServiceUnavailableError

        if last_exception:
            raise ServiceUnavailableError(
                f"Request to {url} failed after {self.retry_config.max_retries + 1} attempts",
                details={"url": url, "last_error": str(last_exception)},
            )

        raise ServiceUnavailableError(f"Request to {url} failed unexpectedly")

    async def _log_and_wait(self, attempt: int, reason: str, url: str) -> None:
        """Log retry attempt and wait before retrying.

        Args:
            attempt: Current attempt number (0-indexed)
            reason: Reason for retry
            url: URL being retried
        """
        delay = self.retry_config.get_delay(attempt)

        if self.logger:
            self.logger.log(
                "WARNING",
                f"Retrying request (attempt {attempt + 1}/{self.retry_config.max_retries})",
                {
                    "url": url,
                    "reason": reason,
                    "delay_seconds": delay,
                    "next_attempt": attempt + 2,
                },
            )

        await asyncio.sleep(delay)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a GET request with retries."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a POST request with retries."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a PUT request with retries."""
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a PATCH request with retries."""
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a DELETE request with retries."""
        return await self.request("DELETE", url, **kwargs)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "RetryableHTTPClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.aclose()

    @property
    def headers(self) -> httpx.Headers:
        """Access to underlying client headers."""
        return self._client.headers

    @property
    def cookies(self) -> httpx.Cookies:
        """Access to underlying client cookies."""
        return self._client.cookies
