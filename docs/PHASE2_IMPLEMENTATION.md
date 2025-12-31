# Phase 2 - Data Collection Implementation

## ✅ Tâches Complétées

### Tâche 2.1 : Interface Abstraite Collector ✅
**Fichier** : [src/ingestion/base.py](../src/ingestion/base.py)

Interface abstraite pour tous les collectors avec :
- Classe `RawEvent` : Structure de données standard pour tous les événements
- Classe abstraite `Collector` : Interface commune pour tous les collectors
- Méthodes abstraites : `collect()`, `publish_to_kafka()`, `archive_to_minio()`
- Méthode `run_once()` : Exécution d'un cycle complet de collection

**Fonctionnalités** :
- ✅ Structure de données `RawEvent` avec sérialisation JSON
- ✅ Interface abstraite `Collector` avec méthodes obligatoires
- ✅ Gestion d'état (running/stopped)
- ✅ Cycle complet de collection avec statistiques

---

### Tâche 2.2 : RSS Collector ✅
**Fichier** : [src/ingestion/rss_collector.py](../src/ingestion/rss_collector.py)

Collector RSS complet avec toutes les fonctionnalités requises :

#### ✅ Implémenté
- [x] Chargement des sources depuis `config/rss_sources.yaml`
- [x] Parsing RSS avec `feedparser`
- [x] Publication vers Kafka topic `raw.events.v1`
- [x] Archivage dans MinIO sous `raw-events/rss/`
- [x] Déduplication avec état persistant (JSON)
- [x] Métriques Prometheus complètes :
  - `rss_collector_feeds_processed_total` (par feed, status)
  - `rss_collector_items_fetched_total` (par feed)
  - `rss_collector_items_published_total` (par status)
  - `rss_collector_fetch_duration_seconds` (histogram par feed)
  - `rss_collector_dedup_hits_total`
  - `rss_collector_active_feeds` (gauge)

#### Fonctionnalités clés
- **Gestion d'erreurs** : Retry logic, logging détaillé
- **Performance** : Traitement asynchrone, batch processing
- **Persistance** : État de déduplication sauvegardé sur disque
- **Monitoring** : Métriques Prometheus complètes
- **Scalabilité** : Configuration par fichier YAML

---

### Tâche 2.3 : Configuration RSS Sources ✅
**Fichier** : [config/rss_sources.yaml](../config/rss_sources.yaml)

Configuration complète avec 30+ sources RSS organisées par tiers :

#### Tiers de qualité
- **Tier 1** : Bloomberg, Reuters, WSJ, FT (quality: 9, priority: high)
- **Tier 2** : CNBC, MarketWatch, Barrons (quality: 8, priority: high)
- **Tier 3** : TechCrunch, The Verge (quality: 7, priority: medium)
- **Tier 4** : CoinDesk, Cointelegraph (quality: 7, priority: medium)
- **Tier 5** : Economist, Forbes (quality: 7-8, priority: medium)
- **Tier 6** : ZeroHedge, Benzinga (quality: 6-7, priority: medium)
- **Tier 7** : Sector specific (Biotech, Energy, Real Estate)
- **Tier 8** : Alternative sources (Hacker News, Reddit)

#### Catégories
- Markets, Business, Finance, Technology, Crypto, Biotech, Energy, Real Estate, Discussion

#### Configuration
- Polling interval : 300 secondes (5 minutes)
- Batch size : 100
- Timeout : 30 secondes
- Max retries : 3
- Deduplication window : 48 heures
- Archive retention : 90 jours

---

## 📦 Tests Unitaires

### test_rss_collector.py ✅
**Fichier** : [tests/unit/test_rss_collector.py](../tests/unit/test_rss_collector.py)

**10 tests complets** :
1. ✅ `test_load_config` - Chargement de la configuration
2. ✅ `test_generate_item_id` - Génération d'ID unique
3. ✅ `test_deduplication` - Détection des doublons
4. ✅ `test_dedup_state_persistence` - Persistance de l'état
5. ✅ `test_collect_events` - Collection d'événements
6. ✅ `test_collect_with_duplicates` - Filtrage des doublons
7. ✅ `test_publish_to_kafka` - Publication Kafka
8. ✅ `test_archive_to_minio` - Archivage MinIO
9. ✅ `test_run_once_integration` - Cycle complet
10. ✅ `test_error_handling_invalid_feed` - Gestion d'erreurs

**Coverage** : Toutes les fonctions principales testées avec mocks

---

## 🚀 Utilisation

