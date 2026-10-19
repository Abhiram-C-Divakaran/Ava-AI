#!/usr/bin/env python3
"""
scripts/deployment/start_ava_server.py — Ava AI Beta Production Server Launcher
Loads production configuration from C:\\AvaBeta\\ava.env and starts Uvicorn with 1 worker.
"""

import os
import sys
from dotenv import load_dotenv

# Ensure workspace root is in sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

ENV_PATH = r"C:\AvaBeta\ava.env"
if os.path.exists(ENV_PATH):
    print(f"[*] Loading production environment from {ENV_PATH}...")
    load_dotenv(ENV_PATH, override=True)
else:
    print(f"[!] Warning: {ENV_PATH} not found, falling back to local .env")
    load_dotenv(override=True)

# Ensure Windows host paths for persistent data
if os.getenv("DB_PATH") == "/app/data/neurosupport.db":
    os.environ["DB_PATH"] = r"C:\AvaBeta\data\neurosupport.db"
if os.getenv("UPLOAD_DIR") == "/app/data/uploads":
    os.environ["UPLOAD_DIR"] = r"C:\AvaBeta\data\uploads"
if os.getenv("REVIEW_IMAGE_DIR") == "/app/data/review_images":
    os.environ["REVIEW_IMAGE_DIR"] = r"C:\AvaBeta\data\review_images"

# Ensure origin includes Tailscale Funnel
tailscale_origin = "https://aizen.tailbcb715.ts.net"
current_origins = os.getenv("ALLOWED_ORIGINS", "")
if tailscale_origin not in current_origins:
    os.environ["ALLOWED_ORIGINS"] = f"{tailscale_origin},http://127.0.0.1:8000"

# Ensure Google OAuth redirect URI is exact
if not os.getenv("GOOGLE_REDIRECT_URI"):
    os.environ["GOOGLE_REDIRECT_URI"] = "https://aizen.tailbcb715.ts.net/api/auth/google/callback"

import uvicorn

if __name__ == "__main__":
    print(f"[*] Starting Ava AI Beta Server on 127.0.0.1:8000 (1 worker)...")
    print(f"[*] DB_PATH: {os.environ.get('DB_PATH')}")
    print(f"[*] ALLOWED_ORIGINS: {os.environ.get('ALLOWED_ORIGINS')}")
    print(f"[*] GOOGLE_REDIRECT_URI: {os.environ.get('GOOGLE_REDIRECT_URI')}")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, workers=1, log_level="info")
