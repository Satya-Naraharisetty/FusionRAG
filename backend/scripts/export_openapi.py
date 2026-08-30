"""
Export the FastAPI OpenAPI JSON specification to docs/api/openapi.json.
"""

import json
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Minimal fallback environments for app module import
os.environ.setdefault("JWT_SECRET", "0" * 64)
os.environ.setdefault("ENCRYPTION_MASTER_KEY", "0" * 64)
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "postgres")
os.environ.setdefault("POSTGRES_DB", "hybrid_rag")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("QDRANT_HOST", "localhost")

from app.main import app  # noqa: E402


def export_openapi():
    spec = app.openapi()
    workspace_root = backend_dir.parent
    out_file = workspace_root / "docs" / "api" / "openapi.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    print(
        f"Successfully exported OpenAPI schema ({len(spec.get('paths', {}))} paths) to {out_file}"
    )


if __name__ == "__main__":
    export_openapi()
