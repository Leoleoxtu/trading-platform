#!/bin/bash
# Script to validate Kafka (Redpanda) setup
# Tests topic creation, producer, and consumer functionality

set -e

echo "=========================================="
echo "  Kafka/Redpanda Validation Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BROKER="localhost:9092"
TEST_TOPIC="test.validation.v1"
TEST_MESSAGE="Hello from validation script at $(date +%s)"

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
    else
        echo -e "${RED}✗${NC} $2"
        exit 1
    fi
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# 1. Check if Redpanda is accessible
echo "1. Checking Redpanda connectivity..."
if docker compose -f infra/docker-compose.yml exec redpanda rpk cluster info --brokers redpanda:29092 &>/dev/null; then
    print_status 0 "Redpanda is accessible"
else
    print_status 1 "Redpanda is NOT accessible"
fi
echo ""

# 2. List existing topics
echo "2. Listing existing topics..."
docker compose -f infra/docker-compose.yml exec redpanda rpk topic list --brokers redpanda:29092
echo ""

# 3. Create test topic
echo "3. Creating test topic '${TEST_TOPIC}'..."
docker compose -f infra/docker-compose.yml exec redpanda rpk topic create "${TEST_TOPIC}" --partitions 3 --brokers redpanda:29092 2>&1 | grep -q "TOPIC_ALREADY_EXISTS\|created successfully" && \
    print_status 0 "Test topic created or already exists" || \
    print_status 1 "Failed to create test topic"
echo ""

# 4. Produce test message
echo "4. Producing test message..."
echo "${TEST_MESSAGE}" | docker compose -f infra/docker-compose.yml exec -T redpanda rpk topic produce "${TEST_TOPIC}" --brokers redpanda:29092 &>/dev/null && \
    print_status 0 "Message produced successfully" || \
    print_status 1 "Failed to produce message"
echo ""

# 5. Consume test message
echo "5. Consuming test message..."
CONSUMED_MSG=$(docker compose -f infra/docker-compose.yml exec redpanda rpk topic consume "${TEST_TOPIC}" --num 1 --offset start --brokers redpanda:29092 2>/dev/null | grep -o "Hello from validation script")
if [ ! -z "$CONSUMED_MSG" ]; then
    print_status 0 "Message consumed successfully"
    print_info "Message content: ${CONSUMED_MSG}..."
else
    print_status 1 "Failed to consume message"
fi
echo ""

# 6. Verify required topics exist
echo "6. Verifying required production topics..."
REQUIRED_TOPICS=(
    "raw.events.v1"
    "events.normalized.v1"
    "events.enriched.v1"
)

for topic in "${REQUIRED_TOPICS[@]}"; do
    if docker compose -f infra/docker-compose.yml exec redpanda rpk topic list --brokers redpanda:29092 | grep -q "^${topic}"; then
        print_status 0 "Topic '${topic}' exists"
    else
        echo -e "${RED}✗${NC} Topic '${topic}' is MISSING"
    fi
done
echo ""

# 7. Show topic details
echo "7. Topic statistics..."
docker compose -f infra/docker-compose.yml exec redpanda rpk topic describe "${TEST_TOPIC}" --brokers redpanda:29092 2>/dev/null || true
echo ""

# 8. Cleanup (optional)
read -p "Delete test topic '${TEST_TOPIC}'? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose -f infra/docker-compose.yml exec redpanda rpk topic delete "${TEST_TOPIC}" --brokers redpanda:29092 &>/dev/null && \
        print_status 0 "Test topic deleted" || \
        echo -e "${YELLOW}⚠${NC} Could not delete test topic (may not exist)"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✓ Kafka validation completed successfully!${NC}"
echo "=========================================="
