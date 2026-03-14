"""Tests for the observability tracing system.

Covers TraceStore CRUD, Tracer context propagation, nested spans,
the @traced decorator, concurrent trace isolation, data truncation,
feature flag no-ops, and TraceQuery tree rendering.
"""

import asyncio
import json

import pytest

from jarvis.logging.trace_store import TraceStore
from jarvis.logging.trace_query import TraceQuery
from jarvis.logging.tracer import (
    ActiveSpan,
    NullSpan,
    Span,
    SpanKind,
    Trace,
    Tracer,
    _truncate_data,
    get_tracer,
    traced,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def trace_db(tmp_path):
    store = TraceStore(db_path=str(tmp_path / "test_traces.db"))
    yield store
    store.close()


@pytest.fixture
def tracer(trace_db):
    return Tracer(store=trace_db, enabled=True, trace_llm_content=False)


@pytest.fixture
def query(trace_db):
    return TraceQuery(trace_db)


# ------------------------------------------------------------------
# TraceStore
# ------------------------------------------------------------------


class TestTraceStore:
    def test_save_and_get_trace(self, trace_db):
        trace = Trace(
            trace_id="test-123",
            user_input="hello",
            user_id=1,
            source="test",
            start_time="2024-01-01T00:00:00",
        )
        trace_db.save_trace(trace)

        result = trace_db.get_trace("test-123")
        assert result is not None
        assert result["trace_id"] == "test-123"
        assert result["user_input"] == "hello"
        assert result["user_id"] == 1

    def test_get_nonexistent_trace(self, trace_db):
        assert trace_db.get_trace("nope") is None

    def test_complete_trace(self, trace_db):
        trace = Trace(trace_id="t-1", start_time="2024-01-01T00:00:00")
        trace_db.save_trace(trace)
        trace_db.complete_trace("t-1", "2024-01-01T00:00:01", 1000.0, "OK")

        result = trace_db.get_trace("t-1")
        assert result["duration_ms"] == 1000.0
        assert result["status"] == "OK"
        assert result["end_time"] == "2024-01-01T00:00:01"

    def test_save_and_get_spans(self, trace_db):
        trace = Trace(trace_id="t-2", start_time="2024-01-01T00:00:00")
        trace_db.save_trace(trace)

        span = Span(
            span_id="s-1",
            trace_id="t-2",
            name="test.op",
            kind="internal",
            start_time="2024-01-01T00:00:00",
        )
        trace_db.save_span(span)

        spans = trace_db.get_spans("t-2")
        assert len(spans) == 1
        assert spans[0]["name"] == "test.op"
        assert spans[0]["kind"] == "internal"

    def test_get_spans_empty(self, trace_db):
        assert trace_db.get_spans("nonexistent") == []

    def test_list_traces_with_limit(self, trace_db):
        for i in range(5):
            trace = Trace(
                trace_id=f"t-{i}", start_time=f"2024-01-0{i + 1}T00:00:00"
            )
            trace_db.save_trace(trace)

        results = trace_db.list_traces(limit=3)
        assert len(results) == 3

    def test_list_traces_filter_by_status(self, trace_db):
        trace_db.save_trace(
            Trace(trace_id="ok-1", start_time="2024-01-01T00:00:00", status="OK")
        )
        trace_db.save_trace(
            Trace(trace_id="err-1", start_time="2024-01-01T00:00:01", status="ERROR")
        )

        ok_traces = trace_db.list_traces(status="OK")
        assert all(t["status"] == "OK" for t in ok_traces)

        err_traces = trace_db.list_traces(status="ERROR")
        assert len(err_traces) == 1
        assert err_traces[0]["trace_id"] == "err-1"

    def test_search_spans_by_agent(self, trace_db):
        trace_db.save_trace(
            Trace(trace_id="t-search", start_time="2024-01-01T00:00:00")
        )
        for name, agent in [("op.a", "AgentA"), ("op.b", "AgentB")]:
            trace_db.save_span(
                Span(
                    span_id=f"s-{name}",
                    trace_id="t-search",
                    name=name,
                    kind="agent",
                    agent_name=agent,
                    start_time="2024-01-01T00:00:00",
                )
            )

        results = trace_db.search_spans(agent_name="AgentA")
        assert len(results) == 1
        assert results[0]["agent_name"] == "AgentA"

    def test_search_spans_by_capability(self, trace_db):
        trace_db.save_trace(
            Trace(trace_id="t-cap", start_time="2024-01-01T00:00:00")
        )
        trace_db.save_span(
            Span(
                span_id="s-cap-1",
                trace_id="t-cap",
                name="agent.toggle",
                kind="agent",
                capability="toggle_lights",
                start_time="2024-01-01T00:00:00",
            )
        )

        results = trace_db.search_spans(capability="toggle_lights")
        assert len(results) == 1

    def test_list_traces_filter_by_agent(self, trace_db):
        trace_db.save_trace(
            Trace(trace_id="t-agent-filter", start_time="2024-01-01T00:00:00")
        )
        trace_db.save_span(
            Span(
                span_id="s-af",
                trace_id="t-agent-filter",
                name="op",
                kind="agent",
                agent_name="WeatherAgent",
                start_time="2024-01-01T00:00:00",
            )
        )

        results = trace_db.list_traces(agent="WeatherAgent")
        assert len(results) == 1
        assert results[0]["trace_id"] == "t-agent-filter"

        results = trace_db.list_traces(agent="NonExistentAgent")
        assert len(results) == 0


# ------------------------------------------------------------------
# Tracer
# ------------------------------------------------------------------


class TestTracer:
    @pytest.mark.asyncio
    async def test_start_and_end_trace(self, tracer, trace_db):
        trace_id = tracer.start_trace(trace_id="abc-123", user_input="test")
        assert trace_id == "abc-123"
        assert tracer.current_trace_id() == "abc-123"

        tracer.end_trace()
        assert tracer.current_trace_id() is None

        result = trace_db.get_trace("abc-123")
        assert result is not None
        assert result["status"] == "OK"
        assert result["duration_ms"] is not None

    @pytest.mark.asyncio
    async def test_auto_generate_trace_id(self, tracer):
        trace_id = tracer.start_trace(user_input="auto-id")
        assert trace_id is not None
        assert len(trace_id) > 0
        tracer.end_trace()

    @pytest.mark.asyncio
    async def test_span_records_timing(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-span")

        async with tracer.span("test.operation", kind=SpanKind.INTERNAL) as s:
            await asyncio.sleep(0.01)

        tracer.end_trace()

        spans = trace_db.get_spans("t-span")
        assert len(spans) == 1
        assert spans[0]["name"] == "test.operation"
        assert spans[0]["kind"] == "internal"
        assert spans[0]["duration_ms"] >= 5
        assert spans[0]["status"] == "OK"
        assert spans[0]["start_time"] is not None
        assert spans[0]["end_time"] is not None

    @pytest.mark.asyncio
    async def test_nested_spans_parent_child(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-nested")

        async with tracer.span("parent") as parent:
            async with tracer.span("child") as child:
                pass

        tracer.end_trace()

        spans = trace_db.get_spans("t-nested")
        assert len(spans) == 2

        parent_span = next(s for s in spans if s["name"] == "parent")
        child_span = next(s for s in spans if s["name"] == "child")

        assert child_span["parent_span_id"] == parent_span["span_id"]
        assert parent_span["parent_span_id"] is None

    @pytest.mark.asyncio
    async def test_deeply_nested_spans(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-deep")

        async with tracer.span("level-1") as s1:
            async with tracer.span("level-2") as s2:
                async with tracer.span("level-3") as s3:
                    pass

        tracer.end_trace()

        spans = trace_db.get_spans("t-deep")
        assert len(spans) == 3

        by_name = {s["name"]: s for s in spans}
        assert by_name["level-2"]["parent_span_id"] == by_name["level-1"]["span_id"]
        assert by_name["level-3"]["parent_span_id"] == by_name["level-2"]["span_id"]

    @pytest.mark.asyncio
    async def test_sibling_spans(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-siblings")

        async with tracer.span("parent"):
            async with tracer.span("child-a"):
                pass
            async with tracer.span("child-b"):
                pass

        tracer.end_trace()

        spans = trace_db.get_spans("t-siblings")
        assert len(spans) == 3

        parent = next(s for s in spans if s["name"] == "parent")
        children = [s for s in spans if s["name"].startswith("child")]
        assert all(c["parent_span_id"] == parent["span_id"] for c in children)

    @pytest.mark.asyncio
    async def test_span_captures_exception(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-error")

        with pytest.raises(ValueError):
            async with tracer.span("failing.op"):
                raise ValueError("something broke")

        tracer.end_trace()

        spans = trace_db.get_spans("t-error")
        assert len(spans) == 1
        assert spans[0]["status"] == "ERROR"
        assert "something broke" in spans[0]["error"]

    @pytest.mark.asyncio
    async def test_span_record_output(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-output")

        async with tracer.span("compute") as s:
            s.record_output({"result": 42})

        tracer.end_trace()

        spans = trace_db.get_spans("t-output")
        assert '"result": 42' in spans[0]["output_data"]

    @pytest.mark.asyncio
    async def test_span_record_error_manual(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-manual-err")

        async with tracer.span("soft-fail") as s:
            s.record_error("upstream timeout")

        tracer.end_trace()

        spans = trace_db.get_spans("t-manual-err")
        assert spans[0]["status"] == "ERROR"
        assert spans[0]["error"] == "upstream timeout"

    @pytest.mark.asyncio
    async def test_span_with_agent_and_capability(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-meta")

        async with tracer.span(
            "agent.toggle_lights",
            kind=SpanKind.AGENT,
            agent_name="LightingAgent",
            capability="toggle_lights",
        ):
            pass

        tracer.end_trace()

        spans = trace_db.get_spans("t-meta")
        assert spans[0]["agent_name"] == "LightingAgent"
        assert spans[0]["capability"] == "toggle_lights"
        assert spans[0]["kind"] == "agent"

    @pytest.mark.asyncio
    async def test_span_with_input_data(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-input")

        async with tracer.span("op", input_data={"query": "weather in NYC"}):
            pass

        tracer.end_trace()

        spans = trace_db.get_spans("t-input")
        assert "weather in NYC" in spans[0]["input_data"]

    @pytest.mark.asyncio
    async def test_span_with_attributes(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-attrs")

        async with tracer.span(
            "llm.chat",
            kind=SpanKind.LLM,
            attributes={"model": "gpt-4o-mini", "tokens": 150},
        ):
            pass

        tracer.end_trace()

        spans = trace_db.get_spans("t-attrs")
        attrs = json.loads(spans[0]["attributes"])
        assert attrs["model"] == "gpt-4o-mini"
        assert attrs["tokens"] == 150

    @pytest.mark.asyncio
    async def test_end_trace_with_error(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-trace-err")
        tracer.end_trace(status="ERROR", error="fatal crash")

        result = trace_db.get_trace("t-trace-err")
        assert result["status"] == "ERROR"

    @pytest.mark.asyncio
    async def test_span_outside_trace_returns_null(self, tracer):
        span = tracer.span("orphan")
        assert isinstance(span, NullSpan)

    @pytest.mark.asyncio
    async def test_null_span_is_harmless(self):
        span = NullSpan()
        async with span as s:
            s.record_output({"x": 1})
            s.record_error("ignored")


# ------------------------------------------------------------------
# Disabled tracer
# ------------------------------------------------------------------


class TestDisabledTracer:
    @pytest.mark.asyncio
    async def test_disabled_returns_null_spans(self, trace_db):
        t = Tracer(store=trace_db, enabled=False)

        trace_id = t.start_trace(user_input="test")
        assert trace_id is not None

        span = t.span("noop")
        assert isinstance(span, NullSpan)

        async with span:
            pass

        t.end_trace()

        assert trace_db.get_trace(trace_id) is None

    @pytest.mark.asyncio
    async def test_disabled_current_trace_id_is_none(self, trace_db):
        t = Tracer(store=trace_db, enabled=False)
        t.start_trace(trace_id="disabled-1")
        assert t.current_trace_id() is None
        assert t.current_span_id() is None


# ------------------------------------------------------------------
# Context propagation
# ------------------------------------------------------------------


class TestContextPropagation:
    @pytest.mark.asyncio
    async def test_set_context_restores_trace(self, tracer, trace_db):
        tracer.start_trace(trace_id="t-ctx")

        async with tracer.span("original") as s:
            original_span_id = s._span.span_id

        tracer.end_trace()

        tracer.set_context("t-ctx", original_span_id)
        assert tracer.current_trace_id() == "t-ctx"
        assert tracer.current_span_id() == original_span_id

    @pytest.mark.asyncio
    async def test_set_context_without_parent(self, tracer):
        tracer.set_context("t-no-parent")
        assert tracer.current_trace_id() == "t-no-parent"
        assert tracer.current_span_id() is None

    @pytest.mark.asyncio
    async def test_concurrent_traces_no_contamination(self, trace_db):
        """asyncio.gather with separate traces must not cross-contaminate."""
        t = Tracer(store=trace_db, enabled=True)

        async def run_trace(tid: str, span_name: str):
            t.start_trace(trace_id=tid, user_input=f"input-{tid}")
            async with t.span(span_name):
                await asyncio.sleep(0.01)
                assert t.current_trace_id() == tid
            t.end_trace()

        await asyncio.gather(
            run_trace("concurrent-1", "span-a"),
            run_trace("concurrent-2", "span-b"),
        )

        spans_1 = trace_db.get_spans("concurrent-1")
        spans_2 = trace_db.get_spans("concurrent-2")

        assert len(spans_1) == 1
        assert spans_1[0]["name"] == "span-a"
        assert len(spans_2) == 1
        assert spans_2[0]["name"] == "span-b"

    @pytest.mark.asyncio
    async def test_message_based_context(self, tracer, trace_db):
        """Simulate context propagation via Message fields."""
        tracer.start_trace(trace_id="t-msg")

        async with tracer.span("sender.span") as sender:
            captured_trace_id = tracer.current_trace_id()
            captured_span_id = tracer.current_span_id()

        tracer.end_trace()

        # Simulate receiving side restoring context
        tracer.set_context(captured_trace_id, captured_span_id)

        async with tracer.span("receiver.span") as receiver:
            pass

        spans = trace_db.get_spans("t-msg")
        assert len(spans) == 2

        receiver_span = next(s for s in spans if s["name"] == "receiver.span")
        assert receiver_span["parent_span_id"] == captured_span_id


# ------------------------------------------------------------------
# Data truncation
# ------------------------------------------------------------------


class TestDataTruncation:
    def test_large_data_is_truncated(self):
        big = {"key": "x" * 5000}
        result = _truncate_data(big)
        assert len(result) <= 4096
        assert "truncated" in result

    def test_small_data_passes_through(self):
        small = {"key": "value"}
        result = _truncate_data(small)
        assert "truncated" not in result
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_none_returns_none(self):
        assert _truncate_data(None) is None

    def test_non_json_serializable(self):
        result = _truncate_data(object())
        assert result is not None  # falls back to str()


# ------------------------------------------------------------------
# @traced decorator
# ------------------------------------------------------------------


class TestTracedDecorator:
    @pytest.mark.asyncio
    async def test_decorated_function_produces_span(self, tracer, trace_db):
        import jarvis.logging.tracer as tracer_mod

        old = tracer_mod._tracer_instance
        tracer_mod._tracer_instance = tracer

        try:

            @traced("test.decorated", kind=SpanKind.INTERNAL)
            async def my_function(x, y):
                return x + y

            tracer.start_trace(trace_id="t-decorated")
            result = await my_function(1, 2)
            tracer.end_trace()

            assert result == 3

            spans = trace_db.get_spans("t-decorated")
            assert len(spans) == 1
            assert spans[0]["name"] == "test.decorated"
        finally:
            tracer_mod._tracer_instance = old

    @pytest.mark.asyncio
    async def test_decorator_noop_without_tracer(self):
        import jarvis.logging.tracer as tracer_mod

        old = tracer_mod._tracer_instance
        tracer_mod._tracer_instance = None

        try:

            @traced("test.noop")
            async def my_func():
                return 42

            result = await my_func()
            assert result == 42
        finally:
            tracer_mod._tracer_instance = old

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_name(self):
        @traced("test.name")
        async def important_function():
            pass

        assert important_function.__name__ == "important_function"

    @pytest.mark.asyncio
    async def test_llm_kind_hides_content(self, tracer, trace_db):
        import jarvis.logging.tracer as tracer_mod

        old = tracer_mod._tracer_instance
        tracer_mod._tracer_instance = tracer

        try:

            @traced("llm.chat", kind=SpanKind.LLM)
            async def chat(messages, model="gpt-4o"):
                return "response"

            tracer.start_trace(trace_id="t-llm-hide")
            await chat([{"role": "user", "content": "secret prompt"}])
            tracer.end_trace()

            spans = trace_db.get_spans("t-llm-hide")
            input_data = json.loads(spans[0]["input_data"])
            assert "secret prompt" not in json.dumps(input_data)
            assert "arg_count" in input_data
        finally:
            tracer_mod._tracer_instance = old


# ------------------------------------------------------------------
# TraceQuery
# ------------------------------------------------------------------


class TestTraceQuery:
    @pytest.mark.asyncio
    async def test_get_trace_with_nested_spans(self, tracer, trace_db, query):
        tracer.start_trace(trace_id="t-query", user_input="hello")
        async with tracer.span("parent"):
            async with tracer.span("child"):
                pass
        tracer.end_trace()

        result = query.get_trace("t-query")
        assert result is not None
        assert len(result["spans"]) == 1  # one root
        assert result["spans"][0]["name"] == "parent"
        assert len(result["spans"][0]["children"]) == 1
        assert result["spans"][0]["children"][0]["name"] == "child"

    @pytest.mark.asyncio
    async def test_render_tree_structure(self, tracer, trace_db, query):
        tracer.start_trace(trace_id="t-tree", user_input="test tree")
        async with tracer.span("orchestrator.process"):
            async with tracer.span("nlu.classify"):
                pass
            async with tracer.span(
                "agent.execute", agent_name="LightingAgent"
            ):
                pass
        tracer.end_trace()

        tree = query.render_tree("t-tree")
        assert "TRACE t-tree" in tree
        assert "orchestrator.process" in tree
        assert "nlu.classify" in tree
        assert "agent.execute" in tree
        assert "LightingAgent" in tree

    @pytest.mark.asyncio
    async def test_render_tree_shows_error(self, tracer, trace_db, query):
        tracer.start_trace(trace_id="t-tree-err", user_input="error test")
        with pytest.raises(RuntimeError):
            async with tracer.span("failing"):
                raise RuntimeError("boom")
        tracer.end_trace()

        tree = query.render_tree("t-tree-err")
        assert "ERROR" in tree
        assert "boom" in tree

    def test_render_tree_not_found(self, query):
        result = query.render_tree("nonexistent")
        assert "not found" in result

    def test_get_trace_not_found(self, query):
        assert query.get_trace("nonexistent") is None

    def test_resolve_time_hours(self, query):
        result = query._resolve_time("1h")
        assert "T" in result

    def test_resolve_time_minutes(self, query):
        result = query._resolve_time("30m")
        assert "T" in result

    def test_resolve_time_days(self, query):
        result = query._resolve_time("2d")
        assert "T" in result

    def test_resolve_time_iso_passthrough(self, query):
        iso = "2024-01-01T00:00:00"
        assert query._resolve_time(iso) == iso

    @pytest.mark.asyncio
    async def test_list_traces(self, tracer, trace_db, query):
        for i in range(3):
            tracer.start_trace(trace_id=f"t-list-{i}", user_input=f"input {i}")
            tracer.end_trace()

        results = query.list_traces(limit=2)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_spans(self, tracer, trace_db, query):
        tracer.start_trace(trace_id="t-search-q")
        async with tracer.span("op", kind=SpanKind.AGENT, agent_name="TestAgent"):
            pass
        tracer.end_trace()

        results = query.search_spans(agent_name="TestAgent")
        assert len(results) == 1


# ------------------------------------------------------------------
# SpanKind
# ------------------------------------------------------------------


class TestSpanKind:
    def test_values(self):
        assert SpanKind.ORCHESTRATOR == "orchestrator"
        assert SpanKind.AGENT == "agent"
        assert SpanKind.LLM == "llm"
        assert SpanKind.SERVICE == "service"
        assert SpanKind.NETWORK == "network"
        assert SpanKind.INTERNAL == "internal"

    def test_string_comparison(self):
        assert SpanKind.AGENT == "agent"
        assert str(SpanKind.AGENT) == "SpanKind.AGENT"
