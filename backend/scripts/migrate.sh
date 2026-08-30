#!/usr/bin/env sh
# Runs Alembic migrations for the Fusion RAG backend.
#
# Usage:
#   ./scripts/migrate.sh          # upgrade to the latest revision
#   ./scripts/migrate.sh -1       # downgrade one revision
set -e

cd "$(dirname "$0")/.."

python -m alembic upgrade "$@"
