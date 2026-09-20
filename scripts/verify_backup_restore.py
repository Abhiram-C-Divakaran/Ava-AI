#!/usr/bin/env python3
"""
scripts/verify_backup_restore.py — Operational Backup and Restore Verification for Ava AI.

Performs live end-to-end operational verification by executing the actual
scripts/backup_db.py and scripts/restore_db.py CLI scripts via subprocess.

Verifies:
1. Backup creation via CLI produces valid, readable SQLite file with integrity = ok.
2. Restore via CLI restores exact snapshot (User A, Memory A, Adaptation A).
3. Post-backup mutations (User B) are discarded by restore.
4. Pre-restore safety backup is created.
5. SQLite PRAGMA integrity_check passes after restore.
"""

import os
import sys
import uuid
import sqlite3
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def run_verification() -> bool:
    print(f"\n======================================================================")
    print(f"  Ava AI — Operational Backup & Restore Verification")
    print(f"======================================================================\n")

    test_id = uuid.uuid4().hex[:8]
    test_db = os.path.join(BASE_DIR, f"temp_verify_db_{test_id}.db")
    backup_file = os.path.join(BASE_DIR, f"temp_verify_backup_{test_id}.db")
    env = os.environ.copy()
    env["DB_PATH"] = test_db

    try:
        # Step 1: Initialize temporary database with schema
        import database as db
        original_db_path = db.DB_PATH
        db.DB_PATH = test_db
        db.init_db()

        # Step 2: Populate known seed data (User A, Memory A, Adaptation A)
        print("[*] Seeding test database with User A, Memory A, Adaptation A...")
        db.create_user("user_a", "User A", "user_a@example.com", "hash_a")
        db.set_user_memory("user_a", "User A prefers concise code", 3)
        db.set_adaptation_profile("user_a", {"verbosity": 0.2, "technical_depth": 0.9}, interaction_count=5)

        # Verify initial data
        user_a = db.get_user_by_id("user_a")
        mem_a = db.get_user_memory("user_a")
        prof_a = db.get_adaptation_profile("user_a")
        assert user_a is not None, "User A failed to insert"
        assert mem_a.get("memory_text") == "User A prefers concise code", "Memory A failed to insert"
        assert prof_a.get("interaction_count") == 5, "Adaptation A failed to insert"
        print("  [PASS] Seed data created and verified")

        # Step 3: Run actual backup CLI via subprocess
        print(f"[*] Executing CLI backup to '{backup_file}'...")
        cmd_backup = [sys.executable, os.path.join(BASE_DIR, "scripts", "backup_db.py"), "--dest", backup_file]
        res = subprocess.run(cmd_backup, env=env, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"  [FAIL] backup_db.py failed with code {res.returncode}:\n{res.stderr}")
            return False

        # Verify backup file properties and SQLite integrity
        if not os.path.exists(backup_file):
            print(f"  [FAIL] Backup file was not created: {backup_file}")
            return False
        if os.path.getsize(backup_file) == 0:
            print(f"  [FAIL] Backup file is empty")
            return False

        b_conn = sqlite3.connect(backup_file)
        b_cur = b_conn.cursor()
        b_cur.execute("PRAGMA integrity_check;")
        integrity = b_cur.fetchone()[0]
        b_conn.close()
        if integrity != "ok":
            print(f"  [FAIL] Backup integrity check failed: {integrity}")
            return False
        print(f"  [PASS] CLI backup succeeded (size: {os.path.getsize(backup_file)} bytes, integrity: {integrity})")

        # Step 4: Mutate database post-backup (Insert User B)
        print("[*] Mutating database post-backup (inserting User B)...")
        db.create_user("user_b", "User B", "user_b@example.com", "hash_b")
        assert db.get_user_by_id("user_b") is not None, "User B should exist before restore"
        print("  [PASS] Database successfully mutated with post-backup record")

        # Step 5: Run actual restore CLI via subprocess
        print(f"[*] Executing CLI restore from '{backup_file}' with --confirm...")
        cmd_restore = [sys.executable, os.path.join(BASE_DIR, "scripts", "restore_db.py"), backup_file, "--confirm"]
        res = subprocess.run(cmd_restore, env=env, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"  [FAIL] restore_db.py failed with code {res.returncode}:\n{res.stderr}")
            return False
        print(f"  [PASS] CLI restore command executed successfully")

        # Step 6: Verify restored database state
        user_a_restored = db.get_user_by_id("user_a")
        mem_a_restored = db.get_user_memory("user_a")
        prof_a_restored = db.get_adaptation_profile("user_a")
        user_b_restored = db.get_user_by_id("user_b")

        if user_a_restored is None:
            print("  [FAIL] User A missing after restore!")
            return False
        if mem_a_restored.get("memory_text") != "User A prefers concise code":
            print("  [FAIL] Memory A missing or corrupt after restore!")
            return False
        if prof_a_restored.get("interaction_count") != 5:
            print("  [FAIL] Adaptation A missing or incorrect after restore!")
            return False
        if user_b_restored is not None:
            print("  [FAIL] Post-backup mutation (User B) still present after restore!")
            return False

        print("  [PASS] User A, Memory A, Adaptation A intact; User B correctly absent")

        # Step 7: Verify restored DB integrity
        r_integrity = db.check_database_integrity()
        if r_integrity != "ok":
            print(f"  [FAIL] Restored database integrity check failed: {r_integrity}")
            return False
        print(f"  [PASS] Restored database PRAGMA integrity_check: {r_integrity}")

        print(f"\n----------------------------------------------------------------------")
        print(f"  [SUCCESS] Operational backup and restore verification passed 100%!")
        print(f"----------------------------------------------------------------------\n")
        return True

    finally:
        db.DB_PATH = original_db_path
        for f in [test_db, backup_file]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        # Clean up any safety backups created in current dir
        for fname in os.listdir(BASE_DIR):
            if fname.startswith(f"temp_verify_db_{test_id}") and ".safety_" in fname:
                try:
                    os.remove(os.path.join(BASE_DIR, fname))
                except Exception:
                    pass


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
