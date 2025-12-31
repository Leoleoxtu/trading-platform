#!/bin/bash
# Script to validate Redis setup
# Tests connection, set/get operations, and configuration

set -e

echo "=========================================="
echo "  Redis Validation Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
TEST_KEY="test:validation:$(date +%s)"
TEST_VALUE="Hello Redis at $(date)"

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

# 1. Check if Redis is accessible
echo "1. Checking Redis connectivity..."
if docker compose -f infra/docker-compose.yml exec redis redis-cli ping | grep -q "PONG"; then
    print_status 0 "Redis is accessible"
else
    print_status 1 "Redis is NOT accessible"
fi
echo ""

# 2. Get Redis info
echo "2. Redis server info..."
docker compose -f infra/docker-compose.yml exec redis redis-cli INFO server | grep -E "redis_version|os|uptime_in_seconds" || true
echo ""

# 3. Test SET operation
echo "3. Testing SET operation..."
docker compose -f infra/docker-compose.yml exec redis redis-cli SET "${TEST_KEY}" "${TEST_VALUE}" | grep -q "OK" && \
    print_status 0 "SET operation successful" || \
    print_status 1 "SET operation failed"
echo ""

# 4. Test GET operation
echo "4. Testing GET operation..."
RETRIEVED_VALUE=$(docker compose -f infra/docker-compose.yml exec redis redis-cli GET "${TEST_KEY}" | tr -d '\r')
if [ "$RETRIEVED_VALUE" == "$TEST_VALUE" ]; then
    print_status 0 "GET operation successful - value matches"
    print_info "Retrieved: ${RETRIEVED_VALUE}"
else
    print_status 1 "GET operation failed - value mismatch"
fi
echo ""

# 5. Test DEL operation
echo "5. Testing DEL operation..."
docker compose -f infra/docker-compose.yml exec redis redis-cli DEL "${TEST_KEY}" | grep -q "1" && \
    print_status 0 "DEL operation successful" || \
    print_status 1 "DEL operation failed"
echo ""

# 6. Check maxmemory policy
echo "6. Checking maxmemory policy..."
MAXMEMORY_POLICY=$(docker compose -f infra/docker-compose.yml exec redis redis-cli CONFIG GET maxmemory-policy | tail -n 1 | tr -d '\r')
print_info "Current maxmemory-policy: ${MAXMEMORY_POLICY}"
if [ "$MAXMEMORY_POLICY" == "allkeys-lru" ]; then
    print_status 0 "Maxmemory policy is correctly set to allkeys-lru"
else
    echo -e "${YELLOW}⚠${NC} Maxmemory policy is '${MAXMEMORY_POLICY}' (recommended: allkeys-lru)"
fi
echo ""

# 7. Check memory usage
echo "7. Memory usage..."
docker compose -f infra/docker-compose.yml exec redis redis-cli INFO memory | grep -E "used_memory_human|maxmemory_human|mem_fragmentation_ratio" || true
echo ""

# 8. Test Hash operations
echo "8. Testing Hash operations..."
HASH_KEY="test:hash:$(date +%s)"
docker compose -f infra/docker-compose.yml exec redis redis-cli HSET "${HASH_KEY}" field1 "value1" field2 "value2" &>/dev/null && \
    print_status 0 "HSET operation successful" || \
    print_status 1 "HSET operation failed"

HASH_VALUE=$(docker compose -f infra/docker-compose.yml exec redis redis-cli HGET "${HASH_KEY}" field1 | tr -d '\r')
if [ "$HASH_VALUE" == "value1" ]; then
    print_status 0 "HGET operation successful"
else
    print_status 1 "HGET operation failed"
fi

docker compose -f infra/docker-compose.yml exec redis redis-cli DEL "${HASH_KEY}" &>/dev/null
echo ""

# 9. Test List operations
echo "9. Testing List operations..."
LIST_KEY="test:list:$(date +%s)"
docker compose -f infra/docker-compose.yml exec redis redis-cli LPUSH "${LIST_KEY}" "item1" "item2" "item3" &>/dev/null && \
    print_status 0 "LPUSH operation successful" || \
    print_status 1 "LPUSH operation failed"

LIST_LEN=$(docker compose -f infra/docker-compose.yml exec redis redis-cli LLEN "${LIST_KEY}" | tr -d '\r')
if [ "$LIST_LEN" == "3" ]; then
    print_status 0 "LLEN operation successful (length: ${LIST_LEN})"
else
    print_status 1 "LLEN operation failed"
fi

docker compose -f infra/docker-compose.yml exec redis redis-cli DEL "${LIST_KEY}" &>/dev/null
echo ""

# 10. Check persistence configuration
echo "10. Persistence configuration..."
docker compose -f infra/docker-compose.yml exec redis redis-cli CONFIG GET save | tail -n 1 | tr -d '\r'
docker compose -f infra/docker-compose.yml exec redis redis-cli CONFIG GET appendonly | tail -n 1 | tr -d '\r'
echo ""

echo "=========================================="
echo -e "${GREEN}✓ Redis validation completed successfully!${NC}"
echo "=========================================="
