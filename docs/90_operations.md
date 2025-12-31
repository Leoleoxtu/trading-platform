# Operations Guide

## Quick Start

### Prerequisites

- Docker Desktop installed and running
- WSL2 enabled (if on Windows)
- Docker Compose V2 (comes with Docker Desktop)
- At least 4GB of available RAM

### Starting the Infrastructure

```bash
cd infra
docker compose up -d
```

This single command will:
1. Start Redpanda (Kafka broker)
2. Start MinIO (S3 storage)
3. Start Kafka UI (web interface)
4. Initialize all Kafka topics automatically
5. Initialize all S3 buckets automatically

### Stopping the Infrastructure

```bash
cd infra
docker compose down
```

To also remove all data (volumes):
```bash
cd infra
docker compose down -v
```

⚠️ **Warning**: `down -v` will delete all Kafka messages and S3 objects!

## Verification Commands

### Check Service Status

```bash
cd infra
docker compose ps
```

Expected output: All services should be "Up" or "Exited" (for init-* services).

### List Kafka Topics

```bash
docker exec -it redpanda rpk topic list
```

Expected output:
```
NAME                      PARTITIONS  REPLICAS
events.enriched.dlq.v1    1           1
events.enriched.v1        6           1
events.normalized.dlq.v1  1           1
events.normalized.v1      6           1
raw.events.dlq.v1         1           1
raw.events.v1             6           1
```

### Describe a Kafka Topic

```bash
docker exec -it redpanda rpk topic describe raw.events.v1
```

This shows detailed information about partitions, replication, and configuration.

### List MinIO Buckets

```bash
docker exec -it init-minio mc ls local
```

Or configure mc locally:
```bash
# ⚠️ NOTE: Default credentials shown below - change these in production!
docker run --rm -it --network infra_default minio/mc \
  alias set local http://minio:9000 minioadmin minioadmin123

docker run --rm -it --network infra_default minio/mc \
  ls local
```

Expected output:
```
[2024-01-15 10:30:00 UTC]     0B pipeline-artifacts/
[2024-01-15 10:30:00 UTC]     0B raw-events/
```

### Check Container Logs

```bash
# All services
cd infra
docker compose logs

# Specific service
docker compose logs redpanda
docker compose logs minio
docker compose logs kafka-ui

# Follow logs in real-time
docker compose logs -f redpanda

# Init services logs
docker compose logs init-topics
docker compose logs init-minio
```

## Web Interfaces

### Kafka UI
- URL: http://localhost:8080
- Purpose: Browse topics, view messages, manage consumer groups
- No authentication required (local development)

**What you can do:**
- View all topics and their configurations
- Browse messages in topics
- View consumer group offsets
- Monitor broker health

### MinIO Console
- URL: http://localhost:9001
- Username: `minioadmin`
- Password: `minioadmin123`

**What you can do:**
- Browse buckets and objects
- Upload/download files
- Set bucket policies
- Monitor storage usage

## Advanced Operations

### Produce Test Message to Kafka

```bash
echo '{"event_id":"test123","source":"manual","timestamp":"2024-01-15T10:00:00Z"}' | \
  docker exec -i redpanda rpk topic produce raw.events.v1
```

### Consume Messages from Kafka

```bash
# Consume raw events
docker exec -it redpanda rpk topic consume raw.events.v1 --num 10

# Consume normalized events
docker exec -it redpanda rpk topic consume events.normalized.v1 --num 10

# Consume enriched events
docker exec -it redpanda rpk topic consume events.enriched.v1 --num 10

# Check DLQ for failures
docker exec -it redpanda rpk topic consume events.enriched.dlq.v1 --num 10
```

### Upload File to MinIO

```bash
# First, copy file to container
docker cp myfile.json init-minio:/tmp/

# Then upload to bucket
docker exec -it init-minio mc cp /tmp/myfile.json local/raw-events/
```

### Check Redpanda Cluster Info

```bash
docker exec -it redpanda rpk cluster info
```

### Reset Topics (Delete and Recreate)

```bash
# Delete a topic
docker exec -it redpanda rpk topic delete raw.events.v1

# Recreate by restarting init service
cd infra
docker compose up init-topics
```

## Configuration

### Using Environment Variables

1. Copy the example environment file:
```bash
cd infra
cp .env.example .env
```

2. Edit `.env` to customize ports, credentials, or resources:
```bash
# Example customizations
REDPANDA_PORT=9093
MINIO_CONSOLE_PORT=9002
REDPANDA_MEMORY=2G
```

3. Restart services:
```bash
docker compose down
docker compose up -d
```

### Changing MinIO Credentials

⚠️ **IMPORTANT**: The default credentials (`minioadmin`/`minioadmin123`) are for local development only. **Never use these in production!**

To change credentials, edit `infra/.env`:
```
MINIO_ROOT_USER=myadmin
MINIO_ROOT_PASSWORD=mysecurepassword
```

Then restart:
```bash
cd infra
docker compose down -v  # Remove old data
docker compose up -d
```

**Security Note**: For production deployments:
- Use strong, randomly generated passwords
- Consider using secrets management (Docker secrets, Vault, etc.)
- Enable TLS/SSL encryption
- Implement proper access controls and IAM policies
- Change all default credentials before exposing services

## Troubleshooting

### Issue: Services Won't Start

**Symptoms:** `docker compose up -d` fails or services exit immediately

**Solutions:**
1. Check if Docker Desktop is running:
   ```bash
   docker ps
   ```

