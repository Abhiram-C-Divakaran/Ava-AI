# Ava AI

> **Adaptive Personal AI Assistant**  
> `AVA = LLM + Persistent Factual Memory + Behavioral Preference Learning + Feedback-Driven Strategy Learning + Closed-Loop Behavioral Adaptation`

---

## 1. Architectural Overview

Ava AI is a personal intelligence assistant designed around persistent personalization without altering underlying neural network weights or relying on semantic vector search.

```
+─────────────────────────────────────────────────────────────────────────────+
|                                 USER INPUT                                  |
+──────────────────────────────────────┬──────────────────────────────────────+
                                       │
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
|                         ML PIPELINE CLASSIFICATION                          |
|         - Intent Classifier  - Sentiment Analyzer  - Frustration Detector   |
+──────────────────────────────────────┬──────────────────────────────────────+
                                       │
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
|                         BEHAVIORAL ADAPTATION ENGINE                        |
|   - 6 Dimensional Profiles (verbosity, depth, code, step-by-step, examples) |
|   - 6 Discrete Behavioral Strategies with Recency-Aware Scoring             |
|   - Recency-Aware Exponential Evidence Decay (Positive & Negative Half-Lives)|
|   - Strict Current-Request Override Arbitration                             |
+──────────────────────────────────────┬──────────────────────────────────────+
                                       │
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
|                        CONTEXT ASSEMBLY & INJECTION                         |
|   - System Persona & Directives                                             |
|   - Cross-Session User Factual Memory (Relational SQLite)                   |
|   - Behavioral Prompt Modulation Directives                                 |
|   - Session History (Last K Messages)                                       |
+──────────────────────────────────────┬──────────────────────────────────────+
                                       │
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
|                               GENERATIVE CORE                               |
|              Model: LLaMA 3.3 70B Versatile (via Groq LPUs)                 |
+──────────────────────────────────────┬──────────────────────────────────────+
                                       │
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
|                        RESPONSE DELIVERY & LOGGING                          |
|   - Streaming SSE / Synchronous REST API                                    |
|   - Observation Event Recording (Database & Structured Logs)                |
+──────────────────────────────────────┬──────────────────────────────────────+
                                       │
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
|                     EXPLICIT FEEDBACK & CLOSED LOOP                         |
|   - Thumbs Up/Down Recording                                                |
|   - Strategy Success/Failure Attribution & Confidence Updates               |
|   - Failed Solution Tracking for Self-Correction                            |
+─────────────────────────────────────────────────────────────────────────────+
```

### Why Ava Is Strictly Non-RAG

Ava is deliberately engineered **NOT** to be a vector Retrieval-Augmented Generation (RAG) system. Ava does not employ:
- Vector databases (e.g., Pinecone, ChromaDB, Milvus, Weaviate, FAISS)
- Dense or sparse vector embeddings
- Semantic similarity search or Top-K embedding retrieval
- Vectorized conversation history

**Rationale**:
1. **Precision Over Probability**: Semantic vector search frequently suffers from false-positive matches, semantic drift, and chunk fragmentation where critical factual nuance is lost.
2. **Explicit Behavioral Transparency**: Personal preferences (such as desiring concise code vs. step-by-step conceptual walkthroughs) are discrete behavioral policies, not vector coordinates. Modeling them with explicit state machines, Bayesian confidence scores, and strategy statistics guarantees deterministic auditability.
3. **Zero Weight Alteration**: Ava learns from the user during conversation loops while keeping base LLM weights frozen, avoiding catastrophic forgetting and inference degradation.

---

## 2. Core Capabilities & Mechanics

### Generative Core
- **Primary Model**: `llama-3.3-70b-versatile` (via Groq Cloud API)
- **Voice Transcription**: `whisper-large-v3`

### The 6 Behavioral Preference Dimensions
Ava currently models six behavioral preference dimensions and six predefined behavioral response strategies. Every user profile tracks these 6 core behavioral preferences stored with confidence scores $[0.0, 1.0]$:
1. `verbosity`: `concise` | `balanced` | `detailed`
2. `technical_depth`: `beginner` | `intermediate` | `advanced`
3. `code_examples`: `true` | `false`
4. `step_by_step`: `true` | `false`
5. `examples`: `true` | `false`
6. `tone`: `friendly` | `direct` | `formal`

### The 6 Behavioral Response Strategies
When generating responses, Ava selects from six predefined behavioral response strategies tailored to the user's past feedback and current intent:
1. `concise_direct`: Provide a short, direct answer with minimal extra explanation.
2. `concise_with_code`: Prefer concise responses with focused code examples when appropriate. Provide a short explanation followed by clean, focused code.
3. `detailed_step_by_step`: Provide a thorough, structured, step-by-step walkthrough.
4. `step_by_step_code`: Provide a structured, step-by-step explanation with code snippets at relevant steps.
5. `code_first`: Lead directly with the code implementation, then provide explanation afterward.
6. `detailed_explanation`: Provide deep conceptual and architectural explanations before practical implementation.

