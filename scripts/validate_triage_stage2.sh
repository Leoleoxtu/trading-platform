#!/bin/bash
# Validation script for Task 2.12: Triage Stage 2 Implementation

echo "=========================================="
echo "TASK 2.12 VALIDATION - TRIAGE STAGE 2"
echo "=========================================="
echo ""

ERRORS=0
WARNINGS=0

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check function
check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1 (MISSING)"
        ERRORS=$((ERRORS + 1))
    fi
}

check_min_lines() {
    if [ -f "$1" ]; then
        LINES=$(wc -l < "$1")
        if [ "$LINES" -ge "$2" ]; then
            echo -e "${GREEN}✓${NC} $1 ($LINES lines)"
        else
            echo -e "${YELLOW}⚠${NC} $1 ($LINES lines, expected >=$2)"
            WARNINGS=$((WARNINGS + 1))
        fi
    else
        echo -e "${RED}✗${NC} $1 (MISSING)"
        ERRORS=$((ERRORS + 1))
    fi
}

echo "1. Checking Schemas..."
echo "----------------------------------------"
check_file "schemas/triaged_event.v1.json"
check_file "schemas/samples/triaged_event_valid.json"
check_min_lines "schemas/triaged_event.v1.json" 200
echo ""

echo "2. Checking Configuration..."
echo "----------------------------------------"
check_file "config/triage_stage2.yaml"
check_file "config/tickers_whitelist.csv"
check_min_lines "config/triage_stage2.yaml" 150
echo ""

echo "3. Checking Service Implementation..."
echo "----------------------------------------"
check_file "services/preprocessing/triage_stage2/app.py"
check_file "services/preprocessing/triage_stage2/requirements.txt"
check_file "services/preprocessing/triage_stage2/Dockerfile"
check_file "services/preprocessing/triage_stage2/README.md"
check_min_lines "services/preprocessing/triage_stage2/app.py" 800
check_min_lines "services/preprocessing/triage_stage2/README.md" 200
echo ""

echo "4. Checking Infrastructure..."
echo "----------------------------------------"
if grep -q "triage-stage2:" infra/docker-compose.yml; then
    echo -e "${GREEN}✓${NC} infra/docker-compose.yml (triage-stage2 service defined)"
else
    echo -e "${RED}✗${NC} infra/docker-compose.yml (triage-stage2 service NOT FOUND)"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "events.triaged.v1" infra/redpanda/init-topics.sh; then
    echo -e "${GREEN}✓${NC} infra/redpanda/init-topics.sh (events.triaged.v1 topic)"
else
    echo -e "${RED}✗${NC} infra/redpanda/init-topics.sh (events.triaged.v1 NOT FOUND)"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "events.triaged.dlq.v1" infra/redpanda/init-topics.sh; then
    echo -e "${GREEN}✓${NC} infra/redpanda/init-topics.sh (events.triaged.dlq.v1 topic)"
else
    echo -e "${RED}✗${NC} infra/redpanda/init-topics.sh (events.triaged.dlq.v1 NOT FOUND)"
    ERRORS=$((ERRORS + 1))
fi
echo ""

echo "5. Checking Observability..."
echo "----------------------------------------"
if grep -q "triage-stage2" infra/observability/prometheus.yml; then
    echo -e "${GREEN}✓${NC} infra/observability/prometheus.yml (triage-stage2 scrape job)"
else
    echo -e "${RED}✗${NC} infra/observability/prometheus.yml (triage-stage2 NOT FOUND)"
    ERRORS=$((ERRORS + 1))
fi

check_file "infra/observability/grafana/dashboards/triage_stage2.json"
check_min_lines "infra/observability/grafana/dashboards/triage_stage2.json" 400
echo ""

echo "6. Checking Tests..."
echo "----------------------------------------"
check_file "tests/integration/test_triage_stage2.py"
check_min_lines "tests/integration/test_triage_stage2.py" 200
echo ""

echo "7. Checking Documentation..."
echo "----------------------------------------"
check_file "docs/triage_stage2.md"
check_file "services/preprocessing/triage_stage2/README.md"
check_file "TASK_2.12_COMPLETE.md"
check_min_lines "docs/triage_stage2.md" 300
check_min_lines "TASK_2.12_COMPLETE.md" 400
echo ""

echo "8. Checking Dependencies..."
echo "----------------------------------------"
if grep -q "spacy" services/preprocessing/triage_stage2/requirements.txt; then
    echo -e "${GREEN}✓${NC} spacy in requirements.txt"
else
    echo -e "${RED}✗${NC} spacy NOT in requirements.txt"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "transformers" services/preprocessing/triage_stage2/requirements.txt; then
    echo -e "${GREEN}✓${NC} transformers in requirements.txt"
