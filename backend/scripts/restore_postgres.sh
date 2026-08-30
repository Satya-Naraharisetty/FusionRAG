#!/bin/bash
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <path_to_backup_dump_file>"
    exit 1
fi

BACKUP_FILE=$1

# Load environment variables if .env exists in parent directory
if [ -f ../.env ]; then
    export $(grep -v '^#' ../.env | xargs)
elif [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DB_USER=${POSTGRES_USER:-postgres}
DB_NAME=${POSTGRES_DB:-fusion_rag}
DB_HOST=${POSTGRES_SERVER:-localhost}
DB_PORT=${POSTGRES_PORT:-5432}

echo "Restoring PostgreSQL backup from '$BACKUP_FILE' into '$DB_NAME'..."

# Set PGPASSWORD so pg_restore runs non-interactively
export PGPASSWORD=${POSTGRES_PASSWORD:-postgres_secure_password_123}

# Perform restore using pg_restore
# Note: we drop and recreate schema objects (clean) or perform direct restore.
pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v "$BACKUP_FILE"

echo "Restore completed successfully."
