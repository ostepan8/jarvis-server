#!/usr/bin/env python3
"""Run tests via the Jarvis self-improvement API and poll for results."""

import argparse
import json
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import get, post


def main():
    parser = argparse.ArgumentParser(description="Run tests via Jarvis API")
    parser.add_argument("test_files", nargs="*", default=None,
                       help="Specific test files to run (default: full suite)")
    parser.add_argument("--working-directory", type=str, default=None,
                       help="Working directory for test execution")
    parser.add_argument("--timeout", type=int, default=120,
                       help="Test timeout in seconds (default: 120)")
    parser.add_argument("--poll-interval", type=float, default=2.0,
                       help="Seconds between poll attempts (default: 2.0)")
    parser.add_argument("--no-poll", action="store_true",
                       help="Return run_id immediately without polling")
    args = parser.parse_args()

    body = {"timeout": args.timeout}
    if args.test_files:
        body["test_files"] = args.test_files
    if args.working_directory:
        body["working_directory"] = args.working_directory

    result = post("/tests/run", data=body)
    run_id = result.get("run_id")

    if not run_id:
        print(json.dumps(result, indent=2))
        return

    if args.no_poll:
        print(json.dumps({"run_id": run_id, "status": "submitted"}, indent=2))
        return

    print(f"Test run started: {run_id}", file=sys.stderr)

    while True:
        time.sleep(args.poll_interval)
        status = get(f"/tests/{run_id}")

        current = status.get("status", "unknown")
        if current in ("completed", "failed"):
            print(json.dumps(status, indent=2))
            sys.exit(0 if status.get("success") else 1)

        print(f"  Status: {current}...", file=sys.stderr)


if __name__ == "__main__":
    main()
