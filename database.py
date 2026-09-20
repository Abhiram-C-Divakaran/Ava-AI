"""
database.py — SQLite persistence layer for Ava AI.
"""
import sqlite3
import hashlib
import hmac
import os
import secrets
import json
from datetime import datetime, timezone
from contextlib import contextmanager

from cache import prefs_cache  # assuming cache.py exists
import config

DB_PATH = config.DB_PATH

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def check_database_integrity(target_path: str | None = None) -> str:
    """Run PRAGMA integrity_check returning 'ok' or error message."""
    if target_path:
        try:
            conn = sqlite3.connect(target_path, timeout=5.0)
            cursor = conn.execute("PRAGMA integrity_check;")
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else "unknown"
        except Exception as e:
            return f"error: {str(e)}"
    with get_conn() as conn:
        cursor = conn.execute("PRAGMA integrity_check;")
        row = cursor.fetchone()
        return row[0] if row else "unknown"

def backup_database(destination_path: str) -> str:
    """Safely create an online SQLite backup of DB_PATH using SQLite's native backup API."""
    dest_dir = os.path.dirname(os.path.abspath(destination_path)) or "."
    os.makedirs(dest_dir, exist_ok=True)
    with get_conn() as src_conn:
        dest_conn = sqlite3.connect(destination_path)
        try:
            with dest_conn:
                src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    return destination_path