2. Check if WSL2 is properly configured (Windows):
   ```bash
   wsl --list --verbose
   ```

3. Check available disk space:
   ```bash
   df -h
   ```

4. Check Docker logs:
   ```bash
   cd infra
   docker compose logs
   ```

### Issue: Port Already in Use

**Symptoms:** Error like "bind: address already in use"

**Solution 1:** Find what's using the port (e.g., 9092):
```bash
# Linux/WSL2
sudo lsof -i :9092
# or
sudo netstat -nlp | grep 9092

# Windows PowerShell
netstat -ano | findstr :9092
```

Kill the process or change the port in `infra/.env`:
```
REDPANDA_PORT=9093
```

**Solution 2:** Use different ports in `.env`:
```bash
cd infra
cp .env.example .env
# Edit .env to change ports
docker compose up -d
```

### Issue: Kafka UI Can't Connect to Broker

**Symptoms:** Kafka UI shows "Cannot connect to broker" or empty cluster

**Solutions:**
1. Check if Redpanda is healthy:
   ```bash
   docker compose ps redpanda
   ```

2. Check Redpanda logs:
   ```bash
   docker compose logs redpanda
   ```

3. Verify network connectivity:
   ```bash
   docker exec -it kafka-ui ping redpanda
   ```

4. Ensure proper depends_on configuration (should already be set)

5. Restart services:
   ```bash
   cd infra
   docker compose restart kafka-ui
   ```

### Issue: Topics Not Created

**Symptoms:** `rpk topic list` shows no topics or missing topics

**Solutions:**
1. Check init-topics logs:
   ```bash
   docker compose logs init-topics
   ```

2. Manually run initialization:
   ```bash
   cd infra
   docker compose up init-topics
   ```

3. If init-topics failed, check Redpanda health:
   ```bash
   docker exec -it redpanda rpk cluster info
   ```

### Issue: MinIO Buckets Not Created

**Symptoms:** MinIO console shows no buckets

**Solutions:**
1. Check init-minio logs:
   ```bash
   docker compose logs init-minio
   ```

2. Manually run initialization:
   ```bash
   cd infra
   docker compose up init-minio
   ```

3. Verify MinIO is healthy:
   ```bash
   docker exec -it minio mc admin info local
   ```

### Issue: WSL2 Docker Daemon Issues

**Symptoms:** Docker commands hang or fail in WSL2

**Solutions:**
1. Restart Docker Desktop from Windows

2. Restart WSL2:
   ```powershell
   # In Windows PowerShell (as Administrator)
   wsl --shutdown
   wsl
   ```

3. Check Docker Desktop WSL2 integration:
   - Open Docker Desktop Settings
   - Go to Resources → WSL Integration
   - Ensure your WSL2 distro is enabled

4. Verify Docker is accessible from WSL2:
   ```bash
   docker version
   ```

### Issue: Out of Memory

**Symptoms:** Services crash or are killed by OOM killer

**Solutions:**
1. Increase Docker Desktop memory limit:
   - Open Docker Desktop Settings
   - Go to Resources
   - Increase Memory to at least 4GB

2. Reduce Redpanda memory in `.env`:
   ```
   REDPANDA_MEMORY=512M
   ```

3. Restart Docker Desktop

### Issue: Slow Performance

**Solutions:**
1. Ensure WSL2 is being used (not WSL1):
   ```bash
   wsl --list --verbose
   # Should show VERSION 2
   ```

2. Ensure Docker Desktop is using WSL2 backend:
   - Docker Desktop Settings → General → Use WSL2 based engine

3. Close unnecessary applications to free up RAM

4. Consider running fewer services if on resource-constrained hardware

## Maintenance

### View Disk Usage

```bash
# Check Docker disk usage
docker system df

# Check volume sizes
docker volume ls
docker volume inspect infra_redpanda_data
docker volume inspect infra_minio_data
```

### Clean Up Old Data

```bash
# Remove stopped containers
docker container prune

# Remove unused volumes (⚠️ only if you're sure!)
docker volume prune

# Remove all unused resources
docker system prune -a --volumes
```

### Backup Data

```bash
# Backup MinIO data
docker run --rm --volumes-from minio -v $(pwd):/backup \
  alpine tar czf /backup/minio-backup.tar.gz /data

# Backup Redpanda data
docker run --rm --volumes-from redpanda -v $(pwd):/backup \
  alpine tar czf /backup/redpanda-backup.tar.gz /var/lib/redpanda/data
```

### Update Images

```bash
cd infra
docker compose pull
docker compose up -d
```

## Monitoring

### Health Checks

```bash
# Check health status
docker compose ps

# Detailed health information
docker inspect redpanda | grep -A 20 Health
docker inspect minio | grep -A 20 Health

# Application service health endpoints
curl http://localhost:8001/health  # RSS Ingestor
curl http://localhost:8002/health  # Normalizer
curl http://localhost:8003/health  # Reddit Ingestor
curl http://localhost:8004/health  # Market Ingestor
curl http://localhost:8005/health  # NLP Enricher
```

### Resource Usage

```bash
# Real-time resource usage
docker stats

# Specific services
docker stats redpanda minio kafka-ui
```

## Development Workflow

### Typical Development Session

```bash
# 1. Start infrastructure
cd infra
docker compose up -d

# 2. Verify everything is running
docker compose ps
docker compose logs -f  # Watch logs

# 3. Check Kafka UI: http://localhost:8080
# 4. Check MinIO Console: http://localhost:9001

# 5. Develop your application (connects to localhost:9092 for Kafka, localhost:9000 for S3)

# 6. When done, stop services
docker compose down
# Or keep running for next session
```

