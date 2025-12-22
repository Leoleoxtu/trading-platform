#!/bin/bash
set -e

echo "Waiting for MinIO to be ready..."

# Configure mc client
mc alias set local http://minio:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}

# Wait for MinIO to be available
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  if mc admin info local &>/dev/null; then
    echo "MinIO is ready!"
    break
  fi
  echo "Waiting for MinIO... (attempt $((RETRY_COUNT+1))/$MAX_RETRIES)"
  RETRY_COUNT=$((RETRY_COUNT+1))
  sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
  echo "ERROR: MinIO did not become ready in time"
  exit 1
fi

# Function to create bucket idempotently
create_bucket() {
  local bucket_name=$1
  
  if mc ls local | grep -q "${bucket_name}"; then
    echo "Bucket '${bucket_name}' already exists - skipping"
  else
    echo "Creating bucket '${bucket_name}'..."
    mc mb local/${bucket_name}
    echo "Bucket '${bucket_name}' created successfully"
  fi
}

# Create all required buckets
echo "Starting bucket creation..."

create_bucket "raw-events"
create_bucket "pipeline-artifacts"

echo "All buckets initialized successfully!"

# List all buckets for verification
echo "Current buckets:"
mc ls local
