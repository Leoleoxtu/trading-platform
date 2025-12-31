#!/bin/bash
# Script to inject test events continuously for observability testing

cd "$(dirname "$0")/../infra"

echo "Starting continuous event injection for Triage Stage 1 testing..."
echo "Press Ctrl+C to stop"

TOPICS=("rss" "reddit")
SOURCES=("bloomberg" "reuters" "wsj" "techcrunch" "cnbc")
KEYWORDS=("earnings" "acquisition" "merger" "IPO" "bankruptcy" "rally" "crash" "surge" "plunge")

while true; do
    RANDOM_TOPIC=${TOPICS[$RANDOM % ${#TOPICS[@]}]}
    RANDOM_SOURCE=${SOURCES[$RANDOM % ${#SOURCES[@]}]}
    RANDOM_KEYWORD=${KEYWORDS[$RANDOM % ${#KEYWORDS[@]}]}
    RANDOM_AMOUNT=$((RANDOM % 1000 + 50))
    RANDOM_PERCENT=$((RANDOM % 15 + 1))
    EVENT_ID="test-$(date +%s)-$RANDOM"
    
    TEXT="Breaking news: Major corporation reports $${RANDOM_AMOUNT}M in ${RANDOM_KEYWORD} activity. Market reacts with ${RANDOM_PERCENT}% movement in early trading session."
    
    docker exec -i redpanda rpk topic produce events.normalized.v1 --brokers localhost:9092 <<EOF
{"schema_version":"normalized_event.v1","event_id":"$EVENT_ID","text":"$TEXT","source_type":"$RANDOM_TOPIC","source_name":"$RANDOM_SOURCE","canonical_url":"https://example.com/$EVENT_ID","lang":"en","event_time_utc":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","normalized_at_utc":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","quality_flags":[],"original_source":{"id":"$EVENT_ID"}}
EOF
    
    # Random sleep between 1-5 seconds
    sleep $((RANDOM % 5 + 1))
done
