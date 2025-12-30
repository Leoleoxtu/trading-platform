#!/bin/bash
# Script de vérification rapide des sources d'actualités

# Don't exit on error - we want to check all services
set +e

echo "============================================================"
echo "Vérification des Sources d'Actualités"
echo "============================================================"
echo ""

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Fonction de vérification
check_service() {
    local name=$1
    local port=$2
    local url="http://localhost:${port}/health"
    
    echo -n "Checking ${name}... "
    
    if response=$(curl -s --max-time 2 "${url}" 2>/dev/null); then
        if echo "$response" | grep -q '"status".*"healthy"' 2>/dev/null; then
            echo -e "${GREEN}✓ Healthy${NC}"
            echo "$response" | jq -c '{service, seen_items, stats}' 2>/dev/null || echo "$response"
            echo ""
            return 0
        else
            echo -e "${YELLOW}⚠ Unhealthy${NC}"
            echo "$response"
            echo ""
            return 1
        fi
    else
        echo -e "${RED}✗ Not responding${NC}"
        echo ""
        return 1
    fi
}

# Vérification des services
echo "1. Services Status"
echo "-------------------"
check_service "RSS Ingestor" 8001
echo ""
check_service "Reddit Ingestor" 8003
echo ""
check_service "Normalizer" 8002
echo ""

# Vérification Kafka
echo "2. Kafka Topics"
echo "---------------"
if docker exec redpanda rpk topic list 2>/dev/null | grep -q "raw.events.v1"; then
    echo -e "${GREEN}✓${NC} Kafka topics exist"
    docker exec redpanda rpk topic list 2>/dev/null | grep "events.v1"
else
    echo -e "${RED}✗${NC} Kafka not available"
fi
echo ""

# Vérification MinIO
echo "3. MinIO Buckets"
echo "----------------"
if docker run --rm --network infra_trading-platform --entrypoint /bin/sh minio/mc -c \
    'mc alias set local http://minio:9000 minioadmin minioadmin123 2>/dev/null && \
     mc ls local/raw-events/ 2>/dev/null' > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} MinIO bucket exists"
    echo "Sources disponibles:"
    docker run --rm --network infra_trading-platform --entrypoint /bin/sh minio/mc -c \
        'mc alias set local http://minio:9000 minioadmin minioadmin123 2>/dev/null && \
         mc ls local/raw-events/' 2>/dev/null | grep "PRE" || echo "  (aucune donnée encore)"
else
    echo -e "${RED}✗${NC} MinIO not available"
fi
echo ""

# Compte des événements récents
echo "4. Recent Events (last minute)"
echo "-------------------------------"
if docker exec redpanda rpk topic consume raw.events.v1 -n 100 --offset end --format json 2>/dev/null | \
    jq -r '.value | fromjson | .source_type' 2>/dev/null | sort | uniq -c > /tmp/events_count.txt 2>/dev/null; then
    
    if [ -s /tmp/events_count.txt ]; then
        echo -e "${GREEN}✓${NC} Events found:"
        cat /tmp/events_count.txt
    else
        echo -e "${YELLOW}⚠${NC} No recent events (may be normal if just started)"
    fi
else
    echo -e "${YELLOW}⚠${NC} Cannot read events (may need to wait for data)"
fi
echo ""

# Configuration Reddit
echo "5. Reddit Configuration"
echo "-----------------------"
if [ -f "../infra/.env" ]; then
    if grep -q "^REDDIT_CLIENT_ID=your_reddit" "../infra/.env" 2>/dev/null; then
        echo -e "${YELLOW}⚠${NC} Reddit credentials not configured"
        echo "   → Edit infra/.env and set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET"
    elif grep -q "^REDDIT_CLIENT_ID=.*[a-zA-Z0-9]" "../infra/.env" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Reddit credentials configured"
    else
        echo -e "${YELLOW}⚠${NC} Reddit credentials not set"
    fi
    
    if subreddits=$(grep "^REDDIT_SUBREDDITS=" "../infra/.env" 2>/dev/null | cut -d= -f2); then
        echo "   Subreddits: ${subreddits:-wallstreetbets,stocks (default)}"
    fi
else
    echo -e "${RED}✗${NC} .env file not found (run: cp infra/.env.example infra/.env)"
fi
echo ""

# Résumé
echo "============================================================"
echo "Summary"
echo "============================================================"
echo ""
echo "Access Points:"
echo "  • RSS Health:      http://localhost:8001/health"
echo "  • Reddit Health:   http://localhost:8003/health"
echo "  • Normalizer:      http://localhost:8002/health"
echo "  • Kafka UI:        http://localhost:8080"
echo "  • MinIO Console:   http://localhost:9001 (minioadmin/minioadmin123)"
echo ""
echo "Next Steps:"
echo "  1. Configure Reddit credentials in infra/.env (see MEMO_AJOUT_SOURCES.md)"
echo "  2. Restart services: cd infra && docker compose restart reddit-ingestor"
echo "  3. Monitor logs: docker compose logs -f reddit-ingestor rss-ingestor"
echo ""