### Strategy Learning & Evidence Decay
- Strategy efficacy is tracked through positive and negative feedback instances.
- **Dual-Decay Half-Life Formula**: Positive evidence and negative evidence decay independently using exponential half-life functions. This prevents stale historical failures from permanently suppressing strategies while allowing newer positive interactions to restore confidence.
- **Current-Request Override**: If the user explicitly asks for a format contradictory to their long-term profile (e.g., asking *"Give me a long, detailed explanation"* when their profile is set to `concise`), the explicit prompt immediately overrides the learned preference for that turn.

---

## 3. Production Hardening & Security Architecture

Phase 4 introduces rigorous production hardening across all layers of the application:

1. **Authoritative Session Authentication & IDOR Protection**:
   - All user-scoped endpoints authenticate strictly through encrypted session cookies (`request.session["user_id"]`).
   - Every session, message, document, memory, and adaptation access operation validates ownership against the session owner.
2. **Multi-Tier Rate Limiting**:
   - Powered by `slowapi` with fallback IP and user-keyed rate limits.
   - Authentication endpoints (`/api/auth/signup`, `/api/auth/login`, `/api/user/password`): `5/minute`.
   - Generative and streaming endpoints (`/api/chat`, `/api/chat/stream`, `/api/feedback`): `30/minute`.
   - Resource-intensive endpoints (`/api/generate-image`, `/api/generate-ppt`): `5/minute`.
3. **CORS & Cookie Hardening**:
   - Explicit `ALLOWED_ORIGINS` configuration.
   - Session cookies configured with `same_site="lax"` and `https_only=True` in production.
4. **Structured JSON Logging & Credential Masking**:
   - Uses `python-json-logger` emitting machine-readable JSON logs.
   - Redacts passwords, bearer tokens, OAuth secrets, and authorization headers from all logs.
5. **Correlation Request IDs**:
   - Injects `X-Request-ID` into every HTTP transaction via Starlette middleware for end-to-end distributed tracing.
6. **Observability & Health Checks**:
   - `GET /health`: Instant liveness probe for process supervision.
   - `GET /ready`: Fast SQLite connectivity verification (zero external LLM dependencies).
7. **Upload Hardening**:
   - Restricts file uploads to an extension whitelist (`.pdf`, `.docx`, `.xlsx`, `.xls`, `.pptx`, `.csv`, `.tsv`, `.txt`, `.md`, `.log`).
   - Limits file size to 10MB.
   - Path traversal prevention using `os.path.basename`.
8. **Code Execution Safety**:
   - Code execution engine is disabled by default in production environments (`ENABLE_CODE_EXECUTION=false`).
9. **SQLite Production Reliability**:
   - Configured with `busy_timeout=5000` (5-second lock queue).
   - Write-Ahead Logging (`PRAGMA journal_mode = WAL`) enabled for high-concurrency read/write transactions.

---

## 4. Getting Started

### Prerequisites
- Python 3.11+
- Git

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Abhiram-C-Divakaran/Ava-AI.git
   cd Ava-AI
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   # On Linux / macOS:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   - For local development:
     ```bash
     cp .env.example .env
     ```
     Edit `.env` to provide your `GROQ_API_KEY` and a cryptographically secure `SECRET_KEY`.
   - For production Docker deployments:
     ```bash
     cp .env.production.example .env.production
     ```
     Ensure `DB_PATH`, `UPLOAD_DIR`, and `REVIEW_IMAGE_DIR` map to `/app/data/...` persistent volume storage.

---

## 5. Running the Application