### Installation des dépendances
```bash
pip install -r requirements.txt
```

### Configuration
1. Copier `.env.example` vers `.env`
2. Configurer les credentials Kafka et MinIO
3. Optionnel : Personnaliser `config/rss_sources.yaml`

### Lancer le collector
```bash
# Standalone
python examples/rss_collector_example.py

# Ou intégrer dans votre orchestrateur
```

### Exemple de code
```python
from src.ingestion.rss_collector import RSSCollector

collector = RSSCollector(
    config_path="config/rss_sources.yaml",
    kafka_bootstrap_servers="localhost:9092",
    kafka_topic="raw.events.v1",
    minio_endpoint="localhost:9000",
    minio_access_key="minioadmin",
    minio_secret_key="minioadmin123",
    minio_bucket="raw-events"
)

# Run once
stats = await collector.run_once()
print(f"Collected: {stats['collected']}, Published: {stats['published']}")
```

### Métriques Prometheus
Exposées sur `http://localhost:8000/metrics` :
```
# HELP rss_collector_items_fetched_total Total RSS items fetched
# TYPE rss_collector_items_fetched_total counter
rss_collector_items_fetched_total{feed_name="Bloomberg"} 145

# HELP rss_collector_feeds_processed_total Total feeds processed
# TYPE rss_collector_feeds_processed_total counter
rss_collector_feeds_processed_total{feed_name="Bloomberg",status="success"} 12
```

---

## 🧪 Tests

### Lancer les tests
```bash
# Tous les tests
pytest

# Tests unitaires seulement
pytest tests/unit/

# Avec coverage
pytest --cov=src --cov-report=html

# Tests spécifiques
pytest tests/unit/test_rss_collector.py -v
```

### Résultats attendus
```
tests/unit/test_rss_collector.py::test_load_config PASSED
tests/unit/test_rss_collector.py::test_generate_item_id PASSED
tests/unit/test_rss_collector.py::test_deduplication PASSED
tests/unit/test_rss_collector.py::test_dedup_state_persistence PASSED
tests/unit/test_rss_collector.py::test_collect_events PASSED
tests/unit/test_rss_collector.py::test_collect_with_duplicates PASSED
tests/unit/test_rss_collector.py::test_publish_to_kafka PASSED
tests/unit/test_rss_collector.py::test_archive_to_minio PASSED
tests/unit/test_rss_collector.py::test_run_once_integration PASSED
tests/unit/test_rss_collector.py::test_error_handling_invalid_feed PASSED

========== 10 passed in 2.34s ==========
```

---

## 📊 Architecture

```
┌─────────────────┐
│  RSS Sources    │
│  (30+ feeds)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  RSS Collector  │
│  - Parse feed   │
│  - Deduplicate  │
│  - Enrich meta  │
└────────┬────────┘
         │
         ├─────────────┐
         ▼             ▼
┌──────────────┐  ┌──────────────┐
│   Kafka      │  │   MinIO      │
│ raw.events.v1│  │ /rss/*.jsonl │
└──────────────┘  └──────────────┘
         │
         ▼
┌──────────────────┐
│  Prometheus      │
│  Metrics /metrics│
└──────────────────┘
```

---

## 📁 Structure des fichiers

```
trading-platform/
├── src/
│   ├── __init__.py
│   └── ingestion/
│       ├── __init__.py
│       ├── base.py                    ← Interface abstraite
│       └── rss_collector.py           ← RSS Collector
├── config/
│   └── rss_sources.yaml               ← Configuration sources
├── tests/
│   ├── __init__.py
│   └── unit/
│       ├── __init__.py
│       └── test_rss_collector.py      ← Tests unitaires
├── examples/
│   └── rss_collector_example.py       ← Exemple d'utilisation
├── requirements.txt                   ← Dépendances Python
└── pytest.ini                         ← Configuration pytest
```

---

## 🎯 Prochaines étapes

Phase 2 - Suite :
- [ ] Tâche 2.4 : Twitter Collector
- [ ] Tâche 2.5 : Reddit Collector
- [ ] Tâche 2.6 : News API Collector
- [ ] Tâche 2.7 : Web Scraper

---

## 📚 Références

- **feedparser** : https://feedparser.readthedocs.io/
- **aiokafka** : https://aiokafka.readthedocs.io/
- **boto3** : https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
- **prometheus_client** : https://github.com/prometheus/client_python

---

**Statut Phase 2** : 3/14 tâches complétées (21%)
**Prêt pour** : Tâche 2.4 (Twitter Collector)
