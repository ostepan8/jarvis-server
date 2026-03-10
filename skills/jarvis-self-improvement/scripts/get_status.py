#!/usr/bin/env python3
"""Check the current status of the Jarvis self-improvement system."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import get


def main():
    result = get("/status")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
