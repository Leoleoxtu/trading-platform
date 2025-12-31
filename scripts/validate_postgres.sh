#!/bin/bash
# Script to validate PostgreSQL/TimescaleDB setup
# Tests connection, database, tables, and TimescaleDB extension

set -e

echo "=========================================="
echo "  PostgreSQL/TimescaleDB Validation"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration from .env
POSTGRES_HOST="localhost"
POSTGRES_PORT="5432"
POSTGRES_DB="market"
POSTGRES_USER="market"
POSTGRES_PASSWORD="market_secret_change_me"

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

# 1. Check if PostgreSQL is accessible
echo "1. Checking PostgreSQL connectivity..."
if docker compose -f infra/docker-compose.yml exec timescaledb pg_isready -U ${POSTGRES_USER} &>/dev/null; then
    print_status 0 "PostgreSQL is accessible"
else
    print_status 1 "PostgreSQL is NOT accessible"
fi
echo ""

# 2. Check database exists
echo "2. Verifying database '${POSTGRES_DB}' exists..."
DB_EXISTS=$(docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'")
if [ "$DB_EXISTS" == "1" ]; then
    print_status 0 "Database '${POSTGRES_DB}' exists"
else
    print_status 1 "Database '${POSTGRES_DB}' does NOT exist"
fi
echo ""

# 3. Check TimescaleDB extension
echo "3. Checking TimescaleDB extension..."
TIMESCALE_VERSION=$(docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -tAc "SELECT extversion FROM pg_extension WHERE extname='timescaledb'" 2>/dev/null || echo "")
if [ ! -z "$TIMESCALE_VERSION" ]; then
    print_status 0 "TimescaleDB extension installed"
    print_info "Version: ${TIMESCALE_VERSION}"
else
    print_status 1 "TimescaleDB extension NOT installed"
fi
echo ""

# 4. List tables
echo "4. Listing tables..."
docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "\dt"
echo ""

# 5. Check hypertables
echo "5. Checking hypertables..."
HYPERTABLES=$(docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -tAc "SELECT table_name FROM timescaledb_information.hypertables" 2>/dev/null || echo "")
if [ ! -z "$HYPERTABLES" ]; then
    print_status 0 "Hypertables found:"
    echo "$HYPERTABLES" | while read -r table; do
        print_info "  - ${table}"
    done
else
    echo -e "${YELLOW}⚠${NC} No hypertables found"
fi
echo ""

# 6. Verify ohlcv table exists
echo "6. Verifying 'ohlcv' table..."
OHLCV_EXISTS=$(docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -tAc "SELECT 1 FROM information_schema.tables WHERE table_name='ohlcv'" 2>/dev/null || echo "")
if [ "$OHLCV_EXISTS" == "1" ]; then
    print_status 0 "Table 'ohlcv' exists"
    
    # Count records
    OHLCV_COUNT=$(docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -tAc "SELECT COUNT(*) FROM ohlcv" 2>/dev/null || echo "0")
    print_info "Records in ohlcv: ${OHLCV_COUNT}"
else
    echo -e "${YELLOW}⚠${NC} Table 'ohlcv' does NOT exist"
fi
echo ""

# 7. Verify feature_vectors table exists
echo "7. Verifying 'feature_vectors' table..."
FV_EXISTS=$(docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -tAc "SELECT 1 FROM information_schema.tables WHERE table_name='feature_vectors'" 2>/dev/null || echo "")
if [ "$FV_EXISTS" == "1" ]; then
    print_status 0 "Table 'feature_vectors' exists"
    
    # Count records
    FV_COUNT=$(docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -tAc "SELECT COUNT(*) FROM feature_vectors" 2>/dev/null || echo "0")
    print_info "Records in feature_vectors: ${FV_COUNT}"
else
    echo -e "${YELLOW}⚠${NC} Table 'feature_vectors' does NOT exist"
fi
echo ""

# 8. Test INSERT and DELETE
echo "8. Testing INSERT and DELETE operations..."
TEST_INSTRUMENT="TEST_$(date +%s)"
INSERT_RESULT=$(docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -tAc "INSERT INTO ohlcv (instrument_id, timeframe, ts, open, high, low, close, volume, source) VALUES ('${TEST_INSTRUMENT}', '1m', NOW(), 100, 105, 95, 102, 10000, 'test') RETURNING instrument_id" 2>/dev/null || echo "")

if [ ! -z "$INSERT_RESULT" ]; then
    print_status 0 "INSERT operation successful"
    
    # Delete test record
    docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -tAc "DELETE FROM ohlcv WHERE instrument_id='${TEST_INSTRUMENT}'" &>/dev/null
    print_status 0 "DELETE operation successful"
else
    print_status 1 "INSERT operation failed"
fi
echo ""

# 9. Check database size
echo "9. Database size..."
docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "SELECT pg_size_pretty(pg_database_size('${POSTGRES_DB}')) as database_size"
echo ""

# 10. Check connections
echo "10. Active connections..."
docker compose -f infra/docker-compose.yml exec -e PGPASSWORD=${POSTGRES_PASSWORD} timescaledb psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "SELECT COUNT(*) as active_connections FROM pg_stat_activity WHERE datname='${POSTGRES_DB}'"
echo ""

echo "=========================================="
echo -e "${GREEN}✓ PostgreSQL validation completed!${NC}"
echo "=========================================="
