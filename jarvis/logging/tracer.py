"""Hierarchical request tracing for Jarvis.

Every request produces a **trace** (tree of **spans**) stored in SQLite.
Context propagation uses ``contextvars`` so async tasks inherit the
current trace automatically.  When context is lost (e.g. across a
message queue boundary), ``set_context`` restores it from the
``trace_id`` / ``parent_span_id`` fields embedded in ``Message``.

Feature flags
-------------
``JARVIS_TRACING``           — master switch (default ``"true"``).
``JARVIS_TRACE_LLM_CONTENT`` — capture full LLM prompts/responses
                               (default ``"false"``; privacy-sensitive).
"""

import contextvars
import functools
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional, Union

from .trace_store import TraceStore

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

TRACING_ENABLED = os.getenv("JARVIS_TRACING", "true").lower() != "false"
TRACE_LLM_CONTENT = os.getenv("JARVIS_TRACE_LLM_CONTENT", "false").lower() == "true"

MAX_DATA_SIZE = 4096  # 4 KB cap on serialised input/output


# ---------------------------------------------------------------------------
# Enums & dataclasses
# ---------------------------------------------------------------------------


class SpanKind(str, Enum):
    ORCHESTRATOR = "orchestrator"
    AGENT = "agent"
    LLM = "llm"
    SERVICE = "service"
    NETWORK = "network"
    INTERNAL = "internal"


@dataclass
class Span:
    span_id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    name: str = ""
    kind: str = SpanKind.INTERNAL
    agent_name: Optional[str] = None
    capability: Optional[str] = None
    start_time: str = ""
    end_time: Optional[str] = None
    duration_ms: Optional[float] = None
    status: str = "OK"
    input_data: Optional[str] = None
    output_data: Optional[str] = None
    error: Optional[str] = None
    attributes: Optional[str] = None


@dataclass
class Trace:
    trace_id: str
    user_input: Optional[str] = None
    user_id: Optional[int] = None
    source: Optional[str] = None
    start_time: str = ""
    end_time: Optional[str] = None
    duration_ms: Optional[float] = None
    status: str = "OK"
    metadata: Optional[str] = None


# ---------------------------------------------------------------------------
# Context variables
# ---------------------------------------------------------------------------