def restore_database(backup_path: str, create_safety_backup: bool = True) -> dict:
    """
    Validate and restore an SQLite backup into DB_PATH.
    1. Validates backup SQLite file exists and passes integrity check.
    2. Creates timestamped safety backup of current database.
    3. Restores backup into current database.
    4. Runs init_db() schema migrations.
    5. Verifies integrity.
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # 1. Validate backup file integrity
    chk_conn = sqlite3.connect(backup_path)
    try:
        res = chk_conn.execute("PRAGMA integrity_check;").fetchone()
        if not res or res[0] != "ok":
            raise ValueError(f"Backup database failed integrity check: {res[0] if res else 'empty'}")
    finally:
        chk_conn.close()

    # 2. Safety backup of current database if exists and has content
    safety_backup_path = None
    if create_safety_backup and os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safety_backup_path = f"{DB_PATH}.safety_{ts}.bak"
        backup_database(safety_backup_path)

    # 3. Restore backup into DB_PATH using SQLite backup API
    src_conn = sqlite3.connect(backup_path)
    try:
        with get_conn() as dest_conn:
            with dest_conn:
                src_conn.backup(dest_conn)
    finally:
        src_conn.close()

    # 4. Run migrations to ensure up to date schema
    init_db()

    # 5. Verify integrity of newly restored DB
    integrity = check_database_integrity()
    if integrity != "ok":
        raise RuntimeError(f"Restored database integrity check failed: {integrity}")

    return {
        "status": "restored",
        "backup_source": backup_path,
        "safety_backup": safety_backup_path,
        "integrity": integrity
    }

def get_applied_migrations() -> list[dict]:
    """Retrieve all recorded schema migrations."""
    with get_conn() as conn:
        try:
            rows = conn.execute("SELECT version, description, applied_at FROM schema_migrations ORDER BY version ASC").fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

def init_db():
    with get_conn() as conn:
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError:
            pass

        # Ensure schema_migrations table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at  TEXT NOT NULL
            );
            """
        )

        def is_applied(v: int) -> bool:
            row = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (v,)).fetchone()
            return row is not None

        def record_migration(v: int, desc: str):
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                (v, desc, _now())
            )

        # Migration 1: Initial core schema
        if not is_applied(1):
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id        TEXT PRIMARY KEY,
                    name           TEXT NOT NULL,
                    email          TEXT UNIQUE NOT NULL,
                    password_hash  TEXT NOT NULL,
                    password_salt  TEXT NOT NULL,
                    created_at     TEXT NOT NULL,
                    custom_instructions TEXT,
                    personality    TEXT DEFAULT 'friendly',
                    preferences    TEXT DEFAULT '{"theme":"light"}',
                    is_admin       INTEGER DEFAULT 0,
                    terms_accepted INTEGER DEFAULT 0,
                    terms_accepted_date TEXT
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id   TEXT PRIMARY KEY,
                    user_id      TEXT NOT NULL,
                    title        TEXT,
                    created_at   TEXT NOT NULL,
                    last_active  TEXT NOT NULL,
                    pinned       INTEGER DEFAULT 0,
                    share_token  TEXT UNIQUE,
                    summary      TEXT,
                    summary_through_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id      TEXT PRIMARY KEY,
                    session_id      TEXT NOT NULL,
                    user_id         TEXT NOT NULL,
                    user_message    TEXT NOT NULL,
                    agent_response  TEXT NOT NULL,
                    intent          TEXT,
                    sentiment_label TEXT,
                    sentiment_score REAL,
                    frustration     REAL,
                    latency_ms      INTEGER,
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL,
                    session_id  TEXT NOT NULL,
                    message_id  TEXT NOT NULL,
                    helpful     INTEGER NOT NULL,
                    created_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS failed_solutions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL,
                    session_id  TEXT NOT NULL,
                    solution    TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    doc_id          TEXT PRIMARY KEY,
                    user_id         TEXT NOT NULL,
                    filename        TEXT NOT NULL,
                    file_path       TEXT NOT NULL,
                    extracted_text  TEXT,
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_memory (
                    user_id         TEXT PRIMARY KEY,
                    memory_text     TEXT NOT NULL DEFAULT '',
                    updated_at      TEXT NOT NULL,
                    message_count_at_update INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS reviews (
                    review_id       TEXT PRIMARY KEY,
                    reviewer_name   TEXT NOT NULL,
                    reviewer_title  TEXT,
                    rating          INTEGER NOT NULL,
                    review_text     TEXT NOT NULL,
                    image_path      TEXT,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    featured        INTEGER NOT NULL DEFAULT 0,
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS adaptation_profiles (
                    user_id                TEXT PRIMARY KEY,
                    profile_json           TEXT NOT NULL,
                    updated_at             TEXT NOT NULL,
                    interaction_count      INTEGER NOT NULL DEFAULT 0,
                    adapted_response_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS adaptation_strategy_stats (
                    user_id         TEXT NOT NULL,
                    strategy        TEXT NOT NULL,
                    successes       INTEGER NOT NULL DEFAULT 0,
                    failures        INTEGER NOT NULL DEFAULT 0,
                    last_updated    TEXT,
                    last_success_at TEXT,
                    last_failure_at TEXT,
                    PRIMARY KEY (user_id, strategy)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_user    ON messages(user_id);
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_user    ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_failed_user      ON failed_solutions(user_id);
                CREATE INDEX IF NOT EXISTS idx_documents_user   ON documents(user_id);
                CREATE INDEX IF NOT EXISTS idx_adaptation_stats_user ON adaptation_strategy_stats(user_id);
                CREATE INDEX IF NOT EXISTS idx_reviews_status   ON reviews(status);
                """
            )
            # Guarded column additions for users & reviews if migrated from ancient DB
            for sql in [
                "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN terms_accepted INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN terms_accepted_date TEXT",
                "ALTER TABLE reviews ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'",
                "ALTER TABLE reviews ADD COLUMN featured INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE user_memory ADD COLUMN message_count_at_update INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE messages ADD COLUMN sentiment_label TEXT",
                "ALTER TABLE messages ADD COLUMN sentiment_score REAL",
            ]:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass
            record_migration(1, "Initial core schema")

        # Migration 2: Session summaries and pins
        if not is_applied(2):
            for sql in [
                "ALTER TABLE sessions ADD COLUMN summary TEXT",
                "ALTER TABLE sessions ADD COLUMN summary_through_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE sessions ADD COLUMN pinned INTEGER DEFAULT 0",
            ]:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass
            record_migration(2, "Session summaries and pin metadata")

        # Migration 3: Adaptation profiles and strategy stats
        if not is_applied(3):
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS adaptation_profiles (
                    user_id                TEXT PRIMARY KEY,
                    profile_json           TEXT NOT NULL,
                    updated_at             TEXT NOT NULL,
                    interaction_count      INTEGER NOT NULL DEFAULT 0,
                    adapted_response_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS adaptation_strategy_stats (
                    user_id         TEXT NOT NULL,
                    strategy        TEXT NOT NULL,
                    successes       INTEGER NOT NULL DEFAULT 0,
                    failures        INTEGER NOT NULL DEFAULT 0,
                    last_updated    TEXT,
                    last_success_at TEXT,
                    last_failure_at TEXT,
                    PRIMARY KEY (user_id, strategy)
                );

                CREATE INDEX IF NOT EXISTS idx_adaptation_stats_user ON adaptation_strategy_stats(user_id);
                """
            )
            record_migration(3, "Behavioral adaptation profiles and strategy stats")

        # Migration 4: Strategy timestamps
        if not is_applied(4):
            for col in ["last_updated TEXT", "last_success_at TEXT", "last_failure_at TEXT"]:
                try:
                    conn.execute(f"ALTER TABLE adaptation_strategy_stats ADD COLUMN {col}")
                except sqlite3.OperationalError:
                    pass
            record_migration(4, "Strategy evidence timestamps for independent decay")

        # Migration 5: Adapted response count
        if not is_applied(5):
            try:
                conn.execute("ALTER TABLE adaptation_profiles ADD COLUMN adapted_response_count INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            record_migration(5, "Adapted response count tracking")

# ─── Auth ─────────────────────────────────────────────────────────────────────
def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return digest.hex(), salt

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    digest, _ = _hash_password(password, salt)
    return hmac.compare_digest(digest, password_hash)

def create_user(user_id: str, name: str, email: str, password: str, terms_accepted: bool = False) -> None:
    password_hash, salt = _hash_password(password)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (user_id, name, email, password_hash, password_salt, created_at, is_admin, terms_accepted, terms_accepted_date) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (user_id, name, email.lower().strip(), password_hash, salt, _now(), 
             1 if terms_accepted else 0, 
             _now() if terms_accepted else None),
        )

def get_user_by_email(email: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

get_user = get_user_by_id

def email_exists(email: str) -> bool:
    return get_user_by_email(email) is not None

def update_password(user_id: str, new_password: str) -> None:
    password_hash, salt = _hash_password(new_password)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, password_salt = ? WHERE user_id = ?",
            (password_hash, salt, user_id)
        )

def get_terms_acceptance(user_id: str) -> dict:
    """Get terms acceptance status for a user."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT terms_accepted, terms_accepted_date FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if not row:
            return {"terms_accepted": False, "terms_accepted_date": None}
        return {
            "terms_accepted": bool(row["terms_accepted"]),
            "terms_accepted_date": row["terms_accepted_date"]
        }

def update_terms_acceptance(user_id: str, accepted: bool = True) -> None:
    """Update terms acceptance status for a user."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET terms_accepted = ?, terms_accepted_date = ? WHERE user_id = ?",
            (1 if accepted else 0, _now() if accepted else None, user_id)
        )

# ─── User Preferences (with caching) ──────────────────────────────────────────
def get_user_preferences(user_id: str) -> dict:
    cached = prefs_cache.get(user_id)
    if cached is not None:
        return cached
    with get_conn() as conn:
        row = conn.execute(
            "SELECT custom_instructions, personality, preferences FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if not row:
            return {}
        prefs = json.loads(row["preferences"]) if row["preferences"] else {}
        result = {
            "custom_instructions": row["custom_instructions"] or "",
            "personality": row["personality"] or "friendly",
            "theme": prefs.get("theme", "light")
        }
        prefs_cache.set(user_id, result)
        return result

def update_user_preferences(user_id: str, prefs: dict) -> None:
    with get_conn() as conn:
        ci = prefs.get("custom_instructions")
        pers = prefs.get("personality")
        theme = prefs.get("theme")
        row = conn.execute("SELECT preferences FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row and row["preferences"]:
            cur = json.loads(row["preferences"])
        else:
            cur = {}
        if theme:
            cur["theme"] = theme
        conn.execute(
            "UPDATE users SET custom_instructions = ?, personality = ?, preferences = ? WHERE user_id = ?",
            (ci, pers, json.dumps(cur), user_id)
        )
    prefs_cache.invalidate(user_id)

# ─── Sessions ─────────────────────────────────────────────────────────────────
def create_session(session_id: str, user_id: str, title: str | None = None) -> None:
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE sessions SET last_active = ? WHERE session_id = ?",
                (_now(), session_id),
            )
        else:
            conn.execute(
                "INSERT INTO sessions (session_id, user_id, title, created_at, last_active) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, user_id, title, _now(), _now()),
            )

def get_sessions_for_user(user_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.session_id, s.title, s.created_at, s.last_active, s.pinned, s.share_token, s.summary,
                   (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) AS message_count,
                   (SELECT m.user_message FROM messages m
                      WHERE m.session_id = s.session_id ORDER BY m.created_at ASC LIMIT 1) AS first_message
            FROM sessions s
            WHERE s.user_id = ?
            ORDER BY s.pinned DESC, s.last_active DESC
            """,
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

def get_session(session_id: str) -> dict | None:
    """Retrieve a single session by session_id."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

def get_message(message_id: str) -> dict | None:
    """Retrieve a single message by message_id."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,)).fetchone()
        return dict(row) if row else None

def get_session_messages(session_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

def delete_session(user_id: str, session_id: str) -> bool:
    with get_conn() as conn:
        msg_ids = conn.execute(
            "SELECT message_id FROM messages WHERE session_id = ? AND user_id = ?",
            (session_id, user_id)
        ).fetchall()
        for row in msg_ids:
            conn.execute("DELETE FROM feedback WHERE message_id = ?", (row["message_id"],))
        conn.execute("DELETE FROM messages WHERE session_id = ? AND user_id = ?", (session_id, user_id))
        conn.execute("DELETE FROM failed_solutions WHERE session_id = ? AND user_id = ?", (session_id, user_id))
        res = conn.execute("DELETE FROM sessions WHERE session_id = ? AND user_id = ?", (session_id, user_id))
        return res.rowcount > 0

def update_session_title(user_id: str, session_id: str, new_title: str) -> bool:
    with get_conn() as conn:
        res = conn.execute(
            "UPDATE sessions SET title = ? WHERE session_id = ? AND user_id = ?",
            (new_title, session_id, user_id)
        )
        return res.rowcount > 0

def set_pin(user_id: str, session_id: str, pinned: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET pinned = ? WHERE session_id = ? AND user_id = ?",
            (1 if pinned else 0, session_id, user_id)
        )

def search_sessions(user_id: str, query: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT session_id, title, first_message
            FROM sessions s
            WHERE user_id = ? AND (
                s.title LIKE ? OR s.session_id IN (
                    SELECT session_id FROM messages WHERE user_message LIKE ?
                )
            )
            ORDER BY last_active DESC
            """,
            (user_id, f"%{query}%", f"%{query}%")
        ).fetchall()
        return [dict(r) for r in rows]

def get_or_create_share_token(session_id: str, user_id: str) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT share_token FROM sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id)
        ).fetchone()
        if row and row["share_token"]:
            return row["share_token"]
        token = secrets.token_urlsafe(12)
        conn.execute(
            "UPDATE sessions SET share_token = ? WHERE session_id = ? AND user_id = ?",
            (token, session_id, user_id)
        )
        return token

def get_shared_session_data(token: str) -> list[dict] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT session_id FROM sessions WHERE share_token = ?", (token,)
        ).fetchone()
        if not row:
            return None
        session_id = row["session_id"]
        rows = conn.execute(
            "SELECT user_message, agent_response, sentiment_label, intent FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

# ─── Summary ──────────────────────────────────────────────────────────────────
def update_session_summary(session_id: str, summary: str, through_count: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET summary = ?, summary_through_count = ? WHERE session_id = ?",
            (summary, through_count, session_id)
        )

def get_session_summary(session_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT summary FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row["summary"] if row else None

def get_session_summary_state(session_id: str) -> dict:
    """Returns {summary, summary_through_count} so the caller knows what's already covered."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT summary, summary_through_count FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        if not row:
            return {"summary": None, "summary_through_count": 0}
        return {"summary": row["summary"], "summary_through_count": row["summary_through_count"] or 0}

# ─── Messages ─────────────────────────────────────────────────────────────────
def save_message(
    message_id: str,
    session_id: str,
    user_id: str,
    user_message: str,
    agent_response: str,
    intent: str,
    sentiment: dict,
    frustration: float,
    latency_ms: int,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO messages (
                message_id, session_id, user_id, user_message, agent_response,
                intent, sentiment_label, sentiment_score, frustration, latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id, session_id, user_id, user_message, agent_response,
                intent, sentiment.get("label"), sentiment.get("score"),
                frustration, latency_ms, _now(),
            ),
        )
        conn.execute(
            "UPDATE sessions SET last_active = ? WHERE session_id = ?",
            (_now(), session_id),
        )

def get_recent_messages(user_id: str, session_id: str | None = None, limit: int = 20) -> list[dict]:
    """Returns the most recent messages, scoped to a single session when session_id is given.

    Falls back to user-wide history (legacy behavior) only when no session_id is provided,
    e.g. for analytics or features that intentionally look across all chats.
    """
    with get_conn() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id = ? AND session_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM messages WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

def count_session_messages(session_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row["c"] if row else 0

def get_messages_in_range(session_id: str, offset: int, count: int) -> list[dict]:
    """Oldest-first slice of a session's messages, e.g. for rolling up into a summary."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?",
            (session_id, count, offset),
        ).fetchall()
        return [dict(r) for r in rows]

def get_all_messages(user_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

def get_last_agent_response(user_id: str, session_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT agent_response FROM messages WHERE user_id = ? AND session_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, session_id),
        ).fetchone()
        return row["agent_response"] if row else None

def count_similar_issues(user_id: str, current_message: str, threshold: float = 0.35) -> int:
    current_tokens = set(current_message.lower().split())
    if not current_tokens:
        return 0
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_message FROM messages WHERE user_id = ?", (user_id,)
        ).fetchall()
    count = 0
    for row in rows:
        past_tokens = set(row["user_message"].lower().split())
        union = current_tokens | past_tokens
        if not union:
            continue
        jaccard = len(current_tokens & past_tokens) / len(union)
        if jaccard > threshold:
            count += 1
    return count

