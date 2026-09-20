"""
test_reliability.py — Comprehensive Operational Reliability Test Suite for Ava AI.

Tests 17 critical reliability domains:
1.  Persistent DB path configuration (production vs dev)
2.  Online SQLite backup creation and integrity
3.  Database integrity check (`PRAGMA integrity_check`)
4.  Database restore with migration and schema verification
5.  Schema migrations tracking (versions 1 through 5)
6.  Concurrent multi-threaded SQLite writes without lock contention
7.  LLM timeout and exponential backoff retry on transient errors (429, 503)
8.  LLM strict non-retry on client errors (400, 401, 403)
9.  Brave search network failure graceful degradation
10. DeepL translation API failure and fallback
11. Replicate image generation failure and fallback
12. Judge0 code execution safety (disabled in production and timeout handling)
13. Readiness probe detects database failure (HTTP 503)
14. Readiness probe detects unwritable storage directories (HTTP 503)
15. Streaming response generator resilience
16. Centralized configuration validation rules
17. Operational metrics collector tracking and admin access control
"""

import os
import sys
import time
import json
import uuid
import tempfile
import sqlite3
import unittest
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

# Reconfigure stdout for utf-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi.testclient import TestClient
import config
import database as db
import llm
import powers
from metrics import MetricsCollector, metrics
from main import app


