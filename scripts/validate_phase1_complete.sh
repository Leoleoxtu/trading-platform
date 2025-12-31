#!/bin/bash
# Master validation script - runs all component validations
# Tests Kafka, MinIO, Redis, PostgreSQL/TimescaleDB, and Prometheus/Grafana

set -e

echo "=========================================="
echo "  PHASE 1 - INFRASTRUCTURE VALIDATION"
echo "  Trading Platform Complete Test Suite"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

print_header() {
    echo ""
    echo -e "${BLUE}=========================================="
    echo -e "  $1"
    echo -e "==========================================${NC}"
    echo ""
}

print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗ FAILED${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
}

# Check if docker compose is running
print_header "0. Checking Docker Compose Services"
if ! docker compose -f infra/docker-compose.yml ps &>/dev/null; then
    echo -e "${RED}✗ Docker Compose is not running${NC}"
    echo "Please start services: cd infra && docker compose up -d"
    exit 1
fi

# Count running services
RUNNING_SERVICES=$(docker compose -f infra/docker-compose.yml ps --format json | jq -r 'select(.State == "running")' | wc -l)
echo -e "${GREEN}✓${NC} Docker Compose is running"
echo "  Running services: ${RUNNING_SERVICES}"
echo ""

# 1. Validate Kafka/Redpanda
print_header "1. Kafka/Redpanda Validation"
if bash scripts/validate_kafka.sh > /tmp/kafka_validation.log 2>&1; then
    print_result 0
else
    print_result 1
    echo "See log: /tmp/kafka_validation.log"
fi

# 2. Validate MinIO
print_header "2. MinIO (S3) Validation"
if bash scripts/validate_minio.sh > /tmp/minio_validation.log 2>&1; then
    print_result 0
else
    print_result 1
    echo "See log: /tmp/minio_validation.log"
fi

# 3. Validate Redis
print_header "3. Redis Validation"
if bash scripts/validate_redis.sh > /tmp/redis_validation.log 2>&1; then
    print_result 0
else
    print_result 1
    echo "See log: /tmp/redis_validation.log"
fi

# 4. Validate PostgreSQL/TimescaleDB
print_header "4. PostgreSQL/TimescaleDB Validation"
if bash scripts/validate_postgres.sh > /tmp/postgres_validation.log 2>&1; then
    print_result 0
else
    print_result 1
    echo "See log: /tmp/postgres_validation.log"
fi

# 5. Check Prometheus
print_header "5. Prometheus Validation"
if curl -s http://localhost:9090/-/healthy | grep -q "Prometheus is Healthy"; then
    echo -e "${GREEN}✓${NC} Prometheus is healthy"
    
    # Check targets
    TARGETS_UP=$(curl -s http://localhost:9090/api/v1/targets | jq -r '.data.activeTargets | map(select(.health == "up")) | length')
    echo "  Active targets: ${TARGETS_UP}"
    print_result 0
else
    echo -e "${RED}✗${NC} Prometheus is not healthy"
    print_result 1
fi

# 6. Check Grafana
print_header "6. Grafana Validation"
if curl -s http://localhost:3001/api/health | grep -q '"database":"ok"'; then
    echo -e "${GREEN}✓${NC} Grafana is healthy"
    
    # Check datasources
    DATASOURCES=$(curl -s -u admin:admin http://localhost:3001/api/datasources | jq '. | length')
    echo "  Configured datasources: ${DATASOURCES}"
    print_result 0
else
    echo -e "${RED}✗${NC} Grafana is not healthy"
    print_result 1
fi

# 7. Check Application Services
print_header "7. Application Services Health"
SERVICES=("rss-ingestor:8001" "normalizer:8002" "reddit-ingestor:8003" "market-ingestor:8004" "nlp-enricher:8005" "feature-store:8006")

for service in "${SERVICES[@]}"; do
    IFS=':' read -r name port <<< "$service"
    if curl -s http://localhost:${port}/health &>/dev/null; then
        echo -e "${GREEN}✓${NC} ${name} is healthy (port ${port})"
    else
        echo -e "${YELLOW}⚠${NC} ${name} is not responding (port ${port}) - may not be started"
    fi
done

# Summary
echo ""
echo "=========================================="
echo -e "  ${BLUE}VALIDATION SUMMARY${NC}"
echo "=========================================="
echo ""
echo "Total tests:  ${TOTAL_TESTS}"
echo -e "Passed:       ${GREEN}${PASSED_TESTS}${NC}"
echo -e "Failed:       ${RED}${FAILED_TESTS}${NC}"
echo ""

if [ ${FAILED_TESTS} -eq 0 ]; then
    echo -e "${GREEN}✓✓✓ ALL TESTS PASSED ✓✓✓${NC}"
    echo "Phase 1 infrastructure is ready!"
    exit 0
else
    echo -e "${RED}✗✗✗ SOME TESTS FAILED ✗✗✗${NC}"
    echo "Check logs in /tmp/*_validation.log"
    exit 1
fi
