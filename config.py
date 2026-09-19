"""
config.py — Centralized configuration and validation layer for Ava AI.
Pulls settings from environment variables with safe defaults and zero circular dependencies.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Environment Mode
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Security & Session Secrets
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if ENVIRONMENT == "production":
        SECRET_KEY = ""
    else:
        SECRET_KEY = "dev_insecure_secret_key_change_in_production"

# CORS Configuration
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
    if origin.strip()
]

# Database Persistence Path
if os.getenv("DB_PATH"):
    DB_PATH = os.getenv("DB_PATH")
elif ENVIRONMENT == "production":
    DB_PATH = "/app/data/neurosupport.db"
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neurosupport.db")

# Upload & Review Storage Paths
if os.getenv("UPLOAD_DIR"):
    UPLOAD_DIR = os.getenv("UPLOAD_DIR")
elif ENVIRONMENT == "production":
    UPLOAD_DIR = "/app/data/uploads"
else:
    UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

if os.getenv("REVIEW_IMAGE_DIR"):
    REVIEW_IMAGE_DIR = os.getenv("REVIEW_IMAGE_DIR")
elif ENVIRONMENT == "production":
    REVIEW_IMAGE_DIR = "/app/data/review_images"
else:
    REVIEW_IMAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review_images")

# Admin Portal
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Execution Safety
ENABLE_CODE_EXECUTION = (
    os.getenv("ENABLE_CODE_EXECUTION", "false").lower() in ("true", "1")
    if ENVIRONMENT == "production"
    else os.getenv("ENABLE_CODE_EXECUTION", "true").lower() in ("true", "1")
)

# LLM Inference
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Optional Integrations
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")
REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY", "")

# Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")


def ensure_directories() -> None:
    """Create persistent storage directories if they do not exist."""
    db_dir = os.path.dirname(os.path.abspath(DB_PATH)) or "."
    try:
        os.makedirs(db_dir, exist_ok=True)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(REVIEW_IMAGE_DIR, exist_ok=True)
    except OSError:
        pass


def validate_config() -> dict:
    """
    Validate production configuration readiness.
    Returns dict: {"valid": bool, "errors": list[str]}
    """
    errors = []

    if ENVIRONMENT == "production":
        if not SECRET_KEY:
            errors.append("SECRET_KEY must be configured in production environment")
        if "*" in ALLOWED_ORIGINS:
            errors.append("ALLOWED_ORIGINS must not contain wildcard '*' in production")

    # Verify DB parent directory writability
    db_dir = os.path.dirname(os.path.abspath(DB_PATH)) or "."
    try:
        os.makedirs(db_dir, exist_ok=True)
        test_file = os.path.join(db_dir, ".write_test_tmp")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
    except Exception as e:
        errors.append(f"DB_PATH directory '{db_dir}' is not writable: {e}")

    # Verify storage directories
    for name, p in [("UPLOAD_DIR", UPLOAD_DIR), ("REVIEW_IMAGE_DIR", REVIEW_IMAGE_DIR)]:
        try:
            os.makedirs(p, exist_ok=True)
            test_file = os.path.join(p, ".write_test_tmp")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
        except Exception as e:
            errors.append(f"{name} directory '{p}' is not writable: {e}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "environment": ENVIRONMENT,
    }
