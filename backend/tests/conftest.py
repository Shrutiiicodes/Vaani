"""Test environment. Runs before any backend module is imported, so these win over .env."""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256"
os.environ["STAFF_USERNAME"] = "admin"
os.environ["STAFF_PASSWORD"] = "admin-password"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ.setdefault("GROQ_API_KEY", "test-key")