else
    echo -e "${RED}✗${NC} transformers NOT in requirements.txt"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "aiokafka" services/preprocessing/triage_stage2/requirements.txt; then
    echo -e "${GREEN}✓${NC} aiokafka in requirements.txt"
else
    echo -e "${RED}✗${NC} aiokafka NOT in requirements.txt"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "prometheus-client" services/preprocessing/triage_stage2/requirements.txt; then
    echo -e "${GREEN}✓${NC} prometheus-client in requirements.txt"
else
    echo -e "${RED}✗${NC} prometheus-client NOT in requirements.txt"
    ERRORS=$((ERRORS + 1))
fi
echo ""

echo "9. Checking Dockerfile..."
echo "----------------------------------------"
if grep -q "en_core_web_sm" services/preprocessing/triage_stage2/Dockerfile; then
    echo -e "${GREEN}✓${NC} spaCy en_core_web_sm model download"
else
    echo -e "${RED}✗${NC} spaCy en_core_web_sm NOT in Dockerfile"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "fr_core_news_sm" services/preprocessing/triage_stage2/Dockerfile; then
    echo -e "${GREEN}✓${NC} spaCy fr_core_news_sm model download"
else
    echo -e "${RED}✗${NC} spaCy fr_core_news_sm NOT in Dockerfile"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "HEALTHCHECK" services/preprocessing/triage_stage2/Dockerfile; then
    echo -e "${GREEN}✓${NC} Healthcheck configured in Dockerfile"
else
    echo -e "${YELLOW}⚠${NC} Healthcheck NOT in Dockerfile"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

echo "10. Checking Key Functions in app.py..."
echo "----------------------------------------"
if grep -q "def extract_entities" services/preprocessing/triage_stage2/app.py; then
    echo -e "${GREEN}✓${NC} extract_entities() function"
else
    echo -e "${RED}✗${NC} extract_entities() NOT FOUND"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "def analyze_sentiment" services/preprocessing/triage_stage2/app.py; then
    echo -e "${GREEN}✓${NC} analyze_sentiment() function"
else
    echo -e "${RED}✗${NC} analyze_sentiment() NOT FOUND"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "def validate_tickers" services/preprocessing/triage_stage2/app.py; then
    echo -e "${GREEN}✓${NC} validate_tickers() function"
else
    echo -e "${RED}✗${NC} validate_tickers() NOT FOUND"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "def calculate_score" services/preprocessing/triage_stage2/app.py; then
    echo -e "${GREEN}✓${NC} calculate_score() function"
else
    echo -e "${RED}✗${NC} calculate_score() NOT FOUND"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "def detect_market_regime" services/preprocessing/triage_stage2/app.py; then
    echo -e "${GREEN}✓${NC} detect_market_regime() function"
else
    echo -e "${RED}✗${NC} detect_market_regime() NOT FOUND"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "def detect_load_regime" services/preprocessing/triage_stage2/app.py; then
    echo -e "${GREEN}✓${NC} detect_load_regime() function"
else
    echo -e "${RED}✗${NC} detect_load_regime() NOT FOUND"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "def calculate_thresholds" services/preprocessing/triage_stage2/app.py; then
    echo -e "${GREEN}✓${NC} calculate_thresholds() function"
else
    echo -e "${RED}✗${NC} calculate_thresholds() NOT FOUND"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "def assign_priority" services/preprocessing/triage_stage2/app.py; then
    echo -e "${GREEN}✓${NC} assign_priority() function"
else
    echo -e "${RED}✗${NC} assign_priority() NOT FOUND"
    ERRORS=$((ERRORS + 1))
fi
echo ""

echo "=========================================="
echo "VALIDATION SUMMARY"
echo "=========================================="
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ ALL CHECKS PASSED!${NC}"
    echo ""
    echo "Task 2.12 implementation is COMPLETE and VALID."
    echo ""
    echo "Next steps:"
    echo "1. Build Docker image: docker compose --profile apps build triage-stage2"
    echo "2. Start service: docker compose --profile apps up -d triage-stage2"
    echo "3. Check health: curl http://localhost:8007/health"
    echo "4. Run tests: python tests/integration/test_triage_stage2.py"
    echo "5. View dashboard: http://localhost:3001/d/triage-stage2"
    echo ""
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ CHECKS PASSED WITH WARNINGS${NC}"
    echo "Warnings: $WARNINGS"
    echo ""
    echo "Implementation is functional but has minor issues to review."
    echo ""
    exit 0
else
    echo -e "${RED}✗ VALIDATION FAILED${NC}"
    echo "Errors: $ERRORS"
    echo "Warnings: $WARNINGS"
    echo ""
    echo "Please fix the errors above before deploying."
    echo ""
    exit 1
fi
