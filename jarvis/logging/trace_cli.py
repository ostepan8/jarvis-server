"""CLI for inspecting Jarvis traces.

Usage::

    python -m jarvis.logging.trace_cli get <trace_id>
    python -m jarvis.logging.trace_cli tree <trace_id>
    python -m jarvis.logging.trace_cli list [--since 1h] [--status ERROR] [--limit 20]
    python -m jarvis.logging.trace_cli spans [--agent X] [--capability Y]
    python -m jarvis.logging.trace_cli last [--tree]

All output is JSON (or ASCII tree) to stdout — pipe-friendly for
coding agents and downstream tooling.
"""

import argparse
import json
import sys

from .trace_query import TraceQuery
from .trace_store import TraceStore


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="trace_cli", description="Jarvis trace inspector"
    )
    sub = parser.add_subparsers(dest="command")

    # -- get ---------------------------------------------------------------
    p_get = sub.add_parser("get", help="Dump trace as JSON")
    p_get.add_argument("trace_id")

    # -- tree --------------------------------------------------------------
    p_tree = sub.add_parser("tree", help="Dump trace as ASCII tree")
    p_tree.add_argument("trace_id")

    # -- list --------------------------------------------------------------
    p_list = sub.add_parser("list", help="List recent traces")
    p_list.add_argument("--since", help="Time window (e.g. 1h, 30m, 2d)")
    p_list.add_argument("--until", help="End time")
    p_list.add_argument("--status", help="Filter by status (OK, ERROR)")
    p_list.add_argument("--agent", help="Filter by agent name")
    p_list.add_argument("--capability", help="Filter by capability")
    p_list.add_argument("--limit", type=int, default=20)

    # -- spans -------------------------------------------------------------
    p_spans = sub.add_parser("spans", help="Search spans")
    p_spans.add_argument("--trace-id", help="Filter by trace ID")
    p_spans.add_argument("--agent", help="Filter by agent name")
    p_spans.add_argument("--capability", help="Filter by capability")
    p_spans.add_argument("--kind", help="Filter by span kind")
    p_spans.add_argument("--status", help="Filter by status")
    p_spans.add_argument("--limit", type=int, default=50)

    # -- last --------------------------------------------------------------
    p_last = sub.add_parser("last", help="Show most recent trace")
    p_last.add_argument("--tree", action="store_true", help="ASCII tree output")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    store = TraceStore()
    query = TraceQuery(store)

    try:
        if args.command == "get":
            result = query.get_trace(args.trace_id)
            if not result:
                print(f"Trace {args.trace_id} not found.", file=sys.stderr)
                sys.exit(1)
            print(json.dumps(result, indent=2))

        elif args.command == "tree":
            print(query.render_tree(args.trace_id))

        elif args.command == "list":
            traces = query.list_traces(
                since=args.since,
                until=args.until,
                status=args.status,
                agent=args.agent,
                capability=args.capability,
                limit=args.limit,
            )
            print(json.dumps(traces, indent=2))

        elif args.command == "spans":
            spans = query.search_spans(
                trace_id=getattr(args, "trace_id", None),
                agent_name=args.agent,
                capability=args.capability,
                kind=args.kind,
                status=args.status,
                limit=args.limit,
            )
            print(json.dumps(spans, indent=2))

        elif args.command == "last":
            traces = query.list_traces(limit=1)
            if not traces:
                print("No traces found.", file=sys.stderr)
                sys.exit(1)
            trace_id = traces[0]["trace_id"]
            if args.tree:
                print(query.render_tree(trace_id))
            else:
                result = query.get_trace(trace_id)
                print(json.dumps(result, indent=2))

    finally:
        store.close()


if __name__ == "__main__":
    main()