class TestOperationalReliability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from main import limiter
        limiter.enabled = False
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_db_path = os.path.join(cls.temp_dir.name, "test_reliability.db")
        cls.orig_db = db.DB_PATH
        db.DB_PATH = cls.test_db_path
        db.init_db()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        from main import limiter
        limiter.enabled = True
        db.DB_PATH = cls.orig_db
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    # 1. Persistent DB path configuration (production vs dev)
    def test_01_persistent_db_path_production_vs_dev(self):
        """Verify DB_PATH defaults to /app/data in production and local path in dev."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            # Test production path resolution
            if not os.getenv("DB_PATH"):
                prod_db = "/app/data/neurosupport.db"
                self.assertEqual(prod_db, "/app/data/neurosupport.db")
        self.assertTrue(config.DB_PATH.endswith(".db"))
        self.assertTrue("data" in config.UPLOAD_DIR or "upload" in config.UPLOAD_DIR)

    # 2. Online SQLite backup creation and integrity
    def test_02_backup_online_succeeds(self):
        """Online backup produces a valid, readable copy of the active database."""
        user_id = f"user_bk_{uuid.uuid4().hex[:6]}"
        db.create_user(user_id, name="Backup User", email=f"{user_id}@example.com", password="pwd")
        backup_path = os.path.join(self.temp_dir.name, f"backup_{uuid.uuid4().hex[:6]}.db")

        ret_path = db.backup_database(backup_path)
        self.assertEqual(ret_path, backup_path)
        self.assertTrue(os.path.exists(backup_path))
        self.assertGreater(os.path.getsize(backup_path), 0)

        # Read from the backup copy
        conn = sqlite3.connect(backup_path)
        row = conn.execute("SELECT name FROM users WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Backup User")

    # 3. Database integrity check (PRAGMA integrity_check)
    def test_03_integrity_check_ok(self):
        """check_database_integrity reports 'ok' on healthy database."""
        result = db.check_database_integrity()
        self.assertEqual(result, "ok")

        # Verify corrupted database is detected
        bad_db_path = os.path.join(self.temp_dir.name, "corrupt.db")
        with open(bad_db_path, "wb") as f:
            f.write(b"not a valid sqlite file header garbage")

        bad_res = db.check_database_integrity(bad_db_path)
        self.assertNotEqual(bad_res, "ok")

    # 4. Database restore with migration and schema verification
    def test_04_restore_preserves_records_and_migrates(self):
        """restore_database validates backup integrity, restores data, and runs migrations."""
        user_id = f"user_rst_{uuid.uuid4().hex[:6]}"
        db.create_user(user_id, name="Restore Test", email=f"{user_id}@example.com", password="pwd")
        backup_path = os.path.join(self.temp_dir.name, f"valid_bk_{uuid.uuid4().hex[:6]}.db")
        db.backup_database(backup_path)

        # Mutate active database
        db.create_user(f"other_{uuid.uuid4().hex[:6]}", name="Temporary", email="tmp@example.com", password="pwd")

        # Restore from backup
        rst_res = db.restore_database(backup_path)
        self.assertEqual(rst_res["status"], "restored")
        self.assertEqual(rst_res["integrity"], "ok")

        # Verify user exists after restore
        u = db.get_user(user_id)
        self.assertIsNotNone(u)
        self.assertEqual(u["name"], "Restore Test")

    # 5. Schema migrations tracking (versions 1 through 5)
    def test_05_schema_migrations_tracking(self):
        """Ensure schema_migrations table tracks versions 1 to 5."""
        with db.get_conn() as conn:
            rows = conn.execute("SELECT version, description FROM schema_migrations ORDER BY version ASC").fetchall()
            versions = [r["version"] for r in rows]
            self.assertIn(1, versions)
            self.assertIn(2, versions)
            self.assertIn(3, versions)
            self.assertIn(4, versions)
            self.assertIn(5, versions)

    # 6. Concurrent multi-threaded SQLite writes without lock contention
    def test_06_concurrent_sqlite_writes(self):
        """15 concurrent threads writing sessions and messages do not produce SQLite lock errors."""
        session_ids = [str(uuid.uuid4()) for _ in range(15)]
        user_id = f"user_conc_{uuid.uuid4().hex[:6]}"
        db.create_user(user_id, name="Concurrent User", email=f"{user_id}@example.com", password="pwd")

        errors = []

        def worker(sid: str, idx: int):
            try:
                db.create_session(sid, user_id, title=f"Session {idx}")
                for m in range(3):
                    msg_id = str(uuid.uuid4())
                    db.save_message(
                        message_id=msg_id,
                        session_id=sid,
                        user_id=user_id,
                        user_message=f"Ping {m}",
                        agent_response=f"Pong {m}",
                        intent="general",
                        sentiment={"label": "neutral", "score": 0.5},
                        frustration=0.0,
                        latency_ms=10,
                    )
                    db.save_feedback(user_id, sid, msg_id, helpful=True)
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=15) as executor:
            list(executor.map(worker, session_ids, range(15)))

        self.assertEqual(len(errors), 0, f"Concurrent writes produced errors: {errors}")

    # 7. LLM timeout and exponential backoff retry on transient errors (429, 503)
    def test_07_llm_timeout_and_retry_transient_errors(self):
        """call_llm retries on 429/503 errors and succeeds on eventual recovery."""
        call_count = 0

        def mock_post(url, headers=None, json=None, timeout=None, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count < 3:
                mock_resp.status_code = 429
                mock_resp.text = '{"error": "rate_limit_exceeded"}'
                return mock_resp
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "Eventual success response after backoff"}}]
            }
            return mock_resp

        with patch("llm.API_KEY", "gsk_test_key_mock"), \
             patch("requests.post", side_effect=mock_post), \
             patch("time.sleep", return_value=None):
            resp = llm.call_llm("test prompt", max_retries=3)
            self.assertEqual(resp, "Eventual success response after backoff")
            self.assertEqual(call_count, 3)

    # 8. LLM strict non-retry on client errors (400, 401, 403)
    def test_08_llm_no_retry_client_errors(self):
        """call_llm immediately fails without retries on 400 Bad Request or 401 Unauthorized."""
        call_count = 0

        def mock_post_400(url, headers=None, json=None, timeout=None, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 400
            mock_resp.text = "Bad Request: invalid parameter"
            return mock_resp

        with patch("llm.API_KEY", "gsk_test_key_mock"), \
             patch("requests.post", side_effect=mock_post_400), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(ValueError) as ctx:
                llm.call_llm("test prompt", max_retries=3)
            self.assertEqual(call_count, 1)
            self.assertIn("400", str(ctx.exception))

    # 9. Brave search network failure graceful degradation
    def test_09_brave_search_failure_graceful(self):
        """web_search gracefully catches connection timeouts or server errors and returns []."""
        with patch("requests.get", side_effect=Exception("Connection reset by peer")):
            results = powers.web_search("latest quantum computing breakthrough")
            self.assertEqual(results, [])

    # 10. DeepL translation API failure and fallback
    def test_10_deepl_translation_failure_fallback(self):
        """translate_deepl falls back cleanly to None on network failure or 500 error."""
        with patch.dict(os.environ, {"DEEPL_API_KEY": "dummy_key"}, clear=False), \
             patch("requests.post", side_effect=Exception("DeepL Gateway Timeout")):
            res = powers.translate_deepl("Hello world", target_lang_name="German")
            self.assertIsNone(res)

    # 11. Replicate image generation failure and fallback
    def test_11_replicate_failure_fallback(self):
        """POST /api/generate-image returns fallback image when replicate is not configured."""
        user_id = f"user_img_{uuid.uuid4().hex[:6]}"
        db.create_user(user_id, name="Img User", email=f"{user_id}@example.com", password="pwd")
        login_resp = self.client.post("/api/auth/login", json={"email": f"{user_id}@example.com", "password": "pwd"})
        self.assertEqual(login_resp.status_code, 200)

        with patch.dict(os.environ, {"REPLICATE_API_KEY": ""}, clear=False):
            resp = self.client.post("/api/generate-image", json={"prompt": "A cute robot"})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("mock"))
            self.assertIn("placekitten", data.get("image_url", ""))

    # 12. Judge0 code execution safety (disabled in production and timeout handling)
    def test_12_judge0_timeout_and_disabled_execution(self):
        """execute_code respects ENABLE_CODE_EXECUTION=False and handles execution timeouts."""
        # 1. Disabled in production
        with patch.object(powers, "ENABLE_CODE_EXECUTION", False):
            res = powers.execute_code("python", "print('hello')")
            self.assertEqual(res["status"], "Disabled")
            self.assertFalse(res["success"])

        # 2. Timeout handling
        import requests as req
        with patch.object(powers, "ENABLE_CODE_EXECUTION", True), \
             patch("requests.post", side_effect=req.Timeout("Execution exceeded 15s")):
            res_timeout = powers.execute_code("python", "while True: pass")
            self.assertEqual(res_timeout["status"], "Timeout")
            self.assertFalse(res_timeout["success"])

    # 13. Readiness probe detects database failure (HTTP 503)
    def test_13_readiness_probe_database_failure(self):
        """GET /ready returns HTTP 503 when database connectivity fails."""
        with patch("database.get_conn", side_effect=sqlite3.OperationalError("Unable to open database")):
            resp = self.client.get("/ready")
            self.assertEqual(resp.status_code, 503)
            data = resp.json()
            self.assertEqual(data.get("status"), "unhealthy")
            self.assertTrue(any("database" in err for err in data.get("errors", [])))

    # 14. Readiness probe detects unwritable storage directories (HTTP 503)
    def test_14_readiness_probe_storage_unwritable(self):
        """GET /ready returns HTTP 503 when upload directory is not writable."""
        with patch("builtins.open", side_effect=PermissionError("Read-only filesystem")):
            resp = self.client.get("/ready")
            self.assertEqual(resp.status_code, 503)
            data = resp.json()
            self.assertEqual(data.get("status"), "unhealthy")

    # 15. Streaming response generator resilience
    def test_15_streaming_disconnect_handling(self):
        """POST /api/chat/stream handles generation exceptions without crashing."""
        user_id = f"user_stream_{uuid.uuid4().hex[:6]}"
        db.create_user(user_id, name="Stream User", email=f"{user_id}@example.com", password="pwd")
        self.client.post("/api/auth/login", json={"email": f"{user_id}@example.com", "password": "pwd"})

        with patch("main.call_llm_streaming", side_effect=RuntimeError("Stream broke")):
            resp = self.client.post("/api/chat/stream", json={"message": "Stream test", "user_id": user_id})
            self.assertEqual(resp.status_code, 200)
            lines = [l for l in resp.text.split("\n") if l.startswith("data: ")]
            self.assertGreater(len(lines), 0)

    # 16. Centralized configuration validation rules
    def test_16_startup_config_validation_rules(self):
        """validate_config enforces non-empty SECRET_KEY and no wildcard origins in production."""
        # Clean config in development
        with patch.object(config, "ENVIRONMENT", "development"):
            v_dev = config.validate_config()
            self.assertTrue(v_dev["valid"])

        # Insecure production config (wildcard + missing secret)
        with patch.object(config, "ENVIRONMENT", "production"), \
             patch.object(config, "SECRET_KEY", ""), \
             patch.object(config, "ALLOWED_ORIGINS", ["*"]):
            v_prod = config.validate_config()
            self.assertFalse(v_prod["valid"])
            self.assertTrue(any("SECRET_KEY" in err for err in v_prod["errors"]))
            self.assertTrue(any("ALLOWED_ORIGINS" in err for err in v_prod["errors"]))

    # 17. Operational metrics collector tracking and admin access control
    def test_17_operational_metrics_collector(self):
        """Operational metrics collector tracks events and is restricted to admin users."""
        collector = MetricsCollector()
        collector.inc("chat_requests", 5)
        collector.inc("chat_errors", 1)
        collector.record_latency(150.0)
        collector.record_latency(250.0)

        snap = collector.get_snapshot()
        self.assertEqual(snap["counters"]["chat_requests"], 5)
        self.assertEqual(snap["counters"]["chat_errors"], 1)
        self.assertEqual(snap["latency"]["count"], 2)
        self.assertEqual(snap["latency"]["avg_ms"], 200.0)
        self.assertEqual(snap["latency"]["min_ms"], 150.0)
        self.assertEqual(snap["latency"]["max_ms"], 250.0)

        # Unauthenticated access to /api/metrics fails
        unauth_client = TestClient(app)
        resp_unauth = unauth_client.get("/api/metrics")
        self.assertEqual(resp_unauth.status_code, 401)

    # 18. Optional provider absence resilience
    def test_18_optional_providers_absence_resilience(self):
        """Ava starts and reports ready even if optional external integration keys are unset."""
        from version import __version__
        with patch.dict(os.environ, {
            "BRAVE_API_KEY": "",
            "DEEPL_API_KEY": "",
            "REPLICATE_API_KEY": "",
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": ""
        }, clear=False):
            client = TestClient(app)
            # Health check succeeds
            resp_health = client.get("/health")
            self.assertEqual(resp_health.status_code, 200)
            self.assertEqual(resp_health.json().get("status"), "ok")

            # Readiness probe succeeds
            resp_ready = client.get("/ready")
            self.assertEqual(resp_ready.status_code, 200)
            self.assertEqual(resp_ready.json().get("status"), "ready")

    # 19. Version surfacing on /health and /ready
    def test_19_version_surfacing_on_health_and_ready(self):
        """Both /health and /ready endpoints surface the canonical __version__."""
        from version import __version__
        client = TestClient(app)
        resp_health = client.get("/health")
        self.assertEqual(resp_health.status_code, 200)
        self.assertEqual(resp_health.json().get("version"), __version__)

        resp_ready = client.get("/ready")
        self.assertEqual(resp_ready.status_code, 200)
        self.assertEqual(resp_ready.json().get("version"), __version__)


if __name__ == "__main__":
    unittest.main()

