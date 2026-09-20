# Ava AI — Release Readiness Checklist (`v1.0.0`)

This document establishes the pre-deployment verification criteria, configuration hardening checks, testing standards, and disaster recovery procedures for **Ava AI `v1.0.0`**.

---

## 1. System Architecture & Model Constraints

- [x] **Core Architecture**: `AVA = LLM + Persistent Factual Memory + Session Memory + Behavioral Preference Learning + Feedback-Driven Strategy Learning + Closed-Loop Behavioral Adaptation`.
- [x] **Behavioral Modeling**: Ava models exactly 6 behavioral preference dimensions (`verbosity`, `technical_depth`, `code_examples`, `step_by_step`, `examples`, `tone`) and 6 predefined behavioral response strategies (`concise_direct`, `concise_with_code`, `detailed_step_by_step`, `step_by_step_code`, `code_first`, `detailed_explanation`).
- [x] **Base Model**: `llama-3.3-70b-versatile` via Groq API.
- [x] **Model Weights Policy**: Model weights remain completely unchanged during user conversations (inference-only).
- [x] **Strict Non-RAG Guarantee**: Zero vector databases, zero embeddings, zero vector indexes (FAISS, ChromaDB, Pinecone, Qdrant, Weaviate), and zero semantic top-k retrieval.
- [x] **External Integrations**: Optional tools (Brave web search, DeepL translation, Replicate images, Judge0 code execution) fail gracefully with clean fallbacks without interrupting conversation flow.

---

## 2. Configuration & Production Hardening

Before deploying to production, verify each setting in your `.env` or container environment:

| Variable | Recommended Production Value | Critical Requirement |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `production` | Enforces HTTPS-only cookies and strict config validation. |
| `SECRET_KEY` | *(64-character hex string)* | **Mandatory.** Application refuses to boot if missing or default in production. |
| `ALLOWED_ORIGINS` | `https://yourdomain.com` | **No wildcards (`*`)** permitted in production. |
| `ADMIN_PASSWORD` | *(Strong, 16+ chars)* | Required for accessing `/admin.html` and `/api/metrics`. |
| `ENABLE_CODE_EXECUTION`| `false` | Disables untrusted code execution sandbox in shared environments. |
| `DB_PATH` | `/app/data/neurosupport.db` | Must be mounted on persistent host storage. |
| `UPLOAD_DIR` | `/app/data/uploads` | Must be located on persistent host storage. |
| `REVIEW_IMAGE_DIR` | `/app/data/review_images` | Must be located on persistent host storage. |
| `GROQ_API_KEY` | `gsk_...` | API key with access to `llama-3.3-70b-versatile`. |

### Generation of Production Secret Key
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 3. Persistence, Backup & Disaster Recovery

### Data Volume Mount
When running via Docker, mount a persistent host volume to `/app/data`:
```bash
docker run -d \
  -p 8000:8000 \
  --name ava-ai \
  --env-file .env.production \
  -v /var/lib/ava/data:/app/data \
  ava-ai:1.0.0
```

### Online Backup Procedure
Execute online backups without taking Ava offline (uses SQLite Online Backup API):
```bash
python scripts/backup_db.py --dest /backups/ava_backup_$(date +%Y%m%d_%H%M%S).db
```

### Database Integrity Verification
```bash
python -c "import database as db; print('Integrity:', db.check_database_integrity())"
# Expected output: Integrity: ok
```

### Restore Procedure
Restores database from backup, creates an automatic safety backup of current state, runs any pending migrations, and verifies restored integrity:
```bash
python scripts/restore_db.py /backups/ava_backup_20260920.db --confirm
```

### Schema Version Tracking
Ava tracks schema migrations via the `schema_migrations` table:
- **v1**: Initial core schema (users, sessions, messages, memory, documents, reviews, feedback)
- **v2**: Session summaries and pin metadata
- **v3**: Behavioral adaptation profiles and strategy stats
- **v4**: Strategy evidence timestamps for independent decay
- **v5**: Truthful adapted response count tracking

---

## 4. Observability & Monitoring

### Probes
- **Liveness Probe**: `GET /health`
  - Returns HTTP 200 `{"status": "ok"}`
- **Readiness Probe**: `GET /ready`
  - Returns HTTP 200 `{"status": "ready", "version": "1.0.0", "database": "connected", "storage": "writable"}`
  - Returns HTTP 503 if database connection fails, schema is inaccessible, or storage directories are unwritable.
  - *Design Note*: External LLM (Groq) uptime does not fail the readiness probe, preventing cascading pod restarts.

