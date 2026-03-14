"""Query and rendering layer for traces.

Builds nested JSON trees from flat span rows, renders ASCII trees for
terminal inspection, and converts relative time strings (``1h``,
``30m``, ``2d``) into ISO timestamps for filtering.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from .trace_store import TraceStore


class TraceQuery:
    def __init__(self, store: TraceStore):
        self._store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Return a full trace with spans nested under their parents."""
        trace = self._store.get_trace(trace_id)
        if not trace:
            return None
        spans = self._store.get_spans(trace_id)
        trace["spans"] = self._nest_spans(spans)
        return trace

    def list_traces(
        self,
        since: str = None,
        until: str = None,
        status: str = None,
        agent: str = None,
        capability: str = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        since_iso = self._resolve_time(since) if since else None
        until_iso = self._resolve_time(until) if until else None
        return self._store.list_traces(
            since=since_iso,
            until=until_iso,
            status=status,
            agent=agent,
            capability=capability,
            limit=limit,
        )

    def search_spans(
        self,
        trace_id: str = None,
        agent_name: str = None,
        capability: str = None,
        kind: str = None,
        status: str = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self._store.search_spans(
            trace_id=trace_id,
            agent_name=agent_name,
            capability=capability,
            kind=kind,
            status=status,
            limit=limit,
        )

    def render_tree(self, trace_id: str) -> str:
        """Render a trace as an ASCII tree suitable for terminal output."""
        trace = self._store.get_trace(trace_id)
        if not trace:
            return f"Trace {trace_id} not found."

        spans = self._store.get_spans(trace_id)

        duration = trace.get("duration_ms")
        duration_str = f"{duration:.0f}ms" if duration is not None else "..."
        status = trace.get("status", "OK")
        user_input = trace.get("user_input") or ""
        if len(user_input) > 60:
            user_input = user_input[:57] + "..."

        lines = [
            f'[{duration_str}] TRACE {trace_id[:8]}: "{user_input}"  {status}'
        ]

        roots = [s for s in spans if not s.get("parent_span_id")]
        for i, root in enumerate(roots):
            self._render_span(root, spans, lines, "", i == len(roots) - 1)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _render_span(
        self,
        span: Dict,
        all_spans: List[Dict],
        lines: List[str],
        prefix: str,
        is_last: bool,
    ) -> None:
        connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "

        duration = span.get("duration_ms")
        duration_str = f"{duration:.0f}ms" if duration is not None else "..."
        status = span.get("status", "OK")
        name = span.get("name", "?")

        details: list[str] = []
        if span.get("agent_name"):
            details.append(f"agent={span['agent_name']}")
        if span.get("capability"):
            details.append(f"cap={span['capability']}")
        attrs = span.get("attributes")
        if attrs:
            try:
                attr_dict = json.loads(attrs) if isinstance(attrs, str) else attrs
                if "model" in attr_dict:
                    details.append(f"model={attr_dict['model']}")
            except Exception:
                pass

        detail_str = "  " + " ".join(details) if details else ""
        error_str = ""
        if status == "ERROR" and span.get("error"):
            error_str = f"  err={span['error'][:50]}"

        lines.append(
            f"{prefix}{connector}[{duration_str}] {name} {status}{detail_str}{error_str}"
        )

        children = [
            s
            for s in all_spans
            if s.get("parent_span_id") == span.get("span_id")
        ]
        child_prefix = prefix + ("    " if is_last else "\u2502   ")
        for j, child in enumerate(children):
            self._render_span(
                child, all_spans, lines, child_prefix, j == len(children) - 1
            )

    def _nest_spans(self, spans: List[Dict]) -> List[Dict]:
        by_id = {s["span_id"]: {**s, "children": []} for s in spans}
        roots: list[Dict] = []

        for s in by_id.values():
            parent_id = s.get("parent_span_id")
            if parent_id and parent_id in by_id:
                by_id[parent_id]["children"].append(s)
            else:
                roots.append(s)

        return roots

    def _resolve_time(self, time_str: str) -> str:
        """Convert ``'1h'``, ``'30m'``, ``'2d'`` to ISO-format timestamps."""
        if not time_str:
            return time_str

        if "T" in time_str or "-" in time_str:
            return time_str

        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        unit = time_str[-1].lower()
        if unit in multipliers:
            try:
                amount = int(time_str[:-1])
                delta = timedelta(seconds=amount * multipliers[unit])
                return (datetime.now(UTC) - delta).isoformat()
            except ValueError:
                pass

        return time_str
