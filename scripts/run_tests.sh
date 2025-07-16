#!/usr/bin/env bash
# Set up virtual environment and run the test suite
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
