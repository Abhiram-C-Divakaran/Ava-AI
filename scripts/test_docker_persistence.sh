#!/usr/bin/env bash
# ==============================================================================
# scripts/test_docker_persistence.sh — Docker Volume & Data Persistence Verification
#
# Validates:
# 1. SQLite database is created in /app/data/neurosupport.db (NOT /app/neurosupport.db).
# 2. User accounts survive container stop, removal, and recreation using the same volume.
# 3. Upload and review image directories survive container recreation.
# 4. Database PRAGMA integrity_check remains ok.
# ==============================================================================

set -euo pipefail

IMAGE_NAME="${1:-ava-ai:rc}"
TIMESTAMP=$(date +%s)
VOLUME_NAME="ava_ci_data_test_${TIMESTAMP}"
CONTAINER_NAME_1="ava_persist_node1_${TIMESTAMP}"
CONTAINER_NAME_2="ava_persist_node2_${TIMESTAMP}"
HOST_PORT=8000
TEST_EMAIL="persist_${TIMESTAMP}@example.com"
TEST_PASSWORD="PersistencePassword123!"
COOKIE_JAR="/tmp/persist_cookies_${TIMESTAMP}.txt"

echo "======================================================================"
echo "  Ava AI — Docker Persistence & Volume Recreation Verification"
echo "  Image: $IMAGE_NAME"
echo "  Volume: $VOLUME_NAME"
echo "======================================================================"

cleanup() {
    echo "[*] Cleaning up test containers and volume..."
    docker rm -f "$CONTAINER_NAME_1" "$CONTAINER_NAME_2" 2>/dev/null || true
    docker volume rm -f "$VOLUME_NAME" 2>/dev/null || true
    rm -f "$COOKIE_JAR" 2>/dev/null || true
}
trap cleanup EXIT

echo "[1/8] Creating persistent Docker volume '$VOLUME_NAME'..."
docker volume create "$VOLUME_NAME"

echo "[2/8] Starting Initial Container ($CONTAINER_NAME_1)..."
docker run -d \
  --name "$CONTAINER_NAME_1" \
  -p "$HOST_PORT:8000" \
  -e ENVIRONMENT=production \
  -e SESSION_HTTPS_ONLY=false \
  -e SECRET_KEY="ci_testing_secret_key_that_is_at_least_32_bytes_long" \
  -e ALLOWED_ORIGINS="http://localhost:8000,http://127.0.0.1:8000" \
  -e GROQ_API_KEY="dummy_key_ci" \
  -e ENABLE_CODE_EXECUTION=false \
  -e DB_PATH="/app/data/neurosupport.db" \
  -e UPLOAD_DIR="/app/data/uploads" \
  -e REVIEW_IMAGE_DIR="/app/data/review_images" \
  -v "$VOLUME_NAME:/app/data" \
  "$IMAGE_NAME"

echo "[3/8] Waiting for Container 1 readiness..."
for i in {1..30}; do
    if curl -fs "http://127.0.0.1:$HOST_PORT/ready" >/dev/null 2>&1; then
        echo "  Container 1 ready after ${i}s"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[-] ERROR: Container 1 failed to become ready."
        docker logs "$CONTAINER_NAME_1"
        exit 1
    fi
    sleep 1
done

echo "[4/8] Verifying Database Location..."
if ! docker exec "$CONTAINER_NAME_1" test -f /app/data/neurosupport.db; then
    echo "[-] ERROR: Database not found at /app/data/neurosupport.db!"
    exit 1
fi
if docker exec "$CONTAINER_NAME_1" test -f /app/neurosupport.db; then
    echo "[-] ERROR: Database was created at /app/neurosupport.db instead of /app/data/neurosupport.db!"
    exit 1
fi
echo "  [PASS] Database correctly located at /app/data/neurosupport.db (not in /app root)"

echo "[5/8] Seeding User Data and Storage Files in Container 1..."
SIGNUP_RESP=$(curl -fs -X POST "http://127.0.0.1:$HOST_PORT/api/auth/signup" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Persist User\",\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")

