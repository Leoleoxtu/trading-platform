#!/bin/bash
set -e

echo "Waiting for Redpanda to be ready..."

# Wait for Redpanda to be available
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  if rpk cluster info --brokers localhost:9092 &>/dev/null; then
    echo "Redpanda is ready!"
    break
  fi
  echo "Waiting for Redpanda... (attempt $((RETRY_COUNT+1))/$MAX_RETRIES)"
  RETRY_COUNT=$((RETRY_COUNT+1))
  sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
  echo "ERROR: Redpanda did not become ready in time"
  exit 1
fi

# Function to create topic idempotently
create_topic() {
  local topic_name=$1
  local partitions=$2
  
  if rpk topic list --brokers localhost:9092 | grep -q "^${topic_name}$"; then
    echo "Topic '${topic_name}' already exists - skipping"
  else
    echo "Creating topic '${topic_name}' with ${partitions} partitions..."
    rpk topic create "${topic_name}" --partitions "${partitions}" --brokers localhost:9092
    echo "Topic '${topic_name}' created successfully"
  fi
}

# Create all required topics
echo "Starting topic creation..."

create_topic "raw.events.v1" 6
create_topic "raw.events.dlq.v1" 1
create_topic "events.normalized.v1" 6
create_topic "events.normalized.dlq.v1" 1

echo "All topics initialized successfully!"

# List all topics for verification
echo "Current topics:"
rpk topic list --brokers localhost:9092
