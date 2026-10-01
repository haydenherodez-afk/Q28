import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="hericr-test-")
# HERICR_TEST_DATABASE_URL=postgresql+psycopg://... požene teste na PostgreSQL (kot v produkciji)
os.environ["HERICR_DATABASE_URL"] = os.environ.get("HERICR_TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["HERICR_STORAGE_DIR"] = f"{_tmp}/files"
os.environ["HERICR_SCHEDULER_ENABLED"] = "false"
os.environ["HERICR_ANTHROPIC_API_KEY"] = ""
os.environ["HERICR_SECRET_KEY"] = "test-secret-key-that-is-long-enough-123456"
