#!/bin/bash
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <path_to_snapshot_file>"
    exit 1
fi

SNAPSHOT_FILE=$1

# Load environment variables if .env exists in parent directory
if [ -f ../.env ]; then
    export $(grep -v '^#' ../.env | xargs)
elif [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

QDRANT_HOST=${QDRANT_HOST:-localhost}
QDRANT_PORT=${QDRANT_PORT:-6333}
COLLECTION_NAME=${VECTOR_COLLECTION_NAME:-documents}

echo "Restoring Qdrant collection '$COLLECTION_NAME' from snapshot '$SNAPSHOT_FILE'..."

# Recover collection from local snapshot file via REST API multipart POST
curl -s -X POST -H "Content-Type: multipart/form-data" \
  -F "snapshot=@$SNAPSHOT_FILE" \
  "http://$QDRANT_HOST:$QDRANT_PORT/collections/$COLLECTION_NAME/snapshots/recover"

echo "Restore completed successfully."