_current_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_trace_id", default=None
)
_span_stack: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar(
    "span_stack", default=None
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate_data(data: Any, max_size: int = MAX_DATA_SIZE) -> Optional[str]:
    if data is None:
        return None
    try:
        s = json.dumps(data, default=str)
    except (TypeError, ValueError):
        s = str(data)
    if len(s) > max_size:
        return s[: max_size - 20] + "... [truncated]"
    return s


# ---------------------------------------------------------------------------
# Span wrappers
# ---------------------------------------------------------------------------


class NullSpan:
    """No-op span returned when tracing is disabled or no trace is active."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def record_output(self, data: Any) -> None:
        pass

    def record_error(self, error: Any) -> None:
        pass


class ActiveSpan:
    """Live span that records timing, data, and errors."""

    def __init__(
        self,
        tracer: "Tracer",
        span_id: str,
        trace_id: str,
        parent_span_id: Optional[str],
        name: str,
        kind: SpanKind,
        agent_name: Optional[str],
        capability: Optional[str],
        input_data: Any,
        attributes: Any,
    ):
        self._tracer = tracer
        self._span = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind.value if isinstance(kind, SpanKind) else kind,
            agent_name=agent_name,
            capability=capability,
            start_time=datetime.now(UTC).isoformat(),
            input_data=_truncate_data(input_data) if input_data is not None else None,
            attributes=_truncate_data(attributes) if attributes is not None else None,
        )
        self._start_perf: float = 0.0
        self._stack_token: Optional[contextvars.Token] = None

    async def __aenter__(self) -> "ActiveSpan":
        self._start_perf = time.perf_counter()
        stack = _span_stack.get() or []
        self._stack_token = _span_stack.set(stack + [self._span.span_id])
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.perf_counter() - self._start_perf
        self._span.end_time = datetime.now(UTC).isoformat()
        self._span.duration_ms = round(elapsed * 1000, 2)

        if exc_type is not None:
            self._span.status = "ERROR"
            self._span.error = f"{exc_type.__name__}: {exc_val}"

        if self._stack_token is not None:
            _span_stack.reset(self._stack_token)

        self._tracer._save_span(self._span)
        return False  # never suppress exceptions

    def record_output(self, data: Any) -> None:
        self._span.output_data = _truncate_data(data)

    def record_error(self, error: Any) -> None:
        self._span.status = "ERROR"
        self._span.error = str(error)


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------


class Tracer:
    """Singleton-ish tracer that owns the store and context management."""

    def __init__(
        self,
        store: TraceStore,
        enabled: bool = True,
        trace_llm_content: bool = False,
    ):
        self._store = store
        self._enabled = enabled
        self._trace_llm_content = trace_llm_content
        # trace_id -> (perf_start, context_token)
        self._active_traces: dict[str, tuple[float, contextvars.Token]] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def trace_llm_content(self) -> bool:
        return self._trace_llm_content

    # -- Trace lifecycle ---------------------------------------------------

    def start_trace(
        self,
        trace_id: Optional[str] = None,
        user_input: str = None,
        user_id: int = None,
        source: str = None,
        metadata: dict = None,
    ) -> str:
        trace_id = trace_id or str(uuid.uuid4())
        if not self._enabled:
            return trace_id

        now = datetime.now(UTC).isoformat()
        trace = Trace(
            trace_id=trace_id,
            user_input=user_input,
            user_id=user_id,
            source=source,
            start_time=now,
            metadata=_truncate_data(metadata) if metadata else None,
        )
        self._store.save_trace(trace)

        token = _current_trace_id.set(trace_id)
        _span_stack.set([])
        self._active_traces[trace_id] = (time.perf_counter(), token)
        return trace_id

    def end_trace(self, status: str = "OK", error: str = None) -> None:
        if not self._enabled:
            return

        trace_id = _current_trace_id.get()
        if not trace_id or trace_id not in self._active_traces:
            return

        start_perf, token = self._active_traces.pop(trace_id)
        elapsed = time.perf_counter() - start_perf
        now = datetime.now(UTC).isoformat()

        final_status = "ERROR" if error else status
        self._store.complete_trace(
            trace_id=trace_id,
            end_time=now,
            duration_ms=round(elapsed * 1000, 2),
            status=final_status,
        )

        _current_trace_id.reset(token)
        _span_stack.set(None)

    # -- Span creation -----------------------------------------------------

    def span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        agent_name: str = None,
        capability: str = None,
        input_data: Any = None,
        attributes: dict = None,
    ) -> Union[ActiveSpan, NullSpan]:
        if not self._enabled:
            return NullSpan()

        trace_id = _current_trace_id.get()
        if not trace_id:
            return NullSpan()

        stack = _span_stack.get()
        parent_span_id = stack[-1] if stack else None

        return ActiveSpan(
            tracer=self,
            span_id=str(uuid.uuid4()),
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            agent_name=agent_name,
            capability=capability,
            input_data=input_data,
            attributes=attributes,
        )

    # -- Context inspection ------------------------------------------------

    def current_trace_id(self) -> Optional[str]:
        return _current_trace_id.get() if self._enabled else None

    def current_span_id(self) -> Optional[str]:
        if not self._enabled:
            return None
        stack = _span_stack.get()
        return stack[-1] if stack else None

    def set_context(self, trace_id: str, parent_span_id: str = None) -> None:
        """Restore trace context, e.g. from fields on a ``Message``."""
        if not self._enabled:
            return
        _current_trace_id.set(trace_id)
        _span_stack.set([parent_span_id] if parent_span_id else [])

    # -- Internal ----------------------------------------------------------

    def _save_span(self, span: Span) -> None:
        try:
            self._store.save_span(span)
        except Exception:
            pass  # tracing must never break request processing


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tracer_instance: Optional[Tracer] = None


def init_tracer(
    store: TraceStore,
    enabled: bool = True,
    trace_llm_content: bool = False,
) -> Tracer:
    global _tracer_instance
    _tracer_instance = Tracer(
        store=store, enabled=enabled, trace_llm_content=trace_llm_content
    )
    return _tracer_instance


def get_tracer() -> Optional[Tracer]:
    return _tracer_instance


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def traced(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    agent_name: str = None,
    capability: str = None,
):
    """Decorator that wraps an async function in a span.

    Captures a summary of arguments as ``input_data`` and the return
    type as ``output_data``.  Full LLM content is gated behind
    ``JARVIS_TRACE_LLM_CONTENT``.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()
            if not tracer or not tracer.enabled:
                return await func(*args, **kwargs)

            input_data = None
            if kind == SpanKind.LLM and not tracer.trace_llm_content:
                input_data = {
                    "arg_count": len(args),
                    "kwarg_keys": list(kwargs.keys()),
                }
            else:
                try:
                    input_data = {
                        "args_count": len(args),
                        "kwargs": {k: str(v)[:200] for k, v in kwargs.items()},
                    }
                except Exception:
                    pass

            async with tracer.span(
                name,
                kind=kind,
                agent_name=agent_name,
                capability=capability,
                input_data=input_data,
            ) as s:
                result = await func(*args, **kwargs)
                if isinstance(s, ActiveSpan):
                    try:
                        if result is not None:
                            s.record_output({"type": type(result).__name__})
                    except Exception:
                        pass
                return result

        return wrapper

    return decorator
