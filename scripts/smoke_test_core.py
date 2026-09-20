#!/usr/bin/env python3
"""
scripts/smoke_test_core.py — Offline Core Smoke Test for Ava AI.

Direct operational test of core system services:
- Health and Readiness
- User Registration & Authentication
- Session Access & User Memory
- Behavioral Adaptation Profile & Preferences
- Cross-User Authorization Enforcement
- User Logout & Post-Logout Protection

Does not require live external Groq LLM API connectivity.
"""

import sys
import argparse
from smoke_test import run_smoke_test


def main():
    parser = argparse.ArgumentParser(description="Ava AI Core Offline Smoke Test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of Ava server")
    args = parser.parse_args()

    success = run_smoke_test(args.base_url, offline=True)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
