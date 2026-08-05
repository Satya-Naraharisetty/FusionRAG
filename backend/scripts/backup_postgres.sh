#!/bin/bash
set -e

# Load environment variables if .env exists in parent directory
if [ -f ../.env ]; then
    export $(grep -v '^#' ../.env | xargs)
elif [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DB_USER=${POSTGRES_USER:-postgres}
DB_NAME=${POSTGRES_DB:-hybrid_rag}
DB_HOST=${POSTGRES_SERVER:-localhost}
DB_PORT=${POSTGRES_PORT:-5432}
BACKUP_DIR=${BACKUP_DIR:-./data/backups}

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/postgres_${DB_NAME}_${TIMESTAMP}.dump"

echo "Starting PostgreSQL backup of '$DB_NAME'..."

# Set PGPASSWORD so pg_dump runs non-interactively
export PGPASSWORD=${POSTGRES_PASSWORD:-postgres_secure_password_123}

# Perform backup using pg_dump Custom format
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -F c -b -v -f "$BACKUP_FILE" "$DB_NAME"

echo "Backup completed successfully: $BACKUP_FILE"
