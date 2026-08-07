import os
import sys

# Add backend directory to system path to resolve app.* imports at runtime in Vercel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: F401
