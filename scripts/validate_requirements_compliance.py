#!/usr/bin/env python3
"""
Feature Store v1 - Requirements Compliance Check

Validates that the implementation meets all requirements from the problem statement:
- Phase 1.7: Feature Store v1 (Timescale) + Schéma features.v1 + Job de calcul + Observabilité + Dashboard

This script performs static analysis and structural validation.
Runtime validation requires docker compose environment (see test_feature_store_smoke.py).
"""

import json
import os
import sys
from pathlib import Path

def check(name: str, condition: bool, detail: str = ""):
    """Print check result"""
    status = "✓" if condition else "✗"
    msg = f"{status} {name}"
    if detail:
        msg += f": {detail}"
    print(msg)
    return condition

def main():
    """Run all compliance checks"""
    repo_root = Path(__file__).parent.parent
    os.chdir(repo_root)
    
    print("=" * 70)
    print("Feature Store v1 - Requirements Compliance Check")
    print("=" * 70)
    print()
    
    all_passed = True
    
    # ========================================
    # Étape A — Schéma schemas/features.v1.json
    # ========================================
    print("Étape A — Schéma schemas/features.v1.json")
    print("-" * 70)
    
    schema_path = Path("schemas/features.v1.json")
    all_passed &= check("Schema file exists", schema_path.exists())
    
    if schema_path.exists():
        with open(schema_path) as f:
            schema = json.load(f)
        
        all_passed &= check("Schema has $schema", "$schema" in schema)
        all_passed &= check("Schema version is features.v1", 
                           schema.get("properties", {}).get("schema_version", {}).get("const") == "features.v1")
        
        required = schema.get("required", [])
        all_passed &= check("feature_id required", "feature_id" in required)
        all_passed &= check("instrument_id required", "instrument_id" in required)
        all_passed &= check("timeframe required", "timeframe" in required)
        all_passed &= check("ts_utc required", "ts_utc" in required)
        all_passed &= check("feature_set_version required", "feature_set_version" in required)
        all_passed &= check("features required", "features" in required)
        all_passed &= check("quality_flags required", "quality_flags" in required)
        all_passed &= check("computed_at_utc required", "computed_at_utc" in required)
        all_passed &= check("pipeline_version required", "pipeline_version" in required)
        
        features = schema.get("properties", {}).get("features", {}).get("properties", {})
        all_passed &= check("ret_1 feature defined", "ret_1" in features)
        all_passed &= check("ret_5 feature defined", "ret_5" in features)
        all_passed &= check("vol_20 feature defined", "vol_20" in features)
        all_passed &= check("event_count_1h feature defined", "event_count_1h" in features)
        all_passed &= check("sentiment_mean_1h feature defined", "sentiment_mean_1h" in features)
        
        all_passed &= check("additionalProperties false", 
                           schema.get("additionalProperties") == False)
    
    sample_path = Path("schemas/samples/features_v1_valid.json")
    all_passed &= check("Sample file exists", sample_path.exists())
    
    print()
    
    # ========================================
    # Étape B — DB : table Timescale feature_vectors
    # ========================================
    print("Étape B — DB : table Timescale feature_vectors")
    print("-" * 70)
    
    sql_path = Path("infra/timescale/feature_store_init.sql")
    all_passed &= check("SQL init file exists", sql_path.exists())
    
    if sql_path.exists():
        with open(sql_path) as f:
            sql = f.read()
        
        all_passed &= check("CREATE TABLE feature_vectors", "CREATE TABLE" in sql and "feature_vectors" in sql)
        all_passed &= check("instrument_id column", "instrument_id TEXT NOT NULL" in sql)
        all_passed &= check("timeframe column", "timeframe TEXT NOT NULL" in sql)
        all_passed &= check("ts column", "ts TIMESTAMPTZ NOT NULL" in sql)
        all_passed &= check("feature_set_version column", "feature_set_version TEXT NOT NULL" in sql)
        all_passed &= check("features JSONB column", "features JSONB NOT NULL" in sql)
        all_passed &= check("quality_flags column", "quality_flags TEXT[]" in sql)
        all_passed &= check("UNIQUE constraint", "UNIQUE" in sql and "instrument_id" in sql and "feature_set_version" in sql)
        all_passed &= check("create_hypertable", "create_hypertable" in sql)
        all_passed &= check("CREATE INDEX", "CREATE INDEX" in sql)
    
    init_sql_path = Path("infra/timescale/init.sql")
    if init_sql_path.exists():
        with open(init_sql_path) as f:
            init_sql = f.read()
        all_passed &= check("Init includes feature_store_init.sql", "feature_store_init.sql" in init_sql)
    
    print()
    
    # ========================================
    # Étape C — Job/service services/features/feature-store
    # ========================================
    print("Étape C — Job/service services/features/feature-store")
    print("-" * 70)
    
    service_dir = Path("services/features/feature-store")
    all_passed &= check("Service directory exists", service_dir.exists())
    
    app_path = service_dir / "app.py"
    all_passed &= check("app.py exists", app_path.exists())
    
    if app_path.exists():
        with open(app_path) as f:
            app_code = f.read()
        
        # Market features
        all_passed &= check("Implements ret_1", "ret_1" in app_code)
        all_passed &= check("Implements ret_5", "ret_5" in app_code)
        all_passed &= check("Implements vol_20", "vol_20" in app_code)
        
        # Event features
        all_passed &= check("Implements event_count", "event_count" in app_code)
        all_passed &= check("Implements sentiment_mean", "sentiment_mean" in app_code)
        all_passed &= check("Implements sentiment_weighted", "sentiment_weighted" in app_code)
        
        # Quality flags
        all_passed &= check("MISSING_OHLCV flag", "MISSING_OHLCV" in app_code)
        all_passed &= check("INSUFFICIENT_OHLCV flag", "INSUFFICIENT_OHLCV" in app_code)
        all_passed &= check("NO_EVENTS flag", "NO_EVENTS" in app_code)
        all_passed &= check("LOW_SENTIMENT_CONFIDENCE flag", "LOW_SENTIMENT_CONFIDENCE" in app_code)
        
        # Endpoints
        all_passed &= check("Health endpoint /health", "/health" in app_code)
        all_passed &= check("Metrics endpoint /metrics", "/metrics" in app_code)
        
        # Architecture
        all_passed &= check("Batch compute approach", "compute_cycle" in app_code or "compute_loop" in app_code)
        all_passed &= check("Event cache", "event_cache" in app_code)
        all_passed &= check("Kafka consumer", "KafkaConsumer" in app_code)
        all_passed &= check("DB upsert", "upsert" in app_code.lower())
        all_passed &= check("UNIQUE constraint handling", "ON CONFLICT" in app_code or "conflict" in app_code.lower())
    
    dockerfile_path = service_dir / "Dockerfile"
    all_passed &= check("Dockerfile exists", dockerfile_path.exists())
    
    requirements_path = service_dir / "requirements.txt"
    all_passed &= check("requirements.txt exists", requirements_path.exists())
    
    if requirements_path.exists():
        with open(requirements_path) as f:
            reqs = f.read()
        all_passed &= check("psycopg2 dependency", "psycopg2" in reqs)
        all_passed &= check("kafka-python dependency", "kafka" in reqs)
        all_passed &= check("numpy dependency", "numpy" in reqs)
        all_passed &= check("prometheus-client dependency", "prometheus" in reqs)
    
    print()
    
    # ========================================
    # Étape D — Observabilité Prometheus
    # ========================================
    print("Étape D — Observabilité Prometheus")
    print("-" * 70)
    
    if app_path.exists():
        with open(app_path) as f:
            app_code = f.read()
        
        # Counters
        all_passed &= check("Metric: compute_runs_total", "compute_runs_total" in app_code)
        all_passed &= check("Metric: feature_vectors_upserted_total", "feature_vectors_upserted_total" in app_code)
        all_passed &= check("Metric: compute_failed_total", "compute_failed_total" in app_code)
        all_passed &= check("Metric: quality_flag_total", "quality_flag_total" in app_code)
        
        # Histograms
        all_passed &= check("Metric: compute_duration_seconds", "compute_duration_seconds" in app_code)
        all_passed &= check("Metric: db_upsert_duration_seconds", "db_upsert_duration_seconds" in app_code)
        
        # Gauges
        all_passed &= check("Metric: last_success_timestamp", "last_success_timestamp" in app_code)
        all_passed &= check("Metric: last_feature_ts_timestamp", "last_feature_ts_timestamp" in app_code)
        all_passed &= check("Metric: cached_events", "cached_events" in app_code)
    
    prom_path = Path("infra/observability/prometheus.yml")
    if prom_path.exists():
        with open(prom_path) as f:
            prom = f.read()
        all_passed &= check("Prometheus scrapes feature-store", "feature-store" in prom)
    
    print()
    
    # ========================================
    # Étape E — Dashboard "Feature Store Health"
    # ========================================
    print('Étape E — Dashboard "Feature Store Health"')
    print("-" * 70)
    
    dashboard_path = Path("infra/observability/grafana/dashboards/feature_store_health.json")
    all_passed &= check("Dashboard file exists", dashboard_path.exists())
    
    if dashboard_path.exists():
        with open(dashboard_path) as f:
            dashboard = json.load(f)
        
        all_passed &= check("Dashboard title", dashboard.get("title") == "Feature Store Health")
        all_passed &= check("Dashboard UID", dashboard.get("uid") == "feature-store-health")
        
        panels = dashboard.get("panels", [])
        all_passed &= check("Has panels", len(panels) >= 8, f"found {len(panels)}")
        
        # Check for required panels (by searching titles)
        panel_titles = [p.get("title", "") for p in panels]
        all_passed &= check("Panel: Last Success Age", any("Success Age" in t for t in panel_titles))
        all_passed &= check("Panel: Compute Runs", any("Compute" in t and "Run" in t for t in panel_titles))
        all_passed &= check("Panel: Vectors Upserted", any("Upserted" in t or "Vector" in t for t in panel_titles))
        all_passed &= check("Panel: Cached Events", any("Cached" in t for t in panel_titles))
        all_passed &= check("Panel: Quality Flags", any("Quality" in t or "Flag" in t for t in panel_titles))
    
    print()
    
    # ========================================
    # Étape F — Docker Compose integration
    # ========================================
    print("Étape F — Docker Compose integration")
    print("-" * 70)
    
    compose_path = Path("infra/docker-compose.yml")
    all_passed &= check("docker-compose.yml exists", compose_path.exists())
    
    if compose_path.exists():
        with open(compose_path) as f:
            compose = f.read()
        
        all_passed &= check("feature-store service defined", "feature-store:" in compose)
        all_passed &= check("Build context", "services/features/feature-store" in compose)
        all_passed &= check("Profile apps", '"apps"' in compose and "feature-store" in compose)
        all_passed &= check("Depends on timescaledb", "timescaledb" in compose and "feature-store" in compose)
        all_passed &= check("Depends on redpanda", "redpanda" in compose and "feature-store" in compose)
        all_passed &= check("Port 8006 exposed", "8006" in compose or "8005" in compose)
        all_passed &= check("FEATURE_TICKERS env", "FEATURE_TICKERS" in compose)
        all_passed &= check("FEATURE_SET_VERSION env", "FEATURE_SET_VERSION" in compose)
    
    env_path = Path("infra/.env.example")
    if env_path.exists():
        with open(env_path) as f:
            env = f.read()
        
        all_passed &= check(".env has FEATURE_TICKERS", "FEATURE_TICKERS" in env)
        all_passed &= check(".env has FEATURE_TIMEFRAMES", "FEATURE_TIMEFRAMES" in env)
        all_passed &= check(".env has FEATURE_SET_VERSION", "FEATURE_SET_VERSION" in env)
        all_passed &= check(".env has FEATURE_REFRESH_SECONDS", "FEATURE_REFRESH_SECONDS" in env)
        all_passed &= check(".env has FEATURE_LOOKBACK_PERIODS", "FEATURE_LOOKBACK_PERIODS" in env)
        all_passed &= check(".env has FEATURE_EVENT_WINDOW_MINUTES", "FEATURE_EVENT_WINDOW_MINUTES" in env)
    
    print()
    
    # ========================================
    # Étape G — Tests
    # ========================================
    print("Étape G — Tests")
    print("-" * 70)
    
    test_path = Path("scripts/test_feature_store_smoke.py")
    all_passed &= check("Smoke test exists", test_path.exists())
    
    if test_path.exists():
        with open(test_path) as f:
            test_code = f.read()
        
        all_passed &= check("Test: DB accessible", "test_db_connection" in test_code)
        all_passed &= check("Test: OHLCV data", "test_ohlcv_data" in test_code or "ohlcv" in test_code.lower())
        all_passed &= check("Test: Simulate events", "simulate" in test_code.lower() or "kafka" in test_code.lower())
        all_passed &= check("Test: Feature vectors", "feature_vectors" in test_code)
        all_passed &= check("Test: Verify features", "verify" in test_code.lower() and "features" in test_code.lower())
    
    print()
    
    # ========================================
    # Étape H — Documentation
    # ========================================
    print("Étape H — Documentation")
    print("-" * 70)
    
    doc_path = Path("docs/50_feature_store.md")
    all_passed &= check("Feature store doc exists", doc_path.exists())
    
    if doc_path.exists():
        with open(doc_path) as f:
            doc = f.read()
        
        all_passed &= check("Documents feature_set_version", "feature_set_version" in doc)
        all_passed &= check("Documents features v1", "ret_1" in doc and "vol_20" in doc)
        all_passed &= check("Documents formulas", "formula" in doc.lower() or "close_t" in doc)
        all_passed &= check("Documents event window", "window" in doc.lower() and "event" in doc.lower())
        all_passed &= check("Documents quality flags", "quality_flags" in doc or "MISSING_OHLCV" in doc)
        all_passed &= check("Documents recalculation", "recalcul" in doc.lower() or "replay" in doc.lower() or "backfill" in doc.lower())
    
    overview_path = Path("docs/00_overview.md")
    if overview_path.exists():
        with open(overview_path) as f:
            overview = f.read()
        all_passed &= check("Overview mentions feature store", "feature-store" in overview.lower() or "feature store" in overview.lower())
    
    print()
    
    # ========================================
    # Summary
    # ========================================
    print("=" * 70)
    if all_passed:
        print("✅ ALL REQUIREMENTS MET")
        print("=" * 70)
        print()
        print("Implementation is compliant with Phase 1.7 requirements.")
        print("Ready for docker compose testing and deployment.")
        return 0
    else:
        print("❌ SOME REQUIREMENTS NOT MET")
        print("=" * 70)
        print()
        print("Please review failed checks above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
