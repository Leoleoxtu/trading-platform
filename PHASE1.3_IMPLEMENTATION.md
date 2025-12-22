# Phase 1.3 - Reddit Ingestor Implementation Summary

## Overview

This document summarizes the implementation of the Reddit ingestor service for the trading platform (Phase 1.3).

## What Was Implemented

### 1. Reddit Ingestor Service (`services/ingestors/reddit/`)

A new Python service that:
- Polls Reddit submissions and/or comments using PRAW (Python Reddit API Wrapper)
- Stores raw data in MinIO for immutable archival
- Publishes RawEvent v1 messages to Kafka
- Implements deduplication to avoid republishing
- Provides health and metrics endpoints
- Follows the same patterns as the existing RSS ingestor

**Key Files:**
- `app.py` - Main application with polling loop, PRAW integration, deduplication, and observability
- `requirements.txt` - Dependencies (praw, kafka-python, boto3, jsonschema, prometheus-client)
- `Dockerfile` - Container image definition

### 2. Configuration Updates

**Docker Compose (`infra/docker-compose.yml`):**
- Added `reddit-ingestor` service with profile "apps"
- Configured dependencies on Redpanda and MinIO
- Exposed port 8003 for health/metrics endpoints
- Created `reddit_ingestor_data` volume for deduplication state

**Environment Variables (`infra/.env.example`):**
```bash
REDDIT_CLIENT_ID=your_reddit_client_id_here
REDDIT_CLIENT_SECRET=your_reddit_client_secret_here
REDDIT_USER_AGENT=trading-platform-ingestor/1.0
REDDIT_SUBREDDITS=wallstreetbets,stocks,investing,cryptocurrency
REDDIT_MODE=submissions  # or comments, or both
REDDIT_POLL_SECONDS=60
REDDIT_LIMIT_PER_POLL=50
REDDIT_PRIORITY=MEDIUM
```

**Prometheus (`infra/observability/prometheus.yml`):**
- Added scraping configuration for reddit-ingestor:8000

### 3. Observability

**Grafana Dashboard Updates:**
Added 4 new panels to `pipeline_health.json`:
1. **Reddit Ingestor - Throughput**: Events published per second
2. **Reddit Ingestor - Errors**: Failures by reason (minio, kafka, schema, api)
3. **Reddit Ingestor - Dedup Hits**: Duplicate items detected
4. **Reddit Ingestor - Last Success Age**: Time since last successful poll

**Prometheus Metrics:**
- `reddit_ingestor_items_fetched_total{kind="submission|comment"}` - Items fetched
- `reddit_ingestor_raw_events_published_total` - Events published
- `reddit_ingestor_raw_events_failed_total{reason}` - Failures by reason
- `reddit_ingestor_dedup_hits_total` - Deduplication hits
- `reddit_ingestor_poll_duration_seconds` - Poll duration histogram
- `reddit_ingestor_minio_put_duration_seconds` - MinIO upload duration
- `reddit_ingestor_kafka_produce_duration_seconds` - Kafka produce duration
- `reddit_ingestor_last_success_timestamp` - Last success timestamp

### 4. Documentation

**New Documentation (`docs/15_reddit_ingestion.md`):**
- Complete service documentation (14KB)
- Configuration guide with Reddit API setup
- Operation instructions
- Troubleshooting guide
- Performance considerations
- Collection mode explanations

**Updated Documentation:**
- `README.md` - Added Reddit ingestor to access points and services list
- `scripts/test_phase1_e2e.py` - Added Reddit health and metrics checks

### 5. Testing Infrastructure

Updated end-to-end tests to include:
- Reddit ingestor health check
- Reddit metrics verification
- Optional testing (passes if service not available)

## Key Design Decisions

### 1. Deduplication Strategy
**Decision:** Use persistent JSON file storage with in-memory set
**Rationale:** 
- Matches RSS ingestor pattern for consistency
- Simple and reliable for single-instance deployment
- Survives container restarts via Docker volume
- Future: Can upgrade to Redis for distributed deployments

**Dedup Key Format:** `reddit:{kind}:{reddit_id}`
- Example: `reddit:submission:abc123` or `reddit:comment:xyz789`

### 2. Collection Modes
**Decision:** Support three modes - submissions, comments, or both
**Rationale:**
- Flexibility for different use cases
- Allows volume control (comments have higher volume)
- Can reduce API calls by only collecting what's needed

### 3. Schema Compliance
**Decision:** Strict validation against `raw_event.v1.json`
**Rationale:**
- Ensures downstream compatibility
- Fails fast on schema issues
- No modification to v1 schema (as per requirements)

### 4. Error Handling
**Decision:** Continue on individual item errors, increment metrics
**Rationale:**
- Service availability over perfect delivery
- Metrics track all failure types
- Can debug issues without service crashes

### 5. API Rate Limiting
**Decision:** Default 60-second poll interval, configurable
**Rationale:**
- Reddit allows ~60 requests/minute
- Safe default for multiple subreddits
- User can adjust based on needs

## Implementation Quality

### Code Review
✅ All feedback addressed:
- Added constants for hardcoded values (REDDIT_BASE_URL, DEFAULT_SUBREDDIT)
- Removed unnecessary hasattr() check for PRAW objects
- Added timeout to health server to prevent busy waiting
- Improved code maintainability

### Security Scan
✅ CodeQL scan passed with 0 vulnerabilities:
- No SQL injection risks
- No XSS vulnerabilities
- No hardcoded credentials
- Proper input validation

### Schema Validation
✅ Sample events validated successfully:
- Submissions produce valid RawEvent v1 messages
- Comments produce valid RawEvent v1 messages
- All required fields present and correctly formatted

