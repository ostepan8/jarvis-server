#!/usr/bin/env python3
"""Submit an improvement task to the Jarvis self-improvement system."""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import post


def main():
    parser = argparse.ArgumentParser(description="Submit an improvement task")
    parser.add_argument("--title", required=True, help="Task title")
    parser.add_argument("--description", required=True, help="Task description")
    parser.add_argument("--priority", default="medium",
                       choices=["urgent", "high", "medium", "low"],
                       help="Task priority (default: medium)")
    parser.add_argument("--files", type=str, default="",
                       help="Comma-separated relevant file paths")
    args = parser.parse_args()

    body = {
        "title": args.title,
        "description": args.description,
        "priority": args.priority,
        "relevant_files": [f.strip() for f in args.files.split(",") if f.strip()],
    }

    result = post("/tasks", data=body)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
