#!/bin/bash
# Feature Store v1 Implementation Checklist
# Validates that all required components are in place

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1 NOT FOUND"
        return 1
    fi
}

check_dir() {
    if [ -d "$1" ]; then
        echo -e "${GREEN}✓${NC} $1/"
        return 0
    else
        echo -e "${RED}✗${NC} $1/ NOT FOUND"
        return 1
    fi
}

check_in_file() {
    if grep -q "$2" "$1" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $1 contains '$2'"
        return 0
    else
        echo -e "${RED}✗${NC} $1 missing '$2'"
        return 1
    fi
}

echo "=========================================="
echo "Feature Store v1 Implementation Checklist"
echo "=========================================="
echo ""

FAIL=0

echo "A. Schema Definition"
echo "--------------------"
check_file "schemas/features.v1.json" || FAIL=1
check_file "schemas/samples/features_v1_valid.json" || FAIL=1
check_in_file "scripts/validate_schema_samples.py" "features.v1.json" || FAIL=1
echo ""

echo "B. TimescaleDB Setup"
echo "--------------------"
check_file "infra/timescale/feature_store_init.sql" || FAIL=1
check_in_file "infra/timescale/feature_store_init.sql" "feature_vectors" || FAIL=1
check_in_file "infra/timescale/feature_store_init.sql" "create_hypertable" || FAIL=1
check_in_file "infra/timescale/feature_store_init.sql" "UNIQUE.*instrument_id.*timeframe.*ts.*feature_set_version" || FAIL=1
check_in_file "infra/timescale/init.sql" "feature_store_init.sql" || FAIL=1
echo ""

echo "C. Feature Store Service"
echo "------------------------"
check_dir "services/features/feature-store" || FAIL=1
check_file "services/features/feature-store/app.py" || FAIL=1
check_file "services/features/feature-store/Dockerfile" || FAIL=1
check_file "services/features/feature-store/requirements.txt" || FAIL=1
check_in_file "services/features/feature-store/app.py" "ret_1" || FAIL=1
check_in_file "services/features/feature-store/app.py" "vol_20" || FAIL=1
check_in_file "services/features/feature-store/app.py" "sentiment_mean" || FAIL=1
check_in_file "services/features/feature-store/app.py" "quality_flags" || FAIL=1
check_in_file "services/features/feature-store/app.py" "/health" || FAIL=1
check_in_file "services/features/feature-store/app.py" "/metrics" || FAIL=1
echo ""

echo "D. Observability"
echo "----------------"
check_in_file "services/features/feature-store/app.py" "feature_store_compute_runs_total" || FAIL=1
check_in_file "services/features/feature-store/app.py" "feature_store_feature_vectors_upserted_total" || FAIL=1
check_in_file "services/features/feature-store/app.py" "feature_store_compute_failed_total" || FAIL=1
check_in_file "services/features/feature-store/app.py" "feature_store_compute_duration_seconds" || FAIL=1
check_in_file "services/features/feature-store/app.py" "feature_store_last_success_timestamp" || FAIL=1
check_file "infra/observability/grafana/dashboards/feature_store_health.json" || FAIL=1
check_in_file "infra/observability/prometheus.yml" "feature-store:8000" || FAIL=1
echo ""

echo "E. Docker Compose Integration"
echo "------------------------------"
check_in_file "infra/docker-compose.yml" "feature-store:" || FAIL=1
check_in_file "infra/docker-compose.yml" "services/features/feature-store" || FAIL=1
check_in_file "infra/docker-compose.yml" "8006:8000" || FAIL=1
echo ""

echo "F. Configuration"
echo "----------------"
check_in_file "infra/.env.example" "FEATURE_TICKERS" || FAIL=1
check_in_file "infra/.env.example" "FEATURE_TIMEFRAMES" || FAIL=1
check_in_file "infra/.env.example" "FEATURE_SET_VERSION" || FAIL=1
check_in_file "infra/.env.example" "FEATURE_REFRESH_SECONDS" || FAIL=1
check_in_file "infra/.env.example" "FEATURE_LOOKBACK_PERIODS" || FAIL=1
check_in_file "infra/.env.example" "FEATURE_EVENT_WINDOW_MINUTES" || FAIL=1
echo ""

echo "G. Testing"
echo "----------"
check_file "scripts/test_feature_store_smoke.py" || FAIL=1
check_in_file "scripts/test_feature_store_smoke.py" "test_db_connection" || FAIL=1
check_in_file "scripts/test_feature_store_smoke.py" "test_ohlcv_data" || FAIL=1
check_in_file "scripts/test_feature_store_smoke.py" "verify_feature_content" || FAIL=1
echo ""

echo "H. Documentation"
echo "----------------"
check_file "docs/50_feature_store.md" || FAIL=1
check_in_file "docs/50_feature_store.md" "feature_set_version" || FAIL=1
check_in_file "docs/50_feature_store.md" "ret_1" || FAIL=1
check_in_file "docs/50_feature_store.md" "quality_flags" || FAIL=1
check_in_file "docs/00_overview.md" "feature-store" || FAIL=1
check_in_file "docs/00_overview.md" "50_feature_store.md" || FAIL=1
echo ""

echo "=========================================="
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo "=========================================="
    exit 0
else
    echo -e "${RED}✗ Some checks failed${NC}"
    echo "=========================================="
    exit 1
fi
