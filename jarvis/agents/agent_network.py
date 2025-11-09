# agents/agent_network.py

from __future__ import annotations

import asyncio
import time
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..logging import JarvisLogger
from ..protocols import InstructionProtocol
from ..core.method_recorder import MethodRecorder
from .message import Message
from .response_aggregator import ResponseAggregator, AggregationStrategy

if TYPE_CHECKING:
    from .base import NetworkAgent  # for type hints only
    from ..core.method_recorder_base import MethodRecorderBase


class MessagePriority(IntEnum):
    """Message priority levels - higher numbers = higher priority."""

    LOW = 1
    NORMAL = 2
    HIGH = 3  # Responses and errors


class AgentNetwork:
    """Central message broker for agent communication."""

    def __init__(
        self,
        logger: Optional[JarvisLogger] = None,
        queue_maxsize: int = 1000,
        record_methods: bool = False,
        recorder: "MethodRecorderBase | None" = None,
        future_ttl: float = 300.0,  # 5 minutes default TTL
        cleanup_interval: float = 60.0,  # Cleanup every minute
        worker_count: int = 1,  # Number of parallel message processors
    ) -> None:
        self.agents: Dict[str, NetworkAgent] = {}

        # Priority-based message queues
        self._high_priority_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self._normal_priority_queue: asyncio.Queue = asyncio.Queue(
            maxsize=queue_maxsize
        )
        self._low_priority_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)

        # Legacy queue for backward compatibility (deprecated)
        self.message_queue: asyncio.Queue = self._normal_priority_queue

        self.capability_registry: Dict[str, List[str]] = {}
        # Track night agents separately so we can enable them later
        self.night_agents: Dict[str, NetworkAgent] = {}
        self.night_capability_registry: Dict[str, List[str]] = {}
        self.logger = logger or JarvisLogger()
        self._running = False
        self._processor_tasks: List[asyncio.Task] = []
        self._cleanup_task: Optional[asyncio.Task] = None
        self._worker_count = max(1, worker_count)  # At least 1 worker

        # For tracking in-flight request futures with TTL
        self._response_futures: Dict[str, Tuple[asyncio.Future, float]] = {}
        self._future_ttl = future_ttl
        self._cleanup_interval = cleanup_interval

        # Reusable JARVIS protocols registry
        self.protocol_registry: List[str] = []

        # Response aggregation service
        self.response_aggregator = ResponseAggregator(
            logger=self.logger,
            default_timeout=future_ttl,
        )

        # Metrics tracking
        self._metrics: Dict[str, Any] = {
            "direct_messages": 0,
            "queued_messages": 0,
            "broadcast_messages": 0,
            "future_cleanups": 0,
            "dropped_messages": 0,
            "backpressure_events": 0,
        }

        # Backpressure thresholds
        self._backpressure_threshold = int(queue_maxsize * 0.8)  # 80% full
        self._circuit_breaker_threshold = int(queue_maxsize * 0.95)  # 95% full
        self._circuit_breaker_active = False

        self.method_recorder: MethodRecorder | None = (
            recorder
            if recorder is not None
            else (MethodRecorder() if record_methods else None)
        )
        if self.method_recorder:
            self.logger.log(
                "INFO",
                "Method recording enabled",
                f"Recorder: {self.method_recorder.__class__.__name__}",
            )

        # Method recording via MethodRecorder
        self.record_methods = record_methods
        self.recorder = recorder

    def register_agent(
        self,
        agent: NetworkAgent,
        include_capabilities: bool = True,
        night_agent: bool = False,
    ) -> None:
        """Register an agent with the network."""
        self.agents[agent.name] = agent
        if night_agent:
            self.night_agents[agent.name] = agent
            # Always remember night capabilities for later activation
            for capability in agent.capabilities:
                self.night_capability_registry.setdefault(capability, []).append(
                    agent.name
                )
        agent.set_network(self)

        if include_capabilities:
            for capability in agent.capabilities:
                self.capability_registry.setdefault(capability, []).append(agent.name)

        self.logger.log(
            "INFO",
            f"Agent registered: {agent.name}",
            f"Capabilities: {agent.capabilities}",
        )

        # If this agent has a 'protocols' attribute, register them
        if hasattr(agent, "protocols"):
            self.protocol_registry = list(getattr(agent, "protocols").keys())

    def register_night_agent(
        self,
        agent: NetworkAgent,
        include_capabilities: bool = False,
    ) -> None:
        """Convenience wrapper to register a night agent."""
        self.register_agent(
            agent,
            include_capabilities=include_capabilities,
            night_agent=True,
        )

    def add_agent_capabilities(self, agent: NetworkAgent) -> None:
        """Activate an agent's capabilities on the network."""
        for capability in agent.capabilities:
            self.capability_registry.setdefault(capability, []).append(agent.name)

    def remove_agent_capabilities(self, agent: NetworkAgent) -> None:
        """Remove an agent's capabilities from the network."""
        for capability in list(agent.capabilities):
            providers = self.capability_registry.get(capability, [])
            if agent.name in providers:
                providers = [p for p in providers if p != agent.name]
                if providers:
                    self.capability_registry[capability] = providers
                else:
                    del self.capability_registry[capability]

    def _get_message_priority(self, message: Message) -> MessagePriority:
        """Determine message priority based on type."""
        if message.message_type in ("capability_response", "error"):
            return MessagePriority.HIGH
        elif message.message_type == "capability_request":
            return MessagePriority.NORMAL
        else:
            return MessagePriority.LOW

    async def send_message(
        self, message: Message, priority: Optional[MessagePriority] = None
    ) -> None:
        """
        Enqueue a message for delivery with priority-based routing.

        For direct messages (to_agent set), attempts fast-path delivery.
        Falls back to queue if fast-path fails.
        """
        # Fast-path: Direct messages to known agents bypass queue
        if message.to_agent and message.to_agent in self.agents:
            try:
                # Try immediate delivery (non-blocking)
                agent = self.agents[message.to_agent]
                # Use create_task for async delivery without blocking
                asyncio.create_task(agent.receive_message(message))
                self._metrics["direct_messages"] += 1
                self.logger.log(
                    "DEBUG",
                    "Fast-path direct message",
                    f"{message.from_agent} -> {message.to_agent}: {message.message_type}",
                )
                return
            except Exception as e:
                self.logger.log(
                    "WARNING",
                    "Fast-path delivery failed, falling back to queue",
                    str(e),
                )
                # Fall through to queue-based delivery

        # Queue-based delivery with priority
        if priority is None:
            priority = self._get_message_priority(message)

        target_queue = {
            MessagePriority.HIGH: self._high_priority_queue,
            MessagePriority.NORMAL: self._normal_priority_queue,
            MessagePriority.LOW: self._low_priority_queue,
        }[priority]

        # Check backpressure before enqueueing
        queue_size = target_queue.qsize()

        # Circuit breaker: reject all but critical messages if queue is nearly full
        if queue_size >= self._circuit_breaker_threshold:
            if priority != MessagePriority.HIGH:
                self._metrics["dropped_messages"] += 1
                self._metrics["backpressure_events"] += 1
                self.logger.log(
                    "WARNING",
                    f"Circuit breaker active - dropping {priority.name} priority message",
                    f"Queue size: {queue_size}/{target_queue.maxsize}, Type: {message.message_type}",
                )
                return
            self._circuit_breaker_active = True

        # Backpressure warning: try to make room for high-priority messages
        elif (
            queue_size >= self._backpressure_threshold
            and priority == MessagePriority.HIGH
        ):
            self._metrics["backpressure_events"] += 1
            # Try to make room by dropping low-priority messages
            try:
                for _ in range(min(3, self._low_priority_queue.qsize())):
                    try:
                        self._low_priority_queue.get_nowait()
                        self._metrics["dropped_messages"] += 1
                    except asyncio.QueueEmpty:
                        break
            except Exception:
                pass

        # Reset circuit breaker if queue has space
        if queue_size < self._backpressure_threshold:
            self._circuit_breaker_active = False

        try:
            await target_queue.put(message)
            self._metrics["queued_messages"] += 1
            if message.message_type == "capability_response":
                self.logger.log(
                    "INFO",
                    f"Queued capability_response message",
                    f"request_id={message.request_id}, to_agent={message.to_agent}, priority={priority.name}, queue_size={target_queue.qsize()}",
                )
        except asyncio.QueueFull:
            self.logger.log(
                "WARNING",
                f"Queue full for priority {priority.name}",
                f"Message type: {message.message_type}",
            )
            # For high-priority messages, try to make room
            if priority == MessagePriority.HIGH:
                try:
                    # Try to get and discard a low-priority message
                    try:
                        self._low_priority_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    await target_queue.put(message)
                except Exception:
                    # Last resort: log and drop
                    self._metrics["dropped_messages"] += 1
                    self.logger.log(
                        "ERROR",
                        "Failed to enqueue high-priority message",
                        f"Message dropped: {message.message_type}",
                    )
            else:
                self._metrics["dropped_messages"] += 1

    async def start(self) -> None:
        """Start the message processing loop and cleanup task."""
        self._running = True
        # Start worker pool for parallel message processing
        for i in range(self._worker_count):
            task = asyncio.create_task(self._process_messages(worker_id=i))
            self._processor_tasks.append(task)
        self._cleanup_task = asyncio.create_task(self._cleanup_futures_loop())
        await self.response_aggregator.start()
        self.logger.log(
            "INFO",
            "Network started",
            f"Workers: {self._worker_count}",
        )

    async def stop(self) -> None:
        """Stop the message loop and wait for it to finish."""
        self._running = False
        # Wait for all worker tasks
        if self._processor_tasks:
            await asyncio.gather(*self._processor_tasks, return_exceptions=True)
            self._processor_tasks.clear()
        if self._cleanup_task:
            await self._cleanup_task
        await self.response_aggregator.stop()
        self.logger.log("INFO", "Network stopped")

    # ------------------------------------------------------------------
    # Method recording helpers
    # ------------------------------------------------------------------
    def start_method_recording(
        self, name: str, description: str = ""
    ) -> InstructionProtocol | None:
        if not self.method_recorder:
            self.method_recorder = MethodRecorder()
        return self.method_recorder.start(name, description)

    def stop_method_recording(self) -> InstructionProtocol | None:
        if not self.method_recorder:
            return None
        return self.method_recorder.stop()

    def get_recorded_protocol(self) -> InstructionProtocol | None:
        if not self.method_recorder:
            return None
        return self.method_recorder.get_protocol()

    async def _get_next_message(self) -> Optional[Message]:
        """Get next message from priority queues (high -> normal -> low)."""
        # Check high priority first
        try:
            return self._high_priority_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

        # Then normal priority
        try:
            return self._normal_priority_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

        # Finally low priority
        try:
            return self._low_priority_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _process_messages(self, worker_id: int = 0) -> None:
        """Internal loop: dispatch messages, broadcast requests, fulfill responses."""
        while self._running:
            try:
                # Try to get message from any priority queue
                message = await self._get_next_message_with_timeout()

                if message is None:
                    continue

                if message.message_type == "capability_response":
                    self.logger.log(
                        "INFO",
                        f"[WORKER] Processing capability_response message (worker {worker_id})",
                        f"{message.from_agent} -> {message.to_agent or 'ALL'}: request_id={message.request_id}",
                    )
                else:
                    self.logger.log(
                        "DEBUG",
                        f"Processing message (worker {worker_id})",
                        f"{message.from_agent} -> {message.to_agent or 'ALL'}: {message.message_type}",
                    )

                # 1) If it's a response to a capability_request, fulfill the Future
                if message.message_type == "capability_response":
                    self.logger.log(
                        "INFO",
                        f"[WORKER] About to call _handle_capability_response",
                        f"request_id={message.request_id}, worker={worker_id}",
                    )
                    await self._handle_capability_response(message)
                    self.logger.log(
                        "INFO",
                        f"[WORKER] Completed _handle_capability_response",
                        f"request_id={message.request_id}, worker={worker_id}",
                    )
                    continue

                # 2) If it's an error reply, treat it as a response too
                if message.message_type == "error":
                    await self._handle_error_message(message)
                    continue

                # 3) Direct message: deliver to the specified agent
                if message.to_agent:
                    if message.to_agent in self.agents:
                        asyncio.create_task(
                            self.agents[message.to_agent].receive_message(message)
                        )
                    continue

                # 4) Broadcast capability_request to all providers (batched)
                if message.message_type == "capability_request":
                    await self._handle_capability_request_broadcast(message)
                    continue

            except Exception as exc:
                self.logger.log(
                    "ERROR",
                    f"Message processing error (worker {worker_id})",
                    str(exc),
                )

    async def _get_next_message_with_timeout(self) -> Optional[Message]:
        """Get next message with timeout, checking priority queues."""
        # Wait for any queue with timeout
        try:
            # Use asyncio.wait to check all queues
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(self._high_priority_queue.get()),
                    asyncio.create_task(self._normal_priority_queue.get()),
                    asyncio.create_task(self._low_priority_queue.get()),
                ],
                timeout=0.1,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Get result from first completed
            if done:
                task = done.pop()
                return await task
        except asyncio.TimeoutError:
            pass

        return None

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle capability response message - fulfill future and optionally deliver to agent."""
        self.logger.log(
            "INFO",
            f"Handling capability_response for request {message.request_id}",
            f"from={message.from_agent}, to={message.to_agent}, content_keys={list(message.content.keys()) if isinstance(message.content, dict) else 'N/A'}",
        )

        fut_data = self._response_futures.get(message.request_id)
        self.logger.log(
            "INFO",
            f"[FUTURE_LOOKUP] Looking up future for request {message.request_id}",
            f"found={fut_data is not None}, available_futures={list(self._response_futures.keys())[:10]}",
        )

        if fut_data:
            fut, _ = fut_data
            fut_id = id(fut)
            self.logger.log(
                "INFO",
                f"[FUTURE_STATE] Future state before set_result",
                f"request_id={message.request_id}, done={fut.done()}, cancelled={fut.cancelled()}, fut_id={fut_id}",
            )
            if not fut.done():
                self.logger.log(
                    "INFO",
                    f"[FUTURE_FULFILL] Fulfilling future for request {message.request_id}",
                    f"from={message.from_agent}, to={message.to_agent}, content_type={type(message.content).__name__}, fut_id={fut_id}",
                )
                # Set the result directly - we're already in the event loop
                fut.set_result(message.content)
                self.logger.log(
                    "INFO",
                    f"[FUTURE_SET] set_result() called",
                    f"request_id={message.request_id}, done_after_set={fut.done()}, cancelled={fut.cancelled()}, fut_id={fut_id}",
                )
                # Yield to event loop to allow waiting coroutine to resume
                await asyncio.sleep(0)
                self.logger.log(
                    "INFO",
                    f"[FUTURE_YIELDED] Yielded to event loop after set_result",
                    f"request_id={message.request_id}, done={fut.done()}, cancelled={fut.cancelled()}, fut_id={fut_id}",
                )
                # Don't clean up here - let wait_for_response handle it
                self.logger.log(
                    "INFO",
                    f"[FUTURE_FULFILLED] Future fulfilled for request {message.request_id}",
                    f"done={fut.done()}, cancelled={fut.cancelled()}, fut_id={fut_id}",
                )
            else:
                self.logger.log(
                    "DEBUG",
                    f"Future already done for request {message.request_id}",
                    "",
                )
        else:
            self.logger.log(
                "WARNING",
                f"No future found for capability_response",
                f"request_id={message.request_id}, from={message.from_agent}, to={message.to_agent}, available_futures={list(self._response_futures.keys())[:5]}",
            )

        # Only deliver to agent if it's not a direct response (to_agent indicates forwarding)
        # Most responses are handled via future fulfillment above
        if message.to_agent and message.to_agent in self.agents:
            asyncio.create_task(self.agents[message.to_agent].receive_message(message))

    async def _handle_error_message(self, message: Message) -> None:
        """Handle error message - fulfill future and deliver to agent."""
        fut_data = self._response_futures.get(message.request_id)
        if fut_data:
            fut, _ = fut_data
            if not fut.done():
                fut.set_result({"error": message.content.get("error")})
                # Clean up future
                del self._response_futures[message.request_id]

        if message.to_agent and message.to_agent in self.agents:
            asyncio.create_task(self.agents[message.to_agent].receive_message(message))

    async def _handle_capability_request_broadcast(self, message: Message) -> None:
        """Handle capability request with batched broadcast to providers."""
        capability = message.content.get("capability")
        providers = self.capability_registry.get(capability, [])
        allowed = message.content.get("allowed_agents")
        if allowed:
            providers = [p for p in providers if p in allowed]

        if (
            self.method_recorder
            and self.method_recorder.recording
            and capability != "intent_matching"
        ):
            provider = providers[0] if providers else None
            if provider:
                params = message.content.get("data", {})
                mappings = message.content.get("mappings")
                self.method_recorder.record_step(provider, capability, params, mappings)

        # Batch broadcast: create all tasks at once instead of one-by-one
        if providers:
            for provider in providers:
                if provider in self.agents:
                    # Reuse message content instead of full clone
                    cloned = Message(
                        from_agent=message.from_agent,
                        to_agent=provider,
                        message_type=message.message_type,
                        content=message.content,  # Reference, not deep copy
                        request_id=message.request_id,
                        reply_to=message.reply_to,
                    )
                    # Create individual tasks for parallel execution
                    asyncio.create_task(self.agents[provider].receive_message(cloned))
                    self._metrics["broadcast_messages"] += 1

    async def request_capability(
        self,
        from_agent: str,
        capability: str,
        data: Any,
        request_id: Optional[str] = None,
        allowed_agents: Optional[set[str]] = None,
    ) -> List[str]:
        """
        Broadcast a capability_request and return the list of providers.
        Also registers a Future for the response.
        """
        if request_id is None:
            request_id = str(asyncio.get_event_loop().time())

        self.logger.log(
            "DEBUG",
            f"Capability request initiated",
            f"From: {from_agent}, Capability: {capability}, Request ID: {request_id}",
        )

        providers = self.capability_registry.get(capability, [])
        if allowed_agents is not None:
            providers = [p for p in providers if p in allowed_agents]

        # Create and store the Future with TTL (only if not already exists)
        if request_id not in self._response_futures:
            loop = asyncio.get_event_loop()
            fut = loop.create_future()
            self._response_futures[request_id] = (fut, time.time())
            self.logger.log(
                "DEBUG",
                f"Created future for capability request",
                f"request_id={request_id}, capability={capability}, from={from_agent}, total_futures={len(self._response_futures)}",
            )
        else:
            self.logger.log(
                "DEBUG",
                f"Reusing existing future for capability request",
                f"request_id={request_id}, capability={capability}, from={from_agent}",
            )

        # Broadcast the capability_request
        msg = Message(
            from_agent=from_agent,
            to_agent=None,
            message_type="capability_request",
            content={
                "capability": capability,
                "data": data,
                "allowed_agents": list(allowed_agents) if allowed_agents else None,
            },
            request_id=request_id,
        )
        await self.send_message(msg)

        # Get providers and log them
        self.logger.log(
            "INFO",
            f"Capability request broadcast",
            f"Capability: {capability}, Potential providers: {len(providers)}",
        )

        if not providers:
            self.logger.log(
                "WARNING",
                f"No providers found for capability",
                f"Capability: {capability}",
            )

        # Return who *could* handle it
        return providers

    async def wait_for_response(self, request_id: str, timeout: float = None) -> Any:
        """
        Await and return the result for a previously requested capability_response.
        """
        self.logger.log(
            "INFO",
            f"wait_for_response called",
            f"request_id={request_id}, timeout={timeout}, available_futures={list(self._response_futures.keys())[:5]}",
        )
        fut_data = self._response_futures.get(request_id)
        if not fut_data:
            self.logger.log(
                "ERROR",
                f"No future found in wait_for_response",
                f"request_id={request_id}, available={list(self._response_futures.keys())[:10]}",
            )
            raise KeyError(f"No pending request with id {request_id}")
        fut, _ = fut_data
        self.logger.log(
            "INFO",
            f"[WAIT_START] Waiting for future to complete",
            f"request_id={request_id}, future_done={fut.done()}, future_cancelled={fut.cancelled()}, future_id={id(fut)}",
        )
        try:
            # Poll loop: check if done, if not yield and check again
            # This ensures we catch the future even if it's fulfilled in a different task
            start_time = time.time()
            poll_count = 0
            last_log_time = start_time

            fut_id = id(fut)
            # Try to await the future directly with a short timeout, then check
            # This is more efficient than polling
            check_interval = 0.1  # Check every 100ms
            while not fut.done():
                poll_count += 1
                elapsed = time.time() - start_time

                # Check timeout first
                if timeout and elapsed > timeout:
                    self.logger.log(
                        "ERROR",
                        f"[POLL_TIMEOUT] Timeout in polling loop",
                        f"request_id={request_id}, elapsed={elapsed:.2f}s, timeout={timeout}, poll_count={poll_count}, fut_done={fut.done()}, fut_cancelled={fut.cancelled()}, fut_id={fut_id}",
                    )
                    raise asyncio.TimeoutError(f"Timeout after {timeout}s")

                # Log every 0.5 seconds to track progress
                if time.time() - last_log_time >= 0.5:
                    # Re-check future from dict to ensure we have the right one
                    fut_data_check = self._response_futures.get(request_id)
                    if fut_data_check:
                        fut_check, _ = fut_data_check
                        fut_id_check = id(fut_check)
                        if fut_id_check != fut_id:
                            self.logger.log(
                                "WARNING",
                                f"[POLL_LOOP] Future object changed!",
                                f"request_id={request_id}, old_fut_id={fut_id}, new_fut_id={fut_id_check}",
                            )
                            fut = fut_check
                            fut_id = fut_id_check

                    # Double-check future state right before logging
                    done_state = fut.done()
                    cancelled_state = fut.cancelled()
                    current_fut_id = id(fut)
                    self.logger.log(
                        "INFO",
                        f"[POLL_LOOP] Still waiting for future",
                        f"request_id={request_id}, poll_count={poll_count}, elapsed={elapsed:.2f}s, fut_done={done_state}, fut_cancelled={cancelled_state}, fut_id={current_fut_id}",
                    )
                    last_log_time = time.time()

                # Try to await with a short timeout - this will raise TimeoutError if not done
                # But we catch it and continue polling
                try:
                    await asyncio.wait_for(asyncio.shield(fut), timeout=check_interval)
                    # If we get here, the future is done!
                    break
                except asyncio.TimeoutError:
                    # Future not done yet, continue polling
                    continue

            # Future is done - get result
            elapsed = time.time() - start_time
            self.logger.log(
                "INFO",
                f"[POLL_DONE] Future detected as done (polling)",
                f"request_id={request_id}, elapsed={elapsed:.2f}s, poll_count={poll_count}, fut_done={fut.done()}, fut_cancelled={fut.cancelled()}",
            )

            self.logger.log(
                "INFO",
                f"[GET_RESULT] Calling fut.result()",
                f"request_id={request_id}, fut_done={fut.done()}",
            )
            result = fut.result()
            self.logger.log(
                "INFO",
                f"[RESULT_GOT] Got result from future",
                f"request_id={request_id}, result_type={type(result).__name__}, result_keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}",
            )

            # Clean up
            self.logger.log(
                "INFO",
                f"[CLEANUP] Cleaning up future from _response_futures",
                f"request_id={request_id}",
            )
            self._response_futures.pop(request_id, None)

            self.logger.log(
                "INFO",
                f"[RETURN] Returning result from wait_for_response",
                f"request_id={request_id}, result_type={type(result).__name__}",
            )
            return result
        except asyncio.TimeoutError as e:
            self.logger.log(
                "ERROR",
                f"Timeout waiting for response",
                f"request_id={request_id}, timeout={timeout}, future_done={fut.done()}",
            )
            self._response_futures.pop(request_id, None)
            raise
        except Exception as e:
            self.logger.log(
                "ERROR",
                f"Exception waiting for response",
                f"request_id={request_id}, error={type(e).__name__}: {str(e)}",
            )
            self._response_futures.pop(request_id, None)
            raise

    async def _cleanup_futures_loop(self) -> None:
        """Periodic cleanup of expired futures."""
        while self._running:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired_futures()
            except Exception as exc:
                self.logger.log("ERROR", "Future cleanup error", str(exc))

    async def _cleanup_expired_futures(self) -> None:
        """Remove expired futures that have exceeded TTL."""
        current_time = time.time()
        expired = []

        for request_id, (fut, created_time) in list(self._response_futures.items()):
            age = current_time - created_time
            if age > self._future_ttl:
                expired.append(request_id)
                if not fut.done():
                    fut.cancel()

        for request_id in expired:
            del self._response_futures[request_id]
            self._metrics["future_cleanups"] += 1

        if expired:
            self.logger.log(
                "DEBUG",
                f"Cleaned up {len(expired)} expired futures",
                (
                    f"Request IDs: {expired[:5]}..."
                    if len(expired) > 5
                    else f"Request IDs: {expired}"
                ),
            )

    def get_metrics(self) -> Dict[str, Any]:
        """Get network performance metrics."""
        queue_depths = {
            "high": self._high_priority_queue.qsize(),
            "normal": self._normal_priority_queue.qsize(),
            "low": self._low_priority_queue.qsize(),
        }
        total_queue_size = sum(queue_depths.values())

        return {
            **self._metrics,
            "active_futures": len(self._response_futures),
            "queue_depths": queue_depths,
            "total_queue_size": total_queue_size,
            "backpressure_threshold": self._backpressure_threshold,
            "circuit_breaker_active": self._circuit_breaker_active,
            "response_aggregator": self.response_aggregator.get_stats(),
        }
