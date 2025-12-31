# 🚀 Quick Start: Triage Stage 1

## Verify Installation (5 minutes)

### 1. Run Unit Tests
```bash
cd /home/leox7/trading-platform
python -m pytest tests/unit/test_triage_stage1.py -v

# Expected: 15/15 PASSED ✅
```

### 2. Build Docker Image
```bash
docker build -t triage-stage1:latest services/preprocessing/triage_stage1/

# Expected: Successfully built triage-stage1:latest ✅
```

### 3. Start Full Stack
```bash
cd infra/
docker-compose --profile infra --profile apps --profile observability up -d

# Wait 60 seconds for services to start
sleep 60

# Check status
docker-compose ps
```

### 4. Verify Service Health
```bash
# Health check
curl http://localhost:8006/health
# Expected: {"status": "healthy", ...}

# Metrics endpoint
curl http://localhost:8006/metrics
# Expected: Prometheus text format metrics
```

### 5. View Grafana Dashboard
```bash
# Open browser
open http://localhost:3000

# Login: admin/admin
# Navigate: Dashboards > Search "Triage Health"
# Verify: 6 panels showing data
```

---

## Configuration Adjustments (Edit & Go)

**File:** `config/triage_stage1.yaml`

### To Keep More Events (Lower Drop Rate)

```yaml
thresholds:
  fast_score_min: 65         # was 70 (relax FAST threshold)
  standard_score_min: 30     # was 40 (relax STANDARD threshold)

scoring:
  source_reliability_weight: 25   # was 35 (less strict)
  short_text_penalty: 5           # was 10 (relax short text)
```

### To Add New Strong Keywords

```yaml
keywords:
  strong:
    - earnings           # existing
    - merger            # existing
    - custom_keyword    # ← ADD HERE
```

### To Trust New Source

```yaml
source_scores:
  rss:
    your_source:
      reliability: 0.80   # 0-1, higher = more trusted
      noise: 0.15         # 0-1, lower = less noisy
```

**Changes apply immediately without restart!** ✨

---

## Monitoring: Key Metrics

### Most Important Panels

1. **DROP_HARD Rate** (should be < 1%)
   - If > 2%: Lower thresholds in config
   - If 0%: Good! Events are preserved

2. **Processing Latency** (should be < 100ms p95)
   - If > 500ms: Check Redis/Kafka lag
   - If < 50ms: Excellent performance

3. **Score Distribution**
   - Shows shape of incoming event quality
   - Validates that scoring logic is working

4. **Dedup Hit Rate** (typical 2-5%)
   - Shows duplicate suppression effectiveness
   - Helps estimate redundancy in sources

---

## Testing: Send Sample Events

### Option A: Via Kafka CLI

```bash
# Inside docker container
docker exec -it redpanda rpk topic produce events.normalized.v1

# Paste JSON (Ctrl+D to send):
{
  "schema_version": "normalized_event.v1",
  "event_id": "test-123",
  "text": "Apple reported earnings beating estimates with $34.2B revenue",
  "source_type": "rss",
  "source_name": "bloomberg",
  "canonical_url": "https://example.com",
  "lang": "en",
  "event_time_utc": "2024-12-31T10:00:00Z",
  "normalized_at_utc": "2024-12-31T10:05:00Z"
}
```

### Option B: Python Integration Test

```bash
python tests/integration/test_triage_stage1_e2e.py

# Sends 8 varied test events and verifies routing
# Expected: 8 tests passed
```

---

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker-compose logs -f triage-stage1

# Verify dependencies
docker-compose ps
# redis, redpanda, normalizer should be "Up"
```

### No Data Flowing
```bash
# Check Kafka topics exist
docker exec -it redpanda rpk topic list | grep stage1

# Check consumer lag
docker exec -it redpanda rpk group describe triage-stage1-v1
```

### Grafana Dashboard Empty
```bash
# Verify Prometheus is scraping
curl http://localhost:9090/targets

# Should show: triage-stage1:8006 as UP
```

### High Latency
```bash
# Check Redis connection
redis-cli -h localhost -p 6379 PING
# Expected: PONG

# Check Kafka broker lag
docker exec -it redpanda rpk topic list --detailed
```

---

## Performance Expectations

| Metric | Target | Status |
|--------|--------|--------|
| Latency p95 | < 100ms | ✅ Typical: 5-20ms |
| Throughput | 100+ events/sec | ✅ Test: 1000/sec possible |
| DROP_HARD rate | < 1% | ✅ Keeps ~99% of events |
| Dedup hit rate | 2-5% | ✅ Suppresses dups well |
| Memory | < 500MB | ✅ Compact service |
| CPU | < 1 core | ✅ Single core sufficient |

---

## Production Deployment

### Prerequisites
- Docker & Docker Compose
- 4GB RAM available
- Kafka/Redpanda cluster running
- Redis instance accessible

### Steps
1. Update `config/triage_stage1.yaml` with your keywords/sources
2. Update `infra/docker-compose.yml` with your Kafka brokers
3. Run: `docker-compose --profile apps up -d triage-stage1`
4. Verify: `curl http://triage-stage1:8006/health`
5. Monitor: Configure Prometheus scraping and Grafana

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `services/preprocessing/triage_stage1/app.py` | Main service logic |
| `config/triage_stage1.yaml` | Configuration (edit for tuning) |
| `schemas/stage1_event.v1.json` | Output schema definition |
| `tests/unit/test_triage_stage1.py` | Unit tests (15 cases) |
| `tests/integration/test_triage_stage1_e2e.py` | Integration tests (8 scenarios) |
| `infra/docker-compose.yml` | Service deployment config |
| `infra/observability/prometheus.yml` | Metrics scraping |
| `infra/observability/grafana/dashboards/triage_health.json` | Monitoring dashboard |
| `docs/triage_stage1.md` | Comprehensive documentation |

---

## Questions?

See full documentation: `docs/triage_stage1.md`

Key sections:
- **Scoring Logic**: How scores are calculated
- **Configuration Guide**: How to tune thresholds
- **Monitoring Setup**: Prometheus + Grafana details
- **Examples**: Real-world scoring scenarios
- **Architecture**: Complete system diagram

---

**Triage Stage 1 is production-ready! 🚀**