### Docker Builds
✅ Both images build successfully:
- reddit-ingestor: ✓
- rss-ingestor: ✓ (verified no regression)

## Architecture Integration

```
Reddit API (PRAW)
      ↓
Reddit Ingestor
      ↓
   ┌──┴──┐
   ↓     ↓
MinIO  Kafka (raw.events.v1)
         ↓
      Normalizer
         ↓
    (downstream services)
```

**Data Flow:**
1. Poll Reddit API for new submissions/comments
2. Check deduplication (in-memory + persistent)
3. Store raw JSON in MinIO (source=reddit/dt=YYYY-MM-DD/{event_id}.json)
4. Calculate SHA-256 hash of raw content
5. Create RawEvent v1 message with metadata
6. Validate against schema
7. Publish to Kafka raw.events.v1 topic
8. Update metrics and log results

## Usage Instructions

### 1. Get Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Select "script" as the app type
4. Fill in name and redirect URI (can be http://localhost)
5. Copy the client ID (under the app name) and secret

### 2. Configure Environment

```bash
cd infra
cp .env.example .env
# Edit .env and set:
REDDIT_CLIENT_ID=your_actual_client_id
REDDIT_CLIENT_SECRET=your_actual_secret
REDDIT_SUBREDDITS=wallstreetbets,stocks,investing
```

### 3. Start Services

```bash
# Start infrastructure, apps, and observability
docker compose --profile apps --profile observability up -d

# Check Reddit ingestor logs
docker compose logs -f reddit-ingestor

# Verify health
curl http://localhost:8003/health

# Check metrics
curl http://localhost:8003/metrics
```

### 4. Monitor in Grafana

1. Open http://localhost:3001 (admin/admin)
2. Navigate to "Pipeline Health" dashboard
3. Scroll to Reddit Ingestor panels
4. Watch throughput, errors, and dedup metrics

### 5. View Events

**In Kafka UI:**
- http://localhost:8080
- Navigate to raw.events.v1 topic
- Filter by `source_type: "reddit"`

**In MinIO:**
- http://localhost:9001 (minioadmin/minioadmin123)
- Navigate to raw-events bucket
- Browse source=reddit/dt=YYYY-MM-DD/

## What's NOT Included (Future Work)

1. **Advanced Deduplication:**
   - No TTL/expiration (items remembered forever)
   - No distributed state (single-instance only)
   - Future: Redis-based deduplication with TTL

2. **Sentiment Analysis:**
   - Raw data only, no AI analysis
   - As per requirements: "no trading advice, no AI analysis in this phase"
   - Future: Separate enrichment service

3. **Historical Backfill:**
   - Only polls new/recent items
   - No ability to fetch historical data
   - Future: Separate backfill utility

4. **Rate Limit Handling:**
   - Basic retry logic only
   - No exponential backoff
   - Future: Adaptive rate limiting

5. **Multiple Instances:**
   - No coordination between replicas
   - Each instance has own dedup state
   - Future: Shared state with Redis/DB

## Testing Checklist

### Automated Tests
- [x] Python syntax validation
- [x] JSON schema validation
- [x] Docker build verification
- [x] Code review completion
- [x] CodeQL security scan
- [x] Sample event validation

### Manual Tests (Requires Credentials)
- [ ] Service starts successfully
- [ ] Health endpoint returns 200
- [ ] Metrics endpoint has all expected metrics
- [ ] Events appear in Kafka raw.events.v1
- [ ] Raw data appears in MinIO
- [ ] Deduplication works (same item not republished)
- [ ] Grafana panels show data
- [ ] Service handles Reddit API errors gracefully
- [ ] Service survives container restart with state intact

## Troubleshooting

### Service Won't Start
**Symptom:** Container exits immediately
**Solution:** Check credentials are set in .env file

### No Events Published
**Symptom:** Health is OK but no events in Kafka
**Solutions:**
- Check Reddit API credentials
- Verify subreddits exist and are public
- Check logs for API errors
- Verify network connectivity to Reddit

### High Dedup Rate
**Symptom:** Most items marked as duplicates
**Solution:** This is normal after initial run - service only publishes new items

### API Rate Limit Errors
**Symptom:** Errors with reason="api" in metrics
**Solutions:**
- Increase REDDIT_POLL_SECONDS
- Reduce number of subreddits
- Reduce REDDIT_LIMIT_PER_POLL

## Files Changed

```
services/ingestors/reddit/
  ├── app.py                    (NEW, 730 lines)
  ├── requirements.txt          (NEW)
  └── Dockerfile                (NEW)

infra/
  ├── docker-compose.yml        (MODIFIED, +74 lines)
  ├── .env.example              (MODIFIED, +9 lines)
  └── observability/
      ├── prometheus.yml        (MODIFIED, +10 lines)
      └── grafana/dashboards/
          └── pipeline_health.json  (MODIFIED, +4 panels)

docs/
  └── 15_reddit_ingestion.md    (NEW, 14KB)

scripts/
  └── test_phase1_e2e.py        (MODIFIED, +45 lines)

README.md                       (MODIFIED)
.gitignore                      (MODIFIED, +Python patterns)
```

## Metrics Summary

- **Lines of Code:** ~730 (app.py)
- **Documentation:** ~14KB (comprehensive)
- **Test Coverage:** Health checks + metrics verification
- **Security Issues:** 0 (CodeQL scan)
- **Code Review Issues:** 7 found, all addressed

## Conclusion

The Reddit ingestor service has been successfully implemented with:
- ✅ Complete functionality as per requirements
- ✅ Comprehensive documentation
- ✅ Full observability integration
- ✅ Security validation passed
- ✅ Code review feedback addressed
- ✅ Consistent with existing patterns

The service is ready for deployment and testing with valid Reddit API credentials.