if [[ "$SIGNUP_RESP" != *"user_id"* ]]; then
    echo "[-] ERROR: User registration failed: $SIGNUP_RESP"
    exit 1
fi
echo "  [PASS] Test user registered successfully"

# Create test files in uploads and review_images
docker exec "$CONTAINER_NAME_1" sh -c "echo 'upload_persistence_content' > /app/data/uploads/test_upload.txt"
docker exec "$CONTAINER_NAME_1" sh -c "echo 'review_persistence_content' > /app/data/review_images/test_review.txt"
echo "  [PASS] Test files written to /app/data/uploads and /app/data/review_images"

echo "[6/8] Stopping and Removing Container 1 (Simulating crash / replacement)..."
docker stop "$CONTAINER_NAME_1"
docker rm "$CONTAINER_NAME_1"

echo "[7/8] Starting Recreated Container 2 ($CONTAINER_NAME_2) with the SAME volume..."
docker run -d \
  --name "$CONTAINER_NAME_2" \
  -p "$HOST_PORT:8000" \
  -e ENVIRONMENT=production \
  -e SESSION_HTTPS_ONLY=false \
  -e SECRET_KEY="ci_testing_secret_key_that_is_at_least_32_bytes_long" \
  -e ALLOWED_ORIGINS="http://localhost:8000,http://127.0.0.1:8000" \
  -e GROQ_API_KEY="dummy_key_ci" \
  -e ENABLE_CODE_EXECUTION=false \
  -e DB_PATH="/app/data/neurosupport.db" \
  -e UPLOAD_DIR="/app/data/uploads" \
  -e REVIEW_IMAGE_DIR="/app/data/review_images" \
  -v "$VOLUME_NAME:/app/data" \
  "$IMAGE_NAME"

echo "  Waiting for Container 2 readiness..."
for i in {1..30}; do
    if curl -fs "http://127.0.0.1:$HOST_PORT/ready" >/dev/null 2>&1; then
        echo "  Container 2 ready after ${i}s"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[-] ERROR: Container 2 failed to become ready."
        docker logs "$CONTAINER_NAME_2"
        exit 1
    fi
    sleep 1
done

echo "[8/8] Verifying Data Persistence in Recreated Container..."
# 1. Login with previous user credentials
LOGIN_RESP=$(curl -fs -c "$COOKIE_JAR" -X POST "http://127.0.0.1:$HOST_PORT/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")

if [[ "$LOGIN_RESP" != *"user_id"* ]]; then
    echo "[-] ERROR: User login failed in recreated container! Data was lost across restart."
    exit 1
fi
echo "  [PASS] User successfully logged into recreated container (User record persisted!)"

# 2. Verify files in /app/data/uploads and /app/data/review_images
UPLOAD_CONTENT=$(docker exec "$CONTAINER_NAME_2" cat /app/data/uploads/test_upload.txt)
if [[ "$UPLOAD_CONTENT" != "upload_persistence_content" ]]; then
    echo "[-] ERROR: /app/data/uploads/test_upload.txt lost or content mismatch!"
    exit 1
fi
echo "  [PASS] /app/data/uploads persisted successfully across container recreation"

REVIEW_CONTENT=$(docker exec "$CONTAINER_NAME_2" cat /app/data/review_images/test_review.txt)
if [[ "$REVIEW_CONTENT" != "review_persistence_content" ]]; then
    echo "[-] ERROR: /app/data/review_images/test_review.txt lost or content mismatch!"
    exit 1
fi
echo "  [PASS] /app/data/review_images persisted successfully across container recreation"

# 3. Database PRAGMA integrity check
INTEGRITY=$(docker exec "$CONTAINER_NAME_2" python -c "import database as db; print(db.check_database_integrity())")
if [[ "$INTEGRITY" != *"ok"* ]]; then
    echo "[-] ERROR: Database integrity compromised: $INTEGRITY"
    exit 1
fi
echo "  [PASS] Restored database PRAGMA integrity_check: ok"

echo ""
echo "======================================================================"
echo "  [SUCCESS] All Docker Persistence & Recreation Checks PASSED!"
echo "======================================================================"
