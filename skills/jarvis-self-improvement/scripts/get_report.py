#!/usr/bin/env python3
"""Fetch improvement reports from the Jarvis self-improvement API."""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import get


def main():
    parser = argparse.ArgumentParser(description="Get improvement reports")
    parser.add_argument("--all", action="store_true", dest="list_all",
                       help="List all reports instead of just the latest")
    parser.add_argument("--limit", type=int, default=10,
                       help="Max reports to return when using --all (default: 10)")
    args = parser.parse_args()

    if args.list_all:
        result = get("/reports", params={"limit": str(args.limit)})
    else:
        result = get("/reports/latest")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