### Development Server
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Open [http://localhost:8000](http://localhost:8000) in your browser.

### Production Server
Ensure `ENVIRONMENT=production` and `SECRET_KEY` are configured:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

---

## 6. Testing & Evaluation

The repository contains 86 automated unit tests across three suites (executing in ~7 seconds offline) plus an 8-scenario behavioral adaptation evaluation suite and deployment smoke/load benchmarks:

### Run All 86 Unit Tests
```bash
python -m unittest test_adaptation.py test_security.py test_reliability.py -v
```

### 1. Adaptation Test Suite (45 Tests)
Validates behavioral learning, strategy statistics, Bayesian updates, exponential decay, token-boundary matching, and multi-user profile isolation:
```bash
python -m unittest test_adaptation.py -v
```

### 2. Security Test Suite (22 Tests)
Validates authentication, authorization, IDOR checks, rate limiting, CORS preflight, production secrets validation, path traversal prevention, user data deletion, log credential masking, and admin role enforcement:
```bash
python -m unittest test_security.py -v
```

### 3. Operational Reliability Test Suite (19 Tests)
Validates persistent storage, online SQLite backup/restore, schema migrations tracking, concurrent multi-threaded writes without lock contention, LLM retry and timeout policies, external tool graceful degradation, and version surfacing:
```bash
python -m unittest test_reliability.py -v
```

### 4. Behavioral Adaptation Evaluation (8 Scenarios)
Offline evaluation against 8 canonical multi-turn behavioral scenarios (programmers, students, analysts, reversals, and overrides):
```bash
python evaluation/evaluate_adaptation.py
```

### 5. 60-Case Automated Behavioral-Policy Evaluation (Structural)
Structural regression suite verifying prompt construction, adaptation policy state, memory presence, override logic, and tool runtime stability across 60 cases:
```bash
python scripts/run_staging_observation.py
```

### 6. Response A/B Quality Evaluation Pipeline
Ava has a validated offline controlled A/B evaluation pipeline. Generates paired outputs (Variant Baseline without adaptation vs Variant Adapted with behavioral policy) with randomized presentation for blind human evaluation:
```bash
# Offline controlled deterministic evaluation
python evaluation/run_response_eval.py --mode offline

# Live Groq evaluation (requires real GROQ_API_KEY)
python evaluation/run_response_eval.py --mode live --temperature 0.2
```

### 7. Evaluation Integrity Test Suite (15 Tests)
Validates evaluation harness modes, strict fallback prohibition, schema validation, review completeness, and blinding:
```bash
python -m unittest evaluation/test_evaluation_integrity.py -v
```

### 8. Independent Factual Memory Benchmark
Evaluates factual memory recall accuracy, omission rate, false-memory rate, and cross-user isolation:
```bash
python evaluation/evaluate_memory.py
```

### 9. Adaptation Convergence & Strategy Learning Benchmark
Empirically measures signal thresholds required for preference convergence across all 6 dimensions, preference reversal dynamics, and the 6-strategy learning matrix:
```bash
python evaluation/evaluate_convergence_and_strategies.py
```

### 9. Deployment Smoke Test & Load Benchmark
Validate active deployment health, auth, session, chat, feedback, and concurrency under write load:
```bash
# Smoke test active server
python scripts/smoke_test.py --base-url http://127.0.0.1:8000

# Concurrency load benchmark (e.g. 25 users)
python scripts/load_test.py --base-url http://127.0.0.1:8000 --users 25 --requests-per-user 3
```

---

## 7. Database Management & Operations

### Online Backup & Safe Restore
Safely backup the active SQLite database without taking Ava offline, and restore with automatic pre-restore safety snapshots and integrity verification:
```bash
# Online hot backup
python scripts/backup_db.py --dest /backups/ava_backup_$(date +%Y%m%d_%H%M%S).db

# Safe restore with integrity check and migrations
python scripts/restore_db.py /backups/ava_backup.db --confirm
```

### Health, Readiness & Metrics Endpoints
- **Liveness**: `GET /health` -> `{"status": "ok", "version": "1.0.1"}`
- **Readiness**: `GET /ready` -> `{"status": "ready", "version": "1.0.1", "database": "connected", "storage": "writable"}`
- **Operational Metrics**: `GET /api/metrics` (Admin authenticated, returns counters, latencies, and uptime)

---

## 8. Docker Deployment & Reverse Proxy Setup

A hardened multi-stage production Dockerfile is included:
```bash
# Build the Docker image
docker build -t ava-ai:1.0.1 .

# Run container with persistent host volume
docker run -d \
  -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e SECRET_KEY="your_secure_random_production_secret" \
  -e GROQ_API_KEY="your_groq_api_key" \
  -e ADMIN_PASSWORD="your_secure_admin_password" \
  -v /var/lib/ava/data:/app/data \
  --name ava-app \
  ava-ai:1.0.0
```

### Reverse Proxy & Rate Limiting Behind Proxies
When deploying Ava behind a reverse proxy (e.g. Nginx, Cloudflare, Traefik, Caddy, AWS ALB, Render, Railway, Fly.io):
- **Rate Limiting**: Authenticated requests are rate-limited per user ID (`user:{user_id}`). Unauthenticated requests (e.g., signup/login) are rate-limited by IP (`ip:{client_ip}`).
- **Trusted Proxies**: Do not blindly trust spoofable `X-Forwarded-For` headers from untrusted clients. Configure your upstream proxy (e.g., Nginx `proxy_set_header X-Forwarded-For $remote_addr;` or Uvicorn `--proxy-headers --forwarded-allow-ips`) to safely map real client IPs.

---

## 9. License

Ava AI is open-source software licensed under the MIT License.
