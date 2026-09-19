"""
scripts/restore_db.py — Safe SQLite database restore procedure for Ava AI.
Enforces explicit confirmation, backup validation, safety snapshotting, and migration replay.
"""

import os
import sys
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db

def main():
    parser = argparse.ArgumentParser(description="Restore Ava AI SQLite database from backup.")
    parser.add_argument("backup_file", type=str, help="Path to backup SQLite file to restore.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Explicit confirmation required to restore database over existing data."
    )
    parser.add_argument(
        "--no-safety-backup",
        action="store_true",
        help="Skip creating a safety backup of the current database before restoring."
    )
    args = parser.parse_args()

    if not args.confirm:
        print("[-] Error: Database restore requires explicit confirmation. Pass --confirm to proceed.", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.backup_file):
        print(f"[-] Error: Backup file not found: {args.backup_file}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Restoring '{db.DB_PATH}' from '{args.backup_file}'...")
    create_safety = not args.no_safety_backup
    try:
        result = db.restore_database(args.backup_file, create_safety_backup=create_safety)
        print(f"[+] Restore successful!")
        if result.get("safety_backup"):
            print(f"[+] Safety backup of previous DB saved at: {result['safety_backup']}")
        print(f"[+] Database integrity verified: {result['integrity']}")
    except Exception as e:
        print(f"[-] Restore failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
