# Ava AI — Release Readiness Checklist (`v1.0.0-rc1`)

This document establishes the pre-deployment verification criteria, configuration hardening checks, testing standards, and disaster recovery procedures for **Ava AI `v1.0.0-rc1`**.

---

## 1. System Architecture & Model Constraints

- [x] **Core Architecture**: `AVA = LLM + Persistent Factual Memory + Session Memory + Behavioral Preference Learning + Feedback-Driven Strategy Learning + Closed-Loop Behavioral Adaptation`.
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
  ava-ai:1.0.0-rc1
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
python scripts/restore_db.py --source /backups/ava_backup_20260920.db
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
  - Returns HTTP 200 `{"status": "ready", "version": "1.0.0-rc1", "database": "connected", "storage": "writable"}`
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
# 1. Run all 82 unit, security, and reliability tests
python -m unittest test_adaptation.py test_security.py test_reliability.py -v

# 2. Run offline behavioral adaptation quality evaluation (8 test scenarios)
python evaluation/evaluate_adaptation.py

# 3. Run automated post-deployment smoke test (against active server)
python scripts/smoke_test.py --base-url http://127.0.0.1:8000

# 4. Run multi-user concurrency and SQLite contention load test
python scripts/load_test.py --base-url http://127.0.0.1:8000 --users 25 --requests-per-user 3
```

### Test Suite Breakdown
| Suite | File | Tests | Coverage Scope |
| :--- | :--- | :--- | :--- |
| **Adaptation** | `test_adaptation.py` | 45 | Preference learning, decays, strategy recovery, policy overrides, multi-user isolation |
| **Security** | `test_security.py` | 20 | Auth isolation, CSRF/session cookies, rate limiting, SQL injection defense, path traversal |
| **Reliability** | `test_reliability.py` | 17 | Persistence, backups, restores, schema versioning, retry policies, fallback degradation |
| **Evaluation** | `evaluation/evaluate_adaptation.py` | 8 | Realistic multi-turn persona evaluation (coders, students, analysts, reversals) |
| **Smoke Test**| `scripts/smoke_test.py` | 9 | End-to-end operational sanity check (/health, /ready, auth, chat, feedback, logout) |

---

## 6. Pre-Flight Sign-Off

- [x] Version declared as `1.0.0-rc1` in `version.py`.
- [x] Dockerfile configured with non-root user `appuser`, persistent volume paths, and robust healthcheck.
- [x] All 82 unit tests passing (0 failures, 0 errors).
- [x] Adaptation quality evaluation 8/8 passing.
- [x] Deployment smoke test passing.
- [x] Concurrency load test passing with 0 SQLite lock errors.
- [x] CI workflow updated and green on GitHub Actions.