### Operational Metrics (`GET /api/metrics`)
Admin-authenticated endpoint returning real-time metrics with zero high-cardinality data:
- `chat_requests`, `chat_errors`, `stream_requests`, `llm_failures`
- `adaptation_used_count`, `feedback_positive`, `feedback_negative`
- `rate_limit_events`, `database_errors`
- `latency.count`, `latency.avg_ms`, `latency.min_ms`, `latency.max_ms`
- `uptime_seconds`

---

## 5. Verification Test Suite Matrix

Ensure all test suites pass with 100% green status before tagging release:

```bash
# 1. Run all 86 unit, security, and reliability tests
python -m unittest test_adaptation.py test_security.py test_reliability.py -v

# 2. Run offline behavioral adaptation quality evaluation (8 test scenarios)
python evaluation/evaluate_adaptation.py

# 3. Run automated post-deployment smoke test (against active server)
python scripts/smoke_test.py --base-url http://127.0.0.1:8000

# 4. Run multi-user concurrency and SQLite contention load test
python scripts/load_test.py --base-url http://127.0.0.1:8000 --users 25 --requests-per-user 3
```

### Test Suite Breakdown
| Suite | File | Tests | Status | Coverage Scope |
| :--- | :--- | :--- | :--- | :--- |
| **Adaptation** | `test_adaptation.py` | 45 | **45/45 PASS** | Preference learning, decays, strategy recovery, policy overrides, multi-user isolation |
| **Security** | `test_security.py` | 22 | **22/22 PASS** | Auth isolation, CSRF/session cookies, rate limiting, SQL injection defense, path traversal, user data deletion, log redaction |
| **Reliability** | `test_reliability.py` | 19 | **19/19 PASS** | Persistence, backups, restores, schema versioning, retry policies, fallback degradation, provider resilience, version surfacing |
| **Evaluation** | `evaluation/evaluate_adaptation.py` | 8 | **8/8 PASS** | Realistic multi-turn persona evaluation (coders, students, analysts, reversals) |
| **Core Smoke** | `scripts/smoke_test.py --offline` | 11 | **11/11 PASS** | End-to-end operational sanity check (/health, /ready, signup, login, session, memory, adaptation, IDOR denial, logout) |
| **Backup / Restore** | `scripts/verify_backup_restore.py` | CLI | **PASS** | Live hot backup and restore operational execution via subprocess with integrity verification |
| **Concurrency Load** | `scripts/run_controlled_load_test.py` | 680 reqs | **PASS** | 10, 25, 50 concurrent users: 100% success rate, 0 SQLite lock errors |

---

## 6. Pre-Flight Sign-Off & Verification Evidence

- [x] **Version**: Declared as `1.0.0` in `version.py`.
- [x] **Configuration**: `.env.example` (development) and `.env.production.example` (production/Docker) clearly separated.
- [x] **Restore CLI**: Canonical command `python scripts/restore_db.py <backup_file> --confirm` documented everywhere.
- [x] **Dockerfile**: Hardened non-root user `appuser`, persistent volume path `/app/data`, and healthcheck probe.
- [x] **All Automated Tests**: 86 / 86 passing (0 failures, 0 errors across adaptation, security, and reliability).
- [x] **Adaptation Quality Evaluation**: 8 / 8 scenarios passing.
- [x] **Operational Smoke Test**: 11 / 11 verification steps passing (`scripts/smoke_test.py --offline`).
- [x] **Docker Volume Persistence**: Verified across container recreation (`scripts/test_docker_persistence.sh`).
- [x] **Operational Hot Backup & Restore**: Live subprocess CLI execution verified (`scripts/verify_backup_restore.py`).
- [x] **Controlled Concurrency Load Test**:
  - *Date*: 2026-09-20 09:15:06 UTC
  - *Environment*: Local WAL SQLite, mocked LLM inference
  - *Concurrency*: 10, 25, 50 concurrent users
  - *Request Count*: 680 total requests
  - *Error Rate*: 0.0% (100.0% success rate across all tiers)
  - *SQLite Lock Errors*: **0**
  - *Latency Results*:
    - 10 users: avg 154.89ms | p50 146.46ms | p95 326.73ms | p99 424.31ms
    - 25 users: avg 289.28ms | p50 185.56ms | p95 1108.59ms | p99 1872.07ms
    - 50 users: avg 541.75ms | p50 377.54ms | p95 2033.54ms | p99 4064.51ms
- [x] **CI Pipeline**: Two-stage GitHub Actions pipeline (`test` -> `docker-smoke`) defined in `.github/workflows/tests.yml`.
- [x] **Release Verification Report**: Documented in `RELEASE_VERIFICATION.md`.
