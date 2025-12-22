# Data Contract Schemas

This directory contains versioned JSON Schema definitions for all events in the trading platform pipeline.

## Overview

All events exchanged between services must conform to a versioned schema. This ensures data consistency, enables validation, and supports schema evolution.

## Schema Versioning

### Version Format

Schemas follow the naming convention: `<event_type>.v<version>.json`

Examples:
- `raw_event.v1.json` - Version 1 of raw events
- `raw_event.v2.json` - Version 2 of raw events (future)
- `normalized_event.v1.json` - Version 1 of normalized events

### Version Evolution Rules

1. **Backward Compatible Changes** (same major version):
   - Adding optional fields
   - Relaxing validation constraints
   - Adding new enum values (if consumers handle unknown values)

2. **Breaking Changes** (new major version):
   - Removing fields
   - Changing field types
   - Making optional fields required
   - Changing field semantics
   - Tightening validation constraints

### Migration Strategy

When creating a new schema version:

1. Create new schema file: `<event_type>.v<N+1>.json`
2. Create new Kafka topics: `<topic_name>.v<N+1>`
3. Update producers to support both versions during transition
4. Update consumers to support both versions
5. Migrate data gradually
6. Deprecate old version after migration complete

## Available Schemas

### raw_event.v1.json

Schema for raw events captured from various sources before normalization.

**Purpose**: Represents unprocessed events as they are ingested from external sources (RSS feeds, APIs, web scraping, etc.)

**Key Fields**:
- `event_id`: Unique UUID for the event
- `source_type`: Type of source (rss, twitter, reddit, etc.)
- `source_name`: Specific source identifier
- `raw_uri`: S3 URI where raw content is stored
- `raw_hash`: SHA-256 hash for integrity verification
- `captured_at_utc`: Ingestion timestamp
- `priority`: Processing priority (HIGH, MEDIUM, LOW)

**Topic**: `raw.events.v1`

**Storage**: Raw content stored in MinIO bucket `raw-events/`

### normalized_event.v1.json

Schema for normalized events after processing and standardization.

**Purpose**: Represents events that have been cleaned, standardized, and enriched with metadata.

**Key Fields**:
- `event_id`: Reference to original raw event UUID
- `normalized_text`: Cleaned and standardized text content
- `lang`: Detected language code (ISO 639-1)
- `dedup_key`: SHA-256 hash for deduplication
- `source_score`: Quality/reliability score (0.0 to 1.0)
- `symbols_candidates`: Extracted ticker symbols or trading pairs
- `pipeline_version`: Version of normalization pipeline

**Topic**: `events.normalized.v1`

**Deduplication**: Uses `dedup_key` to prevent processing duplicates

## Validation

### Prerequisites

Install Python dependencies:
```bash
pip install jsonschema
```

### Validate Schema Samples

From the repository root:

```bash
# Validate all samples
python scripts/validate_schema_samples.py

# Validate specific schema
python scripts/validate_schema_samples.py schemas/raw_event.v1.json samples/raw_event_valid.json
```

### Programmatic Validation

Python example:

```python
import json
import jsonschema

# Load schema
with open('schemas/raw_event.v1.json') as f:
    schema = json.load(f)

# Load event
with open('event.json') as f:
    event = json.load(f)

# Validate
try:
    jsonschema.validate(instance=event, schema=schema)
    print("✓ Event is valid")
except jsonschema.ValidationError as e:
    print(f"✗ Validation error: {e.message}")
```

## Schema Files Structure

```
schemas/
├── README.md                      # This file
├── raw_event.v1.json             # Raw event schema v1
├── normalized_event.v1.json      # Normalized event schema v1
└── samples/                      # Sample data for validation
    ├── raw_event_valid.json      # Valid raw event example
    └── normalized_event_valid.json  # Valid normalized event example
```

## Field Conventions

### Timestamps

- **Format**: RFC3339 (ISO 8601 with timezone)
- **Example**: `2024-01-15T10:30:00Z` or `2024-01-15T10:30:00+00:00`
- **Field suffix**: `_utc` indicates the timestamp is in UTC
- **Type**: `string` with `format: "date-time"`

### Identifiers

- **Event IDs**: UUID v4 format
- **Correlation IDs**: UUID v4 format for tracing across services
- **Hash values**: SHA-256 hex encoded (64 characters, lowercase hex)

### S3 URIs

- **Format**: `s3://<bucket>/<path>`
- **Example**: `s3://raw-events/source=rss/dt=2024-01-15/abc123.json`
- **Convention**: Use Hive-style partitioning for date-based organization

### Enumerations

- **Priority**: `HIGH`, `MEDIUM`, `LOW` (uppercase)
- **Source Types**: `rss`, `twitter`, `reddit`, `newsapi`, `market`, `scrape`, `finnhub`, `manual` (lowercase)

### Text Fields

- **Language codes**: ISO 639-1 (2-letter codes like `en`, `fr`)
- **Content types**: Standard MIME types (e.g., `application/json`, `text/html`)

## Dead Letter Queue (DLQ)

Events that fail validation or processing are sent to DLQ topics:

- `raw.events.dlq.v1` - Failed raw events
- `events.normalized.dlq.v1` - Failed normalization

DLQ messages should include:
- Original event payload
- Error type and message
- Failed stage identifier
- Correlation ID for debugging

## Best Practices

1. **Always validate** events before producing to Kafka
2. **Use correlation_id** for distributed tracing
3. **Store raw content** in S3/MinIO, not in Kafka messages
4. **Calculate hashes** for integrity verification and deduplication
5. **Set appropriate priority** based on content importance
6. **Include metadata** to preserve source context
7. **Handle timezones** consistently (always use UTC)
8. **Version everything** for easier debugging and rollback

## Resources

- [JSON Schema Documentation](https://json-schema.org/)
- [JSON Schema Validator](https://www.jsonschemavalidator.net/)
- [RFC3339 DateTime Format](https://datatracker.ietf.org/doc/html/rfc3339)
- [ISO 639-1 Language Codes](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes)

## Questions or Issues

If you find issues with schemas or need to propose changes, please:
1. Check if the change is backward compatible
2. Create a new version if breaking changes are needed
3. Document the migration path
4. Update all affected services