### Re-running Initialization

```bash
cd infra

# Re-run topic initialization
docker compose up init-topics

# Re-run bucket initialization
docker compose up init-minio
```

The scripts are idempotent - they won't recreate existing topics/buckets.

## Acceptance Tests

The following tests confirm the infrastructure is working correctly:

### Test 1: Start Infrastructure

```bash
cd infra
docker compose --profile infra up -d
```

**Expected result:**
- All services start successfully
- Healthchecks pass for Redpanda and MinIO
- Init services complete and exit with code 0

### Test 2: Verify Topics Created

```bash
docker exec -it redpanda rpk topic list --brokers redpanda:29092
```

**Expected output:**
```
NAME                      PARTITIONS  REPLICAS
events.enriched.dlq.v1    1           1
events.enriched.v1        6           1
events.normalized.dlq.v1  1           1
events.normalized.v1      6           1
raw.events.dlq.v1         1           1
raw.events.v1             6           1
```

### Test 3: Verify Buckets Created

```bash
docker run --rm --network infra_trading-platform minio/mc \
  sh -c 'mc alias set local http://minio:9000 minioadmin minioadmin123 && mc ls local'
```

**Expected output:**
```
[YYYY-MM-DD HH:MM:SS UTC]     0B pipeline-artifacts/
[YYYY-MM-DD HH:MM:SS UTC]     0B raw-events/
```

### Test 4: Kafka UI Accessible

Navigate to http://localhost:8080

**Expected result:**
- Kafka UI loads successfully
- Cluster "local-redpanda" shows as online
- Topics page displays all 4 topics with correct partition counts

### Test 5: MinIO Console Accessible

Navigate to http://localhost:9001

**Expected result:**
- MinIO console login page loads
- Can login with `minioadmin` / `minioadmin123`
- Browser shows both buckets: `raw-events` and `pipeline-artifacts`

### Test 6: Idempotence

```bash
cd infra
docker compose up init-topics --force-recreate
docker compose up init-minio --force-recreate
```

**Expected result:**
- Both services run successfully
- Topics/buckets are detected as existing and skipped
- No errors occur
- Services exit with code 0

### Test 7: Start Applications (Phase 1)

```bash
cd infra
docker compose --profile apps up -d
```

**Expected result:**
- Infrastructure services start (if not already running)
- RSS ingestor and normalizer services start
- All health checks pass after 30 seconds

### Test 8: Verify RSS Ingestor Health

```bash
curl http://localhost:8001/health
```

**Expected output:**
```json
{
  "status": "healthy",
  "service": "rss-ingestor",
  "feeds_count": 1,
  "seen_items": 0
}
```

### Test 9: Verify Normalizer Health

```bash
curl http://localhost:8002/health
```

**Expected output:**
```json
{
  "status": "healthy",
  "service": "normalizer",
  "stats": {
    "processed": 0,
    "dedup_hits": 0,
    "dlq_count": 0,
    "errors": 0
  }
}
```

### Test 10: Verify Raw Events Generated

Wait 2-3 minutes for RSS polling, then:

```bash
docker exec -it redpanda rpk topic consume raw.events.v1 -n 5
```

**Expected output:**
- JSON messages with `schema_version: "raw_event.v1"`
- Valid `event_id`, `source_type: "rss"`, `raw_uri` fields
- Messages contain `correlation_id` for tracing

### Test 11: Verify Normalized Events Generated

Wait 1-2 minutes after raw events appear, then:

```bash
docker exec -it redpanda rpk topic consume events.normalized.v1 -n 5
```

**Expected output:**
- JSON messages with `schema_version: "normalized_event.v1"`
- Valid `event_id` matching raw events
- `normalized_text`, `lang`, `dedup_key` fields present
- `symbols_candidates` array (may be empty)

### Test 12: Verify Raw Events in MinIO

```bash
docker run --rm --network infra_trading-platform minio/mc \
  sh -c 'mc alias set local http://minio:9000 minioadmin minioadmin123 && \
         mc ls --recursive local/raw-events/source=rss/ | head -10'
```

**Expected output:**
- List of JSON files in `source=rss/dt=YYYY-MM-DD/` partitions
- File names are UUIDs with `.json` extension

### Test 13: Trace Event End-to-End

Pick an `event_id` from a normalized event, then:

```bash
EVENT_ID="<event_id_from_test_11>"

# Find in normalized topic
docker exec -it redpanda rpk topic consume events.normalized.v1 -f json | \
  grep "$EVENT_ID" | head -1

# Find in raw topic
docker exec -it redpanda rpk topic consume raw.events.v1 -f json | \
  grep "$EVENT_ID" | head -1

# Find raw file in MinIO
docker run --rm --network infra_trading-platform minio/mc \
  sh -c 'mc alias set local http://minio:9000 minioadmin minioadmin123 && \
         mc find local/raw-events --name "*'$EVENT_ID'*"'
```

**Expected result:**
- Same `event_id` found in both topics
- Raw JSON file exists in MinIO with matching event_id
- `correlation_id` is consistent across all artifacts

### Test 14: Verify DLQ is Empty (Good Path)

```bash
docker exec -it redpanda rpk topic consume events.normalized.dlq.v1 -n 1 --timeout 5s
```

**Expected result:**
- Timeout or empty result (no messages in DLQ)
- If messages exist, investigate error_type and error_message

### Test 15: Verify Schema Validation

```bash
cd /home/runner/work/trading-platform/trading-platform
python3 scripts/validate_schema_samples.py
```

**Expected output:**
```
Validating schema samples...

✓ raw_event_valid.json is valid against raw_event.v1.json
✓ normalized_event_valid.json is valid against normalized_event.v1.json
✓ enriched_event_valid.json is valid against enriched_event.v1.json

All validations passed! ✓
```

### Test 16: Verify NLP Enricher Health

```bash
curl http://localhost:8005/health
```

**Expected output:**
```json
{
  "status": "healthy",
  "service": "nlp-enricher",
  "stats": {
    "consumed": 0,
    "enriched": 0,
    "failed": 0,
    "dlq_count": 0
  }
}
```

### Test 17: Verify Enriched Events Generated

Wait 1-2 minutes after normalized events appear, then:

```bash
docker exec -it redpanda rpk topic consume events.enriched.v1 -n 5
```

**Expected output:**
- JSON messages with `schema_version: "enriched_event.v1"`
- Valid `event_id` matching normalized events
- `entities` array with extracted named entities
- `tickers` array with validated symbols
- `sentiment` object with score and confidence
- `event_category` classification

### Test 18: Verify Enriched Events in MinIO

```bash
docker run --rm --network infra_trading-platform minio/mc \
  sh -c 'mc alias set local http://minio:9000 minioadmin minioadmin123 && \
         mc ls --recursive local/pipeline-artifacts/enriched/ | head -10'
```

**Expected output:**
- List of JSON files in `enriched/source=<type>/dt=YYYY-MM-DD/` partitions
- File names are UUIDs with `.json` extension

### Test 19: Run End-to-End Enrichment Test

```bash
python3 scripts/test_enrichment_e2e.py
```

**Expected output:**
```
🧪 NLP Enrichment Service - End-to-End Tests
======================================================================
📋 Test 1: Validating enriched event schema...
✅ Enriched event schema validation passed
...
Result: 6/6 tests passed
======================================================================
🎉 All tests passed!
```

## Event Validation Commands

### Produce Test Raw Event

```bash
echo '{
  "schema_version": "raw_event.v1",
  "event_id": "'$(uuidgen)'",
  "source_type": "manual",
  "source_name": "test-script",
  "captured_at_utc": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
  "event_time_utc": null,
  "raw_uri": "s3://raw-events/source=manual/dt='$(date -u +%Y-%m-%d)'/test.json",
  "raw_hash": "a3b5c9d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9",
  "content_type": "application/json",
  "priority": "LOW",
  "correlation_id": "'$(uuidgen)'",
  "metadata": {}
}' | docker exec -i redpanda rpk topic produce raw.events.v1
```

### Consume Raw Events with Filter

```bash
# Consume and filter by source_type
docker exec -it redpanda rpk topic consume raw.events.v1 -f json | \
  grep '"source_type":"rss"' | head -5

# Consume and extract event_id
docker exec -it redpanda rpk topic consume raw.events.v1 -f json | \
  jq -r '.value.event_id' | head -10
```

### Consume Normalized Events with Filter

```bash
# Filter by language
docker exec -it redpanda rpk topic consume events.normalized.v1 -f json | \
  grep '"lang":"en"' | head -5

# Extract symbols
docker exec -it redpanda rpk topic consume events.normalized.v1 -f json | \
  jq -r '.value.symbols_candidates[]' | sort | uniq -c | sort -rn | head -20
```

### Consume Enriched Events with Filter

```bash
# Filter by event category
docker exec -it redpanda rpk topic consume events.enriched.v1 -f json | \
  grep '"event_category":"earnings"' | head -5

# Extract sentiment scores
docker exec -it redpanda rpk topic consume events.enriched.v1 -f json | \
  jq -r '.value.sentiment.score' | sort -n | tail -10

# View entities extracted
docker exec -it redpanda rpk topic consume events.enriched.v1 -f json | \
  jq -r '.value.entities[] | "\(.type): \(.text)"' | head -20

# Count events by category
docker exec -it redpanda rpk topic consume events.enriched.v1 -f json | \
  jq -r '.value.event_category' | sort | uniq -c | sort -rn
```

### Search Event by ID in Kafka UI

1. Open http://localhost:8080
2. Navigate to Topics → `raw.events.v1` or `events.normalized.v1`
3. Click "Messages" tab
4. Use search/filter box: `event_id` → enter UUID
5. View message details, headers, and key

### Download Raw Event from MinIO

```bash
EVENT_ID="<your_event_id>"
DATE="<YYYY-MM-DD>"

docker run --rm --network infra_trading-platform minio/mc \
  sh -c 'mc alias set local http://minio:9000 minioadmin minioadmin123 && \
         mc cat local/raw-events/source=rss/dt='$DATE'/'$EVENT_ID'.json' | jq .
```

## Monitoring and Observability

### Check Service Logs

```bash
# All services
docker compose --profile apps logs -f

# Specific service
docker compose logs -f rss-ingestor
docker compose logs -f normalizer

# Filter by level
docker compose logs rss-ingestor | grep '"level":"ERROR"'
docker compose logs normalizer | grep '"level":"WARNING"'
```

### Check Health Endpoints

```bash
# RSS Ingestor
curl http://localhost:8001/health | jq .

# Normalizer
curl http://localhost:8002/health | jq .

# NLP Enricher
curl http://localhost:8005/health | jq .
```

### Check Prometheus Metrics

```bash
# RSS Ingestor metrics
curl http://localhost:8001/metrics | grep rss_ingestor

# Normalizer metrics
curl http://localhost:8002/metrics | grep normalizer

# NLP Enricher metrics
curl http://localhost:8005/metrics | grep nlp_enricher

# View enrichment throughput
curl http://localhost:8005/metrics | grep nlp_enricher_events_enriched_total

# View sentiment drift
curl http://localhost:8005/metrics | grep nlp_enricher_sentiment_mean
```

### Monitor Kafka Consumer Groups

```bash
# List consumer groups
docker exec -it redpanda rpk group list

# Describe normalizer consumer group
docker exec -it redpanda rpk group describe normalizer-v1

# Check lag
docker exec -it redpanda rpk group describe normalizer-v1 --partitions
```

### Check Topic Stats

```bash
# Topic details
docker exec -it redpanda rpk topic describe raw.events.v1
docker exec -it redpanda rpk topic describe events.normalized.v1

# Message count (approximate)
docker exec -it redpanda rpk topic describe raw.events.v1 | grep "high water mark"
```

### Check MinIO Storage Usage

Via Console: http://localhost:9001 → Buckets → raw-events → Summary

Via CLI:
```bash
docker run --rm --network infra_trading-platform minio/mc \
  sh -c 'mc alias set local http://minio:9000 minioadmin minioadmin123 && \
         mc du local/raw-events'
```

## Troubleshooting Phase 1

### No Raw Events Being Generated

**Symptom**: `raw.events.v1` topic is empty after several minutes

**Solution**:
1. Check RSS ingestor logs:
   ```bash
   docker compose logs rss-ingestor | tail -50
   ```

2. Verify RSS feeds are accessible:
   ```bash
   docker exec -it rss-ingestor python -c "import feedparser; print(feedparser.parse('https://feeds.feedburner.com/TechCrunch/'))"
   ```

3. Check if items are being marked as duplicates:
   ```bash
   curl http://localhost:8001/health | jq .seen_items
   ```

4. Reset deduplication state:
   ```bash
   docker compose stop rss-ingestor
   docker volume rm infra_rss_ingestor_data
   docker compose --profile apps up -d rss-ingestor
   ```

### No Normalized Events Being Generated

**Symptom**: `events.normalized.v1` topic is empty but `raw.events.v1` has messages

**Solution**:
1. Check normalizer logs:
   ```bash
   docker compose logs normalizer | tail -50
   ```

2. Check consumer group lag:
   ```bash
   docker exec -it redpanda rpk group describe normalizer-v1
   ```

3. Check DLQ for errors:
   ```bash
   docker exec -it redpanda rpk topic consume events.normalized.dlq.v1 -n 10
   ```

4. Verify MinIO connectivity from normalizer:
   ```bash
   docker exec -it normalizer wget -O- http://minio:9000/minio/health/live
   ```

### High DLQ Count

**Symptom**: Many messages in `events.normalized.dlq.v1`

**Solution**:
1. Consume DLQ and check error types:
   ```bash
   docker exec -it redpanda rpk topic consume events.normalized.dlq.v1 -f json | \
     jq -r '.value | "\(.error_type): \(.error_message)"' | head -20
   ```

2. Common issues:
   - `download_error`: Raw files missing in MinIO (check S3 URIs)
   - `schema_validation_error`: Schema version mismatch
   - `normalization_error`: Empty text content

### Schema Validation Errors

**Symptom**: Events rejected due to schema validation

**Solution**:
1. Check schema version in events:
   ```bash
   docker exec -it redpanda rpk topic consume raw.events.v1 -n 1 -f json | \
     jq .value.schema_version
   ```

2. Validate sample events:
   ```bash
   docker exec -it redpanda rpk topic consume raw.events.v1 -n 1 -f json | \
     jq .value > /tmp/test_event.json
   
   python3 scripts/validate_schema_samples.py \
     schemas/raw_event.v1.json /tmp/test_event.json
   ```

## Next Steps

After verifying Phase 1 works:

1. ✅ Infrastructure running (Redpanda, MinIO, Kafka UI)
2. ✅ RSS ingestor producing raw events
3. ✅ Normalizer processing and producing normalized events
4. ✅ Schemas validated
5. ✅ End-to-end tracing working
6. ✅ Observability stack (Prometheus, Grafana) - Phase 1.2 ✅

Future development:
- Twitter/X API ingestion service
- Reddit API ingestion service  
- Market data ingestion (yfinance, Finnhub)
- Data enrichment pipeline (symbol validation, sentiment)
- Stream processing (real-time aggregations)

See `docs/10_ingestion.md` and `docs/20_normalization.md` for service details.

---

## Observability (Phase 1.2)

### Overview

The observability stack provides comprehensive monitoring of the trading platform pipeline using Prometheus and Grafana. It tracks throughput, latency, error rates, deduplication, and consumer lag.

**Stack Components:**
- **Prometheus**: Metrics collection and storage
- **Grafana**: Visualization and dashboards
- **Kafka Exporter**: Consumer lag metrics for Redpanda
- **Service /metrics endpoints**: RSS ingestor and normalizer expose Prometheus metrics

### Starting Observability Stack

The observability stack is optional and runs via the `observability` profile:

```bash
cd infra

# Option 1: Start everything together (recommended)
docker compose --profile apps --profile observability up -d

# Option 2: Start observability separately
docker compose --profile infra up -d      # Infrastructure first
docker compose --profile apps up -d       # Applications second
docker compose --profile observability up -d  # Observability last
```

**Note:** Applications work perfectly fine without the observability profile. This is optional for monitoring.

### Access Points

After starting the observability stack:

- **Grafana**: http://localhost:3001
  - Default credentials: `admin` / `admin`
  - Dashboard: "Pipeline Health" (auto-provisioned)
- **Prometheus**: http://localhost:9090
  - Query UI and target status
- **Kafka Exporter**: http://localhost:9308/metrics
  - Consumer lag metrics

### Verifying Observability

#### 1. Check All Services Running

```bash
docker compose --profile observability ps
```

Expected output should show `prometheus`, `grafana`, and `kafka-exporter` containers running.

#### 2. Check Metrics Endpoints

```bash
# RSS Ingestor metrics
curl -s http://localhost:8001/metrics | head -20

# Normalizer metrics
curl -s http://localhost:8002/metrics | head -20
```

Expected: Prometheus-format metrics (lines starting with `# HELP` and metric names).

#### 3. Verify Prometheus Targets

Navigate to http://localhost:9090/targets

Expected: All targets should show status "UP":
- `rss-ingestor` (1/1 up)
- `normalizer` (1/1 up)
- `kafka-exporter` (1/1 up)

#### 4. Access Grafana Dashboard

1. Navigate to http://localhost:3001
2. Login with `admin` / `admin` (or your configured credentials)
3. Go to Dashboards → "Pipeline Health"
4. Wait 1-2 minutes for data to populate

### Available Metrics

#### RSS Ingestor Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `rss_ingestor_items_fetched_total` | Counter | Total items fetched from RSS feeds |
| `rss_ingestor_raw_events_published_total` | Counter | Total raw events published to Kafka |
| `rss_ingestor_raw_events_failed_total` | Counter | Total failed raw events |
| `rss_ingestor_dedup_hits_total` | Counter | Total deduplicated items |
| `rss_ingestor_poll_duration_seconds` | Histogram | RSS feed polling duration |
| `rss_ingestor_minio_put_duration_seconds` | Histogram | MinIO upload duration |
| `rss_ingestor_kafka_produce_duration_seconds` | Histogram | Kafka produce duration |
| `rss_ingestor_last_success_timestamp` | Gauge | Unix timestamp of last successful poll |

#### Normalizer Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `normalizer_raw_events_consumed_total` | Counter | Total raw events consumed |
| `normalizer_normalized_events_published_total` | Counter | Total normalized events published |
| `normalizer_events_failed_total{stage}` | Counter | Failed events by stage (download, parse, schema, normalize, produce) |
| `normalizer_dlq_published_total` | Counter | Total events sent to DLQ |
| `normalizer_dedup_hits_total` | Counter | Total duplicate events detected |
| `normalizer_processing_duration_seconds` | Histogram | End-to-end event processing duration |
| `normalizer_minio_get_duration_seconds` | Histogram | MinIO download duration |
| `normalizer_kafka_produce_duration_seconds` | Histogram | Kafka produce duration |
| `normalizer_last_success_timestamp` | Gauge | Unix timestamp of last successful processing |

#### Kafka Consumer Lag Metrics (via kafka-exporter)

| Metric | Type | Description |
|--------|------|-------------|
| `kafka_consumergroup_lag{consumergroup, topic, partition}` | Gauge | Consumer lag by consumer group, topic, and partition |

### Pipeline Health Dashboard

The "Pipeline Health" dashboard is automatically provisioned and includes:

#### Throughput Panels
- **Events Per Second**: Raw events published vs normalized events published
- **Throughput rates** over time

#### DLQ Monitoring
- **DLQ Events Per Second**: Rate of events sent to dead letter queue
- **Total DLQ Count**: Cumulative DLQ events (alerts if high)

#### Latency Analysis
- **Normalizer Processing Latency**: p50, p95, p99 percentiles
- **RSS Ingestor Latency**: Poll duration and Kafka produce latency (p50, p95)

#### Deduplication Metrics
- **Deduplication Rate**: Dedup hits per second for both services
- **Dedup Hit Ratio**: Percentage of duplicate events (0-100%)

#### Consumer Lag
- **Consumer Lag (normalizer-v1)**: Total lag across all partitions
- **Consumer Lag by Partition**: Individual partition lags

#### Service Health
- **Service Status**: UP/DOWN indicators for RSS ingestor and normalizer
- **Seconds Since Last Success**: Time since last successful operation (alerts if too high)

### Prometheus Queries

You can run custom queries in Prometheus (http://localhost:9090):

#### Throughput Queries

```promql
# Raw events published per second
rate(rss_ingestor_raw_events_published_total[1m])

# Normalized events per second
rate(normalizer_normalized_events_published_total[1m])

# DLQ rate
rate(normalizer_dlq_published_total[1m])
```

#### Latency Queries

```promql
# p95 normalizer processing latency
histogram_quantile(0.95, rate(normalizer_processing_duration_seconds_bucket[5m]))

# p99 kafka produce latency (RSS ingestor)
histogram_quantile(0.99, rate(rss_ingestor_kafka_produce_duration_seconds_bucket[5m]))
```

#### Deduplication Queries

```promql
# Dedup hit ratio (RSS ingestor)
rate(rss_ingestor_dedup_hits_total[5m]) / 
(rate(rss_ingestor_dedup_hits_total[5m]) + rate(rss_ingestor_raw_events_published_total[5m]))

# Normalizer dedup hits per minute
rate(normalizer_dedup_hits_total[1m]) * 60
```

#### Consumer Lag Queries

```promql
# Total normalizer lag
sum(kafka_consumergroup_lag{topic="raw.events.v1",consumergroup="normalizer-v1"})

# Lag by partition
kafka_consumergroup_lag{topic="raw.events.v1",consumergroup="normalizer-v1"}
```

#### Service Health Queries

```promql
# Service up/down status
up{job="rss-ingestor"}
up{job="normalizer"}

# Seconds since last success
time() - rss_ingestor_last_success_timestamp
time() - normalizer_last_success_timestamp
```

### Customizing Grafana

You can customize the dashboard after it's provisioned:

1. Navigate to http://localhost:3001
2. Go to Dashboards → "Pipeline Health"
3. Click the gear icon (⚙️) → Settings
4. Add new panels, modify queries, or adjust thresholds
5. Click "Save dashboard" to persist changes

**Note:** Changes persist in the `grafana_data` Docker volume.

### Configuration

#### Changing Grafana Credentials

Edit `infra/.env` or set environment variables:

```bash
GRAFANA_ADMIN_USER=myadmin
GRAFANA_ADMIN_PASSWORD=strongpassword
```

Then restart:

```bash
docker compose --profile observability down
docker compose --profile observability up -d
```

#### Changing Ports

Edit `infra/.env`:

```bash
PROMETHEUS_PORT=9091
GRAFANA_PORT=3002
KAFKA_EXPORTER_PORT=9309
```

#### Adjusting Scrape Intervals

Edit `infra/observability/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'rss-ingestor'
    scrape_interval: 5s  # Change from 10s to 5s for more frequent scraping
```

Restart Prometheus:

```bash
docker compose restart prometheus
```

### Troubleshooting Observability

#### Issue: Prometheus Targets Down

**Symptom:** Targets show "DOWN" status in http://localhost:9090/targets

**Solutions:**

1. Verify services are running:
   ```bash
   docker compose --profile apps ps
   curl http://localhost:8001/health
   curl http://localhost:8002/health
   ```

2. Check metrics endpoints:
   ```bash
   curl http://localhost:8001/metrics
   curl http://localhost:8002/metrics
   ```

3. Check Prometheus logs:
   ```bash
   docker compose logs prometheus
   ```

4. Verify network connectivity:
   ```bash
   docker exec prometheus ping rss-ingestor
   docker exec prometheus ping normalizer
   ```

#### Issue: No Data in Grafana Dashboard

**Symptom:** Dashboard panels show "No data"

**Solutions:**

1. Wait 1-2 minutes for data to populate

2. Check Prometheus targets are UP (see above)

3. Verify Prometheus datasource:
   - Grafana → Configuration → Data Sources
   - Click "Prometheus"
   - Click "Test" button (should show "Data source is working")

4. Check if services are generating traffic:
   ```bash
   # Verify events are being produced
   docker exec -it redpanda rpk topic consume raw.events.v1 -n 1
   ```

5. Check Grafana logs:
   ```bash
   docker compose logs grafana
   ```

#### Issue: Kafka Exporter Shows No Lag Data

**Symptom:** Consumer lag panels show no data

**Solutions:**

1. Verify kafka-exporter is running:
   ```bash
   docker compose --profile observability ps kafka-exporter
   ```

2. Check kafka-exporter metrics directly:
   ```bash
   curl http://localhost:9308/metrics | grep kafka_consumergroup_lag
   ```

3. Verify consumer group exists:
   ```bash
   docker exec -it redpanda rpk group list
   docker exec -it redpanda rpk group describe normalizer-v1
   ```

4. Check kafka-exporter logs:
   ```bash
   docker compose logs kafka-exporter
   ```

#### Issue: Grafana Won't Login

**Symptom:** "Invalid username or password" error

**Solutions:**

1. Use default credentials: `admin` / `admin`

2. Reset Grafana admin password:
   ```bash
   docker compose stop grafana
   docker volume rm infra_grafana_data
   docker compose --profile observability up -d grafana
   ```

3. Check environment variables:
   ```bash
   docker compose config | grep GRAFANA
   ```

### Stopping Observability Stack

To stop only the observability stack while keeping apps running:

```bash
docker compose --profile observability down
```

To stop everything:

```bash
docker compose --profile apps --profile observability down
```

To remove all data (including metrics history):

```bash
docker compose --profile apps --profile observability down -v
```

⚠️ **Warning:** `down -v` will delete all Prometheus metrics and Grafana dashboards!

### Performance Impact

The observability stack has minimal impact on the pipeline:

- **Prometheus scraping**: ~10-15s intervals, negligible CPU/network
- **Metrics collection**: Minimal overhead (<1% CPU per service)
- **Storage**: Prometheus stores ~2-3 MB per day (default 15-day retention)
- **Grafana**: Only active when dashboard is open

**Recommendation:** Keep observability running in development for continuous monitoring.

---

## Triage Stage 1 Monitoring

### Overview

Le service **Triage Stage 1** effectue un routing déterministe des événements normalisés vers 4 buckets :
- **FAST** (score ≥ 70) : Événements prioritaires → NLP immédiat
- **STANDARD** (40-69) : Traitement normal
- **COLD** (< 40) : Batch/sampling
- **DROP_HARD** : Spam évident (< 1% typique)

### Lancement du service

```bash
# Démarrer infra + apps + observability
cd infra
docker compose --profile infra --profile apps --profile observability up -d

# Vérifier que triage-stage1 est démarré
docker compose ps triage-stage1

# Logs du service
docker compose logs -f triage-stage1
```

### Vérification des métriques

```bash
# Health check
curl http://localhost:8006/health

# Métriques Prometheus
curl http://localhost:8006/metrics | grep triage_stage1
```

### Prometheus Targets

Vérifier que **triage-stage1** apparaît en **UP** :
- URL : http://localhost:9090/targets
- Job : `triage-stage1`
- Target : `triage-stage1:8006`

### Grafana Dashboard

- **URL** : http://localhost:3001
- **Login** : admin / admin
- **Dashboard** : `Triage Stage 1`

Le dashboard contient 15 panels organisés en 4 sections :

| Section | Panels |
|---------|--------|
| Throughput & Routing | Ingest rate, Routed rate par bucket, Bucket share (%) |
| Performance & Latency | Latency p95/p50, Totals, Last success age, Status |
| Errors & Quality | Error rate, Dedup hits, DROP_HARD % |
| Score Distribution | Histogram buckets, Score percentiles |

### Requêtes PromQL Utiles

**1. Taux d'ingestion (events/sec):**
```promql
rate(triage_stage1_events_consumed_total[5m])
```

**2. Distribution par bucket (%):**
```promql
sum by(bucket) (rate(triage_stage1_events_routed_total[5m])) 
  / scalar(sum(rate(triage_stage1_events_routed_total[5m])))
```

**3. Latence p95 (secondes):**
```promql
histogram_quantile(0.95, sum(rate(triage_stage1_processing_duration_seconds_bucket[5m])) by (le))
```

**4. Taux d'erreur total:**
```promql
sum(rate(triage_stage1_events_failed_total[5m]))
```

**5. Taux de dedup (%):**
```promql
(rate(triage_stage1_dedup_hits_total[5m]) / rate(triage_stage1_events_consumed_total[5m])) * 100
```

**6. Age du dernier succès (secondes):**
```promql
time() - triage_stage1_last_success_timestamp
```

**7. Score médian (p50):**
```promql
histogram_quantile(0.50, sum(rate(triage_stage1_score_distribution_bucket[5m])) by (le))
```

### Alertes recommandées

| Métrique | Seuil | Action |
|----------|-------|--------|
| DROP_HARD % | > 2% | Vérifier config keywords/thresholds |
| Latency p95 | > 100ms | Vérifier Redis/Kafka |
| Last success age | > 300s | Service probablement DOWN |
| Error rate | > 0.1/s | Vérifier DLQ et logs |

### Troubleshooting

```bash
# Service ne démarre pas
docker compose logs triage-stage1 | tail -50

# Prometheus ne voit pas la target
curl http://triage-stage1:8006/metrics  # depuis le réseau Docker

# Pas de données dans Grafana
# 1. Vérifier que des events arrivent dans events.normalized.v1
docker exec -it redpanda rpk topic consume events.normalized.v1 --num 1

# 2. Vérifier que le consumer group consomme
docker exec -it redpanda rpk group describe triage-stage1-v1
```

---

### Acceptance Test - Observability

Run this test to verify Phase 1.2 is working:

```bash
# 1. Start everything
cd infra
docker compose --profile apps --profile observability up -d

# 2. Wait for services to be healthy
sleep 30

# 3. Check metrics endpoints
echo "Testing RSS Ingestor metrics..."
curl -s http://localhost:8001/metrics | head -5

echo "Testing Normalizer metrics..."
curl -s http://localhost:8002/metrics | head -5

# 4. Check Prometheus targets (should all be UP)
echo "Check Prometheus targets at: http://localhost:9090/targets"

# 5. Access Grafana dashboard
echo "Access Grafana at: http://localhost:3001"
echo "Login: admin / admin"
echo "Dashboard: Pipeline Health"

# 6. Wait 2-3 minutes for RSS polling and data to populate

# 7. Verify metrics in Prometheus
echo "Sample query: rate(rss_ingestor_raw_events_published_total[1m])"
```

**Expected Results:**
- ✅ All metrics endpoints return Prometheus-format data
- ✅ Prometheus shows 3/3 targets UP
- ✅ Grafana dashboard loads and shows data after 2-3 minutes
- ✅ Consumer lag panel shows lag value (0 or >0)
- ✅ All services remain healthy with observability enabled

### Metrics Best Practices

1. **Don't add high-cardinality labels**: Avoid labels with many unique values (e.g., full URLs, UUIDs)
2. **Use consistent naming**: Follow Prometheus naming conventions (e.g., `_total` suffix for counters)
3. **Set reasonable histogram buckets**: Default buckets work for most latency measurements
4. **Monitor metric cardinality**: Check metric counts in Prometheus to avoid explosion
5. **Use alerts wisely**: Set up alerting for critical thresholds (high DLQ rate, service down, high lag)

### Next Steps

With observability in place, you can:

1. **Set up alerting**: Configure Prometheus Alertmanager for critical alerts
2. **Add more dashboards**: Create service-specific or business-metric dashboards
3. **Export metrics**: Send to external monitoring systems (Datadog, New Relic, etc.)
4. **Long-term storage**: Configure Prometheus remote write for longer retention
5. **Distributed tracing**: Add OpenTelemetry for request tracing across services
