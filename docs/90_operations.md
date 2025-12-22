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

Edit `infra/.env`:
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

## Next Steps

After verifying the infrastructure works:

1. Develop data ingestion services (RSS, Twitter, Reddit, Market, Finnhub)
2. Develop normalization service to process raw → normalized events
3. Set up monitoring and observability (Prometheus, Grafana)
4. Implement data enrichment pipelines
5. Build analytics and visualization layer

See `docs/00_overview.md` for architecture details.
