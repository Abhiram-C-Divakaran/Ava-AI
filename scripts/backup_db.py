"""
scripts/backup_db.py — Safe SQLite online database backup utility for Ava AI.
"""

import os
import sys
import argparse
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db

def main():
    parser = argparse.ArgumentParser(description="Backup Ava AI SQLite database online.")
    parser.add_argument(
        "--dest",
        type=str,
        default=None,
        help="Destination path for backup file. Defaults to 'backup_<timestamp>.db'."
    )
    args = parser.parse_args()

    if not args.dest:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        args.dest = os.path.join(os.path.dirname(db.DB_PATH) or ".", f"backup_ava_{ts}.db")

    print(f"[*] Starting live online backup from '{db.DB_PATH}' to '{args.dest}'...")
    dest_path = db.backup_database(args.dest)
    print(f"[+] Backup written to: {dest_path}")

    # Verify backup integrity
    import sqlite3
    chk = sqlite3.connect(dest_path)
    try:
        res = chk.execute("PRAGMA integrity_check;").fetchone()
        integrity = res[0] if res else "unknown"
        if integrity == "ok":
            print(f"[+] Backup integrity check PASSED ({integrity}). File size: {os.path.getsize(dest_path)} bytes.")
        else:
            print(f"[!] Warning: backup integrity check reported: {integrity}", file=sys.stderr)
            sys.exit(1)
    finally:
        chk.close()

if __name__ == "__main__":
    main()
