#!/usr/bin/env python3
"""Run or fetch discovery analysis from the Jarvis self-improvement API."""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import get, post


def main():
    parser = argparse.ArgumentParser(description="Discover issues in the Jarvis codebase")
    parser.add_argument("--types", type=str, default=None,
                       help="Comma-separated discovery types: logs,tests,todos,code_quality")
    parser.add_argument("--lookback-hours", type=int, default=24,
                       help="How far back to look for issues (default: 24)")
    parser.add_argument("--cached", action="store_true",
                       help="Return cached discoveries instead of running new analysis")
    parser.add_argument("--type-filter", type=str, default=None,
                       help="Filter cached results by type")
    args = parser.parse_args()

    if args.cached:
        params = {}
        if args.type_filter:
            params["type"] = args.type_filter
        result = get("/discoveries", params=params)
    else:
        body = {"lookback_hours": args.lookback_hours}
        if args.types:
            body["types"] = [t.strip() for t in args.types.split(",")]
        result = post("/discover", data=body)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
