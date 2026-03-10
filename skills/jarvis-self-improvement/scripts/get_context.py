#!/usr/bin/env python3
"""Read a project file via the Jarvis self-improvement API."""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import get


def main():
    parser = argparse.ArgumentParser(description="Read a project file via API")
    parser.add_argument("file_path", help="Path to the file (relative to project root)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                       help="Output as JSON instead of raw content")
    args = parser.parse_args()

    result = get(f"/context/{args.file_path}")

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        print(result.get("content", ""))


if __name__ == "__main__":
    main()
