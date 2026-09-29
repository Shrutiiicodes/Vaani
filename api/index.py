import os
import sys

# Add backend directory to system path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from main import app  # noqa: F401  (Vercel looks for `app`)
