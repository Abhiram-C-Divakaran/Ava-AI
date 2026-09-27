#!/usr/bin/env python3
"""
cleanup_events.py — Retention policy cleanup script for Ava AI product analytics.

Policy:
- Raw product events are retained for 30–90 days (default: 60 days).
- Aggregated metrics and user feedback entries are preserved until resolved.
- Destructive operations require an explicit positive retention window.
"""
import sys
import os
import argparse
from datetime import datetime, timezone, timedelta

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db

def main():
    parser = argparse.ArgumentParser(description="Purge product analytics events older than specified retention days.")
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="Retention window in days (must be >= 1; recommended 30–90, default 60)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count eligible records without deleting them"
    )
    args = parser.parse_args()

    if args.days < 1:
        print("ERROR: Retention days must be at least 1.", file=sys.stderr)
        sys.exit(1)

    db.init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    print(f"[{datetime.now(timezone.utc).isoformat()}] Retention cleanup target: events older than {args.days} days (< {cutoff})")

    if args.dry_run:
        with db.get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM product_events WHERE created_at < ?", (cutoff,)).fetchone()
            count = row["c"] if row else 0
        print(f"[DRY-RUN] Eligible events to delete: {count}")
    else:
        deleted = db.delete_product_events_older_than(args.days)
        print(f"[CLEANUP COMPLETE] Successfully deleted {deleted} product event(s) older than {args.days} days.")

if __name__ == "__main__":
    main()
