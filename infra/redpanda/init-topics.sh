#!/bin/bash
set -e

echo "Waiting for Redpanda to be ready..."

# Wait for Redpanda to be available
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  if rpk cluster info --brokers redpanda:29092 &>/dev/null; then
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
  
  # Use word boundary to match exact topic name (not substring)
  if rpk topic list --brokers redpanda:29092 | grep -q "^${topic_name}[[:space:]]"; then
    echo "Topic '${topic_name}' already exists - skipping"
  else
    echo "Creating topic '${topic_name}' with ${partitions} partitions..."
    if rpk topic create "${topic_name}" --partitions "${partitions}" --brokers redpanda:29092 2>&1 | grep -q "TOPIC_ALREADY_EXISTS"; then
      echo "Topic '${topic_name}' already exists (created concurrently) - skipping"
    else
      echo "Topic '${topic_name}' created successfully"
    fi
  fi
}

# Create all required topics
echo "Starting topic creation..."

# Stage 0: Raw events
create_topic "raw.events.v1" 6
create_topic "raw.events.dlq.v1" 1

# Stage 0.5: Normalized events
create_topic "events.normalized.v1" 6
create_topic "events.normalized.dlq.v1" 1

# Stage 1: Triage buckets
create_topic "events.stage1.fast.v1" 6
create_topic "events.stage1.standard.v1" 6
create_topic "events.stage1.cold.v1" 6
create_topic "events.stage1.dropped.v1" 1
create_topic "events.stage1.dlq.v1" 1

# Stage 2: Triage NLP (with sentiment + entities)
create_topic "events.triaged.v1" 6
create_topic "events.triaged.dlq.v1" 1

# Stage 3: Enrichment (future)
create_topic "events.enriched.v1" 6
create_topic "events.enriched.dlq.v1" 1

# Stage 4: Final signals and orchestration (future)
create_topic "newscards.v1" 5
create_topic "signals.final.v1" 3

echo "All topics initialized successfully!"

# List all topics for verification
echo "Current topics:"
rpk topic list --brokers redpanda:29092
