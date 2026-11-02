import os
import sys

# In serverless environments outside /tmp, the filesystem is read-only.
# Ensure fallback SQLite writes to /tmp if Supabase is not configured.
if "RU_READER_DB" not in os.environ and not os.getenv("SUPABASE_URL"):
    os.environ["RU_READER_DB"] = "/tmp/ru_reader.db"

# Ensure backend directory is in sys.path
backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from main import app

