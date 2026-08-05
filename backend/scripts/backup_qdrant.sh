#!/bin/bash
set -e

# Load environment variables if .env exists in parent directory
if [ -f ../.env ]; then
    export $(grep -v '^#' ../.env | xargs)
elif [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

QDRANT_HOST=${QDRANT_HOST:-localhost}
QDRANT_PORT=${QDRANT_PORT:-6333}
COLLECTION_NAME=${VECTOR_COLLECTION_NAME:-documents}
BACKUP_DIR=${BACKUP_DIR:-./data/backups}

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "Triggering Qdrant snapshot creation for collection '$COLLECTION_NAME'..."
SNAPSHOT_RESPONSE=$(curl -s -X POST "http://$QDRANT_HOST:$QDRANT_PORT/collections/$COLLECTION_NAME/snapshots")

# Extract the snapshot filename from the JSON response
SNAPSHOT_NAME=$(echo "$SNAPSHOT_RESPONSE" | grep -o '"name":"[^"]*' | grep -o '[^"]*$' | head -n 1)

if [ -z "$SNAPSHOT_NAME" ]; then
    echo "Error: Failed to retrieve snapshot name from Qdrant response: $SNAPSHOT_RESPONSE"
    exit 1
fi

echo "Downloading snapshot '$SNAPSHOT_NAME'..."
curl -s -o "$BACKUP_DIR/qdrant_${COLLECTION_NAME}_${TIMESTAMP}.snapshot" \
  "http://$QDRANT_HOST:$QDRANT_PORT/collections/$COLLECTION_NAME/snapshots/$SNAPSHOT_NAME"

echo "Snapshot saved to $BACKUP_DIR/qdrant_${COLLECTION_NAME}_${TIMESTAMP}.snapshot"

# Clean up snapshot on server to save disk space
curl -s -X DELETE "http://$QDRANT_HOST:$QDRANT_PORT/collections/$COLLECTION_NAME/snapshots/$SNAPSHOT_NAME" > /dev/null
echo "Server snapshot cleaned up."