def get_similar_past_queries(user_id: str, current_input: str, limit: int = 3) -> list[str]:
    """Returns similar past user messages (for suggestions)."""
    current_tokens = set(current_input.lower().split())
    if not current_tokens:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT user_message FROM messages WHERE user_id = ?",
            (user_id,)
        ).fetchall()
    similarities = []
    for row in rows:
        past_tokens = set(row["user_message"].lower().split())
        if not past_tokens:
            continue
        intersection = len(current_tokens & past_tokens)
        union = len(current_tokens | past_tokens)
        jaccard = intersection / union if union else 0
        if jaccard > 0.3:
            similarities.append((jaccard, row["user_message"]))
    similarities.sort(reverse=True, key=lambda x: x[0])
    return [msg for _, msg in similarities[:limit]]

def save_failed_solution(user_id: str, session_id: str, solution: str) -> None:
    condensed = solution[:200]
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM failed_solutions WHERE user_id = ? AND solution = ?",
            (user_id, condensed),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO failed_solutions (user_id, session_id, solution, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, session_id, condensed, _now()),
            )

def get_failed_solutions(user_id: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT solution FROM failed_solutions WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [r["solution"] for r in rows]

def save_feedback(user_id: str, session_id: str, message_id: str, helpful: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO feedback (user_id, session_id, message_id, helpful, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, session_id, message_id, 1 if helpful else 0, _now()),
        )

def get_feedback(user_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM feedback WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

# ─── Documents ─────────────────────────────────────────────────────────────────
def save_document(doc_id: str, user_id: str, filename: str, file_path: str, extracted_text: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO documents (doc_id, user_id, filename, file_path, extracted_text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, user_id, filename, file_path, extracted_text, _now())
        )

def get_document(doc_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None

def get_user_documents(user_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

# ─── Stats ─────────────────────────────────────────────────────────────────────
def get_user_stats(user_id: str) -> dict:
    with get_conn() as conn:
        messages = conn.execute(
            "SELECT * FROM messages WHERE user_id = ? ORDER BY created_at ASC", (user_id,)
        ).fetchall()
        if not messages:
            return {"total_interactions": 0}
        sentiments = [m["sentiment_label"] for m in messages]
        intents = [m["intent"] for m in messages]
        avg_frustration = sum(m["frustration"] or 0 for m in messages) / len(messages)
        avg_latency = sum(m["latency_ms"] or 0 for m in messages) / len(messages)
        failed_count = conn.execute(
            "SELECT COUNT(*) AS c FROM failed_solutions WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]
        return {
            "total_interactions": len(messages),
            "failed_solutions_count": failed_count,
            "sentiment_breakdown": {s: sentiments.count(s) for s in set(sentiments)},
            "top_intent": max(set(intents), key=intents.count) if intents else "unknown",
            "avg_frustration": round(avg_frustration, 3),
            "avg_latency_ms": round(avg_latency, 1),
            "first_seen": messages[0]["created_at"][:10],
            "last_seen": messages[-1]["created_at"][:10],
        }

def get_global_analytics() -> dict:
    with get_conn() as conn:
        total_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        total_interactions = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
        intent_rows = conn.execute(
            "SELECT intent, COUNT(*) AS c FROM messages GROUP BY intent ORDER BY c DESC LIMIT 5"
        ).fetchall()
        sentiment_rows = conn.execute(
            "SELECT sentiment_label, COUNT(*) AS c FROM messages GROUP BY sentiment_label"
        ).fetchall()
        avg_frustration = conn.execute(
            "SELECT AVG(frustration) AS a FROM messages"
        ).fetchone()["a"]
        # Get users who accepted terms
        terms_accepted_count = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE terms_accepted = 1"
        ).fetchone()["c"]
        return {
            "total_users": total_users,
            "total_interactions": total_interactions,
            "top_intents": {r["intent"]: r["c"] for r in intent_rows},
            "sentiment_distribution": {r["sentiment_label"]: r["c"] for r in sentiment_rows},
            "avg_frustration": round(avg_frustration, 3) if avg_frustration else 0,
            "avg_interactions_per_user": round(total_interactions / total_users, 1) if total_users else 0,
            "terms_accepted_count": terms_accepted_count,
        }

def delete_user_data(user_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM feedback WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM failed_solutions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM documents WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_memory WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM adaptation_profiles WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM adaptation_strategy_stats WHERE user_id = ?", (user_id,))

# ─── Cross-session user memory (Claude-style persistent memory) ───────────────
def get_user_memory(user_id: str) -> dict:
    """Returns {memory_text, message_count_at_update}. Empty defaults if none yet."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT memory_text, message_count_at_update FROM user_memory WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if not row:
            return {"memory_text": "", "message_count_at_update": 0}
        return {"memory_text": row["memory_text"] or "", "message_count_at_update": row["message_count_at_update"] or 0}

def set_user_memory(user_id: str, memory_text: str, message_count_at_update: int) -> None:
    with get_conn() as conn:
        existing = conn.execute("SELECT user_id FROM user_memory WHERE user_id = ?", (user_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE user_memory SET memory_text = ?, updated_at = ?, message_count_at_update = ? WHERE user_id = ?",
                (memory_text, _now(), message_count_at_update, user_id)
            )
        else:
            conn.execute(
                "INSERT INTO user_memory (user_id, memory_text, updated_at, message_count_at_update) "
                "VALUES (?, ?, ?, ?)",
                (user_id, memory_text, _now(), message_count_at_update)
            )

def clear_user_memory(user_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM user_memory WHERE user_id = ?", (user_id,))

def count_all_user_messages(user_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["c"] if row else 0

# ─── Reviews ────────────────────────────────────────────────────────────────
def create_review(review_id: str, reviewer_name: str, reviewer_title: str | None,
                   rating: int, review_text: str, image_path: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reviews (review_id, reviewer_name, reviewer_title, rating, "
            "review_text, image_path, status, featured, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?)",
            (review_id, reviewer_name, reviewer_title, rating, review_text, image_path, _now())
        )

def get_public_reviews(limit: int = 50) -> list[dict]:
    """Approved reviews only, featured first, newest first — what the landing page shows."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reviews WHERE status = 'approved' "
            "ORDER BY featured DESC, created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_all_reviews() -> list[dict]:
    """Every review regardless of status — admin only."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reviews ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

def get_review(review_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE review_id = ?", (review_id,)).fetchone()
        return dict(row) if row else None

def update_review_status(review_id: str, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE reviews SET status = ? WHERE review_id = ?", (status, review_id))

def set_review_featured(review_id: str, featured: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE reviews SET featured = ? WHERE review_id = ?", (1 if featured else 0, review_id))

def delete_review(review_id: str) -> dict | None:
    """Deletes the review and returns its row (so the caller can clean up the image file)."""
    review = get_review(review_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM reviews WHERE review_id = ?", (review_id,))
    return review


# ─── Adaptation Engine Persistence ──────────────────────────────────────────

def get_adaptation_profile(user_id: str) -> dict | None:
    """Retrieve adaptation profile for user_id. Returns dict with parsed profile_json, or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, profile_json, updated_at, interaction_count, adapted_response_count FROM adaptation_profiles WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if not row:
            return None
        try:
            profile_data = json.loads(row["profile_json"])
        except Exception:
            profile_data = {}
        row_keys = row.keys() if hasattr(row, "keys") else []
        adapted_count = row["adapted_response_count"] if "adapted_response_count" in row_keys else 0
        return {
            "user_id": row["user_id"],
            "profile": profile_data,
            "updated_at": row["updated_at"],
            "interaction_count": row["interaction_count"],
            "adapted_response_count": adapted_count,
        }


def set_adaptation_profile(
    user_id: str,
    profile: dict,
    interaction_count: int | None = None,
    adapted_response_count: int | None = None,
) -> None:
    """Persist or update adaptation profile JSON for user_id."""
    now = _now()
    profile_json = json.dumps(profile)
    with get_conn() as conn:
        if interaction_count is not None and adapted_response_count is not None:
            conn.execute(
                """
                INSERT INTO adaptation_profiles (user_id, profile_json, updated_at, interaction_count, adapted_response_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at,
                    interaction_count = excluded.interaction_count,
                    adapted_response_count = excluded.adapted_response_count
                """,
                (user_id, profile_json, now, interaction_count, adapted_response_count)
            )
        elif interaction_count is not None:
            conn.execute(
                """
                INSERT INTO adaptation_profiles (user_id, profile_json, updated_at, interaction_count, adapted_response_count)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at,
                    interaction_count = excluded.interaction_count
                """,
                (user_id, profile_json, now, interaction_count)
            )
        else:
            conn.execute(
                """
                INSERT INTO adaptation_profiles (user_id, profile_json, updated_at, interaction_count, adapted_response_count)
                VALUES (?, ?, ?, 0, 0)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, profile_json, now)
            )


def clear_adaptation_profile(user_id: str) -> bool:
    """Clear learned adaptation profile and strategy stats for user_id without touching messages or factual memory."""
    with get_conn() as conn:
        c1 = conn.execute("DELETE FROM adaptation_profiles WHERE user_id = ?", (user_id,)).rowcount
        conn.execute("DELETE FROM adaptation_strategy_stats WHERE user_id = ?", (user_id,))
        return c1 > 0


def increment_adaptation_interaction_count(user_id: str, adapted_used: bool = False) -> int:
    """Increment interaction count for user's adaptation profile, and adapted_response_count if adapted_used is True."""
    now = _now()
    adapted_delta = 1 if adapted_used else 0
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO adaptation_profiles (user_id, profile_json, updated_at, interaction_count, adapted_response_count)
            VALUES (?, '{}', ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                interaction_count = adaptation_profiles.interaction_count + 1,
                adapted_response_count = adaptation_profiles.adapted_response_count + ?,
                updated_at = excluded.updated_at
            """,
            (user_id, now, adapted_delta, adapted_delta)
        )
        row = conn.execute("SELECT interaction_count FROM adaptation_profiles WHERE user_id = ?", (user_id,)).fetchone()
        return row["interaction_count"] if row else 1


def record_strategy_feedback(user_id: str, strategy: str, helpful: bool, timestamp: str | None = None) -> None:
    """Track successes, failures, and timestamps for behavioral response strategies."""
    now = timestamp or _now()
    with get_conn() as conn:
        if helpful:
            conn.execute(
                """
                INSERT INTO adaptation_strategy_stats (user_id, strategy, successes, failures, last_updated, last_success_at)
                VALUES (?, ?, 1, 0, ?, ?)
                ON CONFLICT(user_id, strategy) DO UPDATE SET
                    successes = adaptation_strategy_stats.successes + 1,
                    last_updated = excluded.last_updated,
                    last_success_at = excluded.last_success_at
                """,
                (user_id, strategy, now, now)
            )
        else:
            conn.execute(
                """
                INSERT INTO adaptation_strategy_stats (user_id, strategy, successes, failures, last_updated, last_failure_at)
                VALUES (?, ?, 0, 1, ?, ?)
                ON CONFLICT(user_id, strategy) DO UPDATE SET
                    failures = adaptation_strategy_stats.failures + 1,
                    last_updated = excluded.last_updated,
                    last_failure_at = excluded.last_failure_at
                """,
                (user_id, strategy, now, now)
            )


def get_strategy_stats(user_id: str) -> dict[str, dict]:
    """Return all strategy statistics with timestamps for user_id."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT strategy, successes, failures, last_updated, last_success_at, last_failure_at
            FROM adaptation_strategy_stats WHERE user_id = ?
            """,
            (user_id,)
        ).fetchall()
        return {
            row["strategy"]: {
                "successes": row["successes"],
                "failures": row["failures"],
                "last_updated": row["last_updated"],
                "last_success_at": row["last_success_at"],
                "last_failure_at": row["last_failure_at"],
            }
            for row in rows
        }


def get_user_feedback_stats(user_id: str) -> dict:
    """Return total feedback count and positive feedback count for user_id."""
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM feedback WHERE user_id = ?", (user_id,)).fetchone()["c"]
        positive = conn.execute("SELECT COUNT(*) AS c FROM feedback WHERE user_id = ? AND helpful = 1", (user_id,)).fetchone()["c"]
        return {
            "total_feedback": total,
            "positive_feedback": positive,
            "negative_feedback": total - positive,
            "positive_rate": round(positive / total, 3) if total > 0 else 0.0,
        }