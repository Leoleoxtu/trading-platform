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
docker exec -it redpanda rpk topic consume raw.events.v1 --num 10
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

All validations passed! ✓
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

Future development:
- Twitter/X API ingestion service
- Reddit API ingestion service  
- Market data ingestion (yfinance, Finnhub)
- Data enrichment pipeline (symbol validation, sentiment)
- Stream processing (real-time aggregations)
- Observability stack (Prometheus, Grafana) - Phase 1.2

See `docs/10_ingestion.md` and `docs/20_normalization.md` for service details.
