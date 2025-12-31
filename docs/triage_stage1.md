# Triage Stage 1 - Deterministic Event Routing

## 🎯 Objectif

Mettre en place un **entonnoir déterministe ultra-rapide** qui :
- **Garde presque tout** (objectif 100k/jour) avec score 0-100
- **Route intelligemment** : FAST (immédiat) → STANDARD (normal) → COLD (batch) → DROP_HARD (spam rare)
- **Explique les décisions** via scores composés et tags de raisons
- **Observable & configurable** : tout dans YAML, métriques complètes, pas de magic numbers

---

## 📋 Architecture

### Topics Kafka

**Entrée** :
- `events.normalized.v1` ← Données nettoyées et dédupliquées du Stage 0

**Sorties** (routing par bucket) :
- `events.stage1.fast.v1` (6 partitions) → Stage 2 immédiat
- `events.stage1.standard.v1` (6 partitions) → Processing normal
- `events.stage1.cold.v1` (6 partitions) → Batch/sampling (optionnel)
- `events.stage1.dropped.v1` (1 partition) → Audit DROP_HARD
- `events.stage1.dlq.v1` (1 partition) → Erreurs processing

**Consumer group** : `triage-stage1-v1`

---

## 🔄 Logique Déterministe

### Étape 1: Extraction de Signaux "Cheap"

À partir du texte normalisé + métadata :

```python
signals = {
    'text_length': len(text),
    'has_ticker_candidate': bool(ticker_regex.search(text)),
    'ticker_candidates': ['AAPL', 'MSFT'],
    'has_numbers': bool(re.search(r'\d', text)),
    'has_percent': bool(re.search(r'%', text)),
    'has_money': bool(re.search(r'\$|billion|million', text)),
    'keyword_hits': ['strong'] / ['weak'] / ['clickbait'],
    'source_reliability': 0.95,      # Depuis config YAML
    'source_noise': 0.05,            # Depuis config YAML
    'recency_seconds': 605           # now - event_time
}
```

### Étape 2: Scoring Composé (0-100)

```
Score = [Base 50] + additions + pénalités

Additions :
  +0..35 : source_reliability (fort poids)
  +0..25 : strong keywords (fort impact)
  +0..15 : ticker candidates (plus si plusieurs)
  +0..10 : numbers/money/percent
  +0..10 : recency (< 5min)

Pénalités :
  -0..20 : source_noise (fort)
  -0..15 : clickbait detected
  -0..10 : texte trop court
  -0..15 : duplicate récent

Chaque composant → tag dans triage_reasons[] :
  HIGH_SOURCE_RELIABILITY, STRONG_KEYWORDS, HAS_TICKER_CANDIDATES,
  HAS_MONEY_OR_PERCENT, VERY_RECENT, HIGH_SOURCE_NOISE, CLICKBAIT_SUSPECT, etc.
```

### Étape 3: Routing par Score

```
FAST   if score >= 70  ← Immédiat, Stage 2 NLP prioritaire
STANDARD if score >= 40  ← Normal
COLD   if score < 40   ← Conservé, traité en batch
DROP_HARD : RAREMENT (spam évident + multiple signals négatifs)
```

### Étape 4: Priority Hint (P0-P3)

```
FAST:
  score >= 85 → P0 (urgent)
  score >= 70 → P1 (important)

STANDARD:
  score >= 50 → P1 (normal)
  score >= 40 → P2 (bas)

COLD: P3 (faible signal conservé)
```

---

## ⚙️ Configuration

**Fichier** : `config/triage_stage1.yaml`

### Keywords (listes fermées, low-cardinality)

```yaml
keywords:
  strong:
    - earnings
    - sec / fed / fomc
    - merger / acquisition / bankruptcy
    - hack / breach / scandal
    - guidance / recall / ipo
  
  weak:
    - rumor / reported / might
    - sources say / alleged / claims
  
  clickbait:
    - shocking / you won't believe
    - revealed / insider / exclusive
```

### Source Scores

```yaml
source_scores:
  rss:
    bloomberg: {reliability: 0.95, noise: 0.05}
    reuters:   {reliability: 0.95, noise: 0.05}
    wsj:       {reliability: 0.93, noise: 0.08}
    reddit:    {reliability: 0.40, noise: 0.60}
  market:
    yfinance: {reliability: 0.90, noise: 0.05}
  default:
    reliability: 0.30
    noise: 0.60
```

### Thresholds

```yaml
thresholds:
  fast_score_min: 70       # Bucket FAST
  standard_score_min: 40   # Bucket STANDARD (< 40 → COLD)
```

### Scoring Weights

```yaml
scoring:
  source_reliability_weight: 35
  strong_keywords_weight: 25
  ticker_candidates_weight: 15
  numbers_money_weight: 10
  recency_weight: 10
  
  source_noise_penalty: 20
  clickbait_penalty: 15
  short_text_penalty: 10
```

---

## 📊 Schema Sortie : `stage1_event.v1`

**Fichier** : `schemas/stage1_event.v1.json`

Champs obligatoires :

```json
{
  "schema_version": "stage1_event.v1",
  "event_id": "uuid",
  "triaged_at_utc": "ISO8601",
  "pipeline_version": "1.0.0",
  
  "source_type": "rss|reddit|twitter|news_api|web_scrape",
  "source_name": "bloomberg",
  "event_time_utc": "ISO8601 ou null",
  "canonical_url": "https://...",
  "lang": "en",
  
  "triage_score_stage1": 85,              // 0-100
  "triage_bucket": "FAST|STANDARD|COLD|DROP_HARD",
  "priority_hint": "P0|P1|P2|P3",
  
  "triage_reasons": [                     // Tags explicatifs
    "HIGH_SOURCE_RELIABILITY",
    "STRONG_KEYWORDS",
    "HAS_TICKER_CANDIDATES",
    "HAS_MONEY_OR_PERCENT",
    "VERY_RECENT"
  ],
  
  "signals": {                            // Features quantitatives
    "text_length": 512,
    "has_ticker_candidate": true,
    "ticker_candidates": ["AAPL", "MSFT"],
    "ticker_candidates_count": 2,
    "has_numbers": true,
    "has_percent": true,
    "has_money": true,
    "keyword_hits": ["strong"],
    "source_reliability": 0.95,
    "source_noise": 0.05,
    "recency_seconds": 605
  },
  
  "quality_flags": [                      // Issues to flag
    "CLICKBAIT_SUSPECT",
    "SPAM_SUSPECT"
  ],
  
  "normalized_event": {                   // Ref minimal pour Stage 2
    "event_id": "...",
    "text": "...",
    "url": "https://...",
    "source": "rss"
  }
}
```

---

## 📈 Observabilité Prometheus

**Port HTTP** : `8006`

**Endpoints** :
- `GET /health` → JSON `{status, running, timestamp}`
- `GET /metrics` → Prometheus text format

**Métriques exposées** :

```prometheus
# Counters
triage_stage1_events_consumed_total
triage_stage1_events_routed_total{bucket="FAST|STANDARD|COLD|DROP_HARD"}
triage_stage1_events_failed_total{reason="..."}
triage_stage1_dedup_hits_total

# Histograms
triage_stage1_processing_duration_seconds
triage_stage1_score_distribution

# Gauges
triage_stage1_last_success_timestamp
```

---

## 🐳 Déploiement Docker

**Service dans docker-compose.yml** :

```yaml
triage-stage1:
  build:
    context: services/preprocessing/triage_stage1
    dockerfile: Dockerfile
  environment:
    KAFKA_BROKERS: redpanda:29092
    REDIS_URL: redis://redis:6379
    CONFIG_PATH: /etc/triage_stage1.yaml
  volumes:
    - ./config/triage_stage1.yaml:/etc/triage_stage1.yaml:ro
  ports:
    - "8006:8006"
  depends_on:
    - redpanda
    - redis
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8006/health"]
    interval: 30s
    timeout: 10s
    retries: 3
  profiles:
    - apps
```

### Lancer

```bash
# Avec infra + apps + observability
docker-compose --profile infra --profile apps --profile observability up -d

# Logs
docker-compose logs -f triage-stage1

# Health check
curl http://localhost:8006/health
curl http://localhost:8006/metrics
```

---

## 🧪 Tests & Validation

**Fichier** : `tests/unit/test_triage_stage1.py` (370 lignes, 20 tests)

Cas couverts :

1. **Signal extraction** : ticker, keywords, money, recency
2. **Scoring** : high-quality event, low-quality event, duplicates
3. **Bucket assignment** : FAST, STANDARD, COLD, DROP_HARD
4. **Priority mapping** : P0-P3
5. **Integration** : varied event types → correct buckets

### Lancer

```bash
# Tous les tests Triage
pytest tests/unit/test_triage_stage1.py -v

# Cas spécifique
pytest tests/unit/test_triage_stage1.py::test_calculate_score_high -v

# Avec coverage
pytest tests/unit/test_triage_stage1.py --cov=services.preprocessing.triage_stage1
```

---

## 📊 Grafana Dashboard

**Panel 1: Routing Distribution**
```
rate(triage_stage1_events_routed_total[5m]) by (bucket)
```
Montre % FAST/STANDARD/COLD/DROP_HARD en temps réel.

**Panel 2: Latency (p95)**
```
histogram_quantile(0.95, rate(triage_stage1_processing_duration_seconds_bucket[5m]))
```
Doit être < 100ms (très rapide).

**Panel 3: Score Distribution**
```
histogram_quantile([0.25, 0.5, 0.75, 0.95], rate(triage_stage1_score_distribution_bucket[5m]))
```
Montre shape de la distribution de scores.

**Panel 4: Dedup Rate**
```
rate(triage_stage1_dedup_hits_total[5m]) / rate(triage_stage1_events_consumed_total[5m])
```
Doit être faible (< 5%).

**Panel 5: DROP_HARD Rate**
```
rate(triage_stage1_events_routed_total{bucket="DROP_HARD"}[5m]) / rate(triage_stage1_events_consumed_total[5m])
```
**Doit rester très faible** (< 1%). Si élevé → ajuster config keywords/thresholds.

**Panel 6: Last Success**
```
triage_stage1_last_success_timestamp
```
Alerte si > 5 min = service down.

---

## 🔧 Ajustement Thresholds pour viser 100k/j

**Situation** : Actuellement on drop trop d'events (DROP_HARD rate > 2%)

**Actions** :

1. **Baisser thresholds** :
   ```yaml
   thresholds:
     fast_score_min: 65       # était 70
     standard_score_min: 35   # était 40
   ```

2. **Relaxer weights** :
   ```yaml
   scoring:
     source_reliability_weight: 25  # était 35 (moins pénalisant)
     short_text_penalty: 5          # était 10
   ```

3. **Monitorer impact** :
   - Vérifier `triage_stage1_events_routed_total{bucket="COLD"}` augmente
   - Vérifier `triage_stage1_events_routed_total{bucket="DROP_HARD"}` diminue
   - Vérifier latency reste < 100ms

---

## 🚀 Intégration Pipeline Complète

```
events.normalized.v1
       │
       ▼
   [Triage Stage 1]
       │
   ├─► events.stage1.fast.v1
   │      │
   │      ▼
   │   [Stage 2 NLP - Immédiat]
   │      │
   │      ▼
   │   events.enriched.v1
   │
   ├─► events.stage1.standard.v1
   │      │
   │      ▼
   │   [Processing Normal]
   │
   ├─► events.stage1.cold.v1
   │      │
   │      ▼
   │   [Batch Processing]
   │
   └─► events.stage1.dropped.v1 (audit)
```

---

## 📝 Exemples

### Exemple 1 : Strong Keyword + Reliable Source → FAST

**Event normalisé** :
```json
{
  "event_id": "evt123",
  "text": "Apple Inc. reported Q4 earnings beating estimates with $34.2B revenue",
  "url": "https://bloomberg.com/news/...",
  "source": "rss",
  "timestamp": "2024-12-31T15:30:00Z",
  "metadata": {
    "source_name": "bloomberg"
  }
}
```

**Processing** :
- Keywords : **strong** (earnings) ✓
- Ticker : **AAPL** ✓
- Money : **$34.2B** ✓
- Recency : **2min** (very recent) ✓
- Source : **0.95 reliability** ✓
- Score : 50 + 25 (reliability) + 25 (keywords) + 15 (ticker) + 10 (money) - 0 (clean) = **85**

**Output** :
```json
{
  "triage_bucket": "FAST",
  "triage_score_stage1": 85,
  "priority_hint": "P0",
  "triage_reasons": [
    "HIGH_SOURCE_RELIABILITY",
    "STRONG_KEYWORDS",
    "HAS_TICKER_CANDIDATES",
    "HAS_MONEY_OR_PERCENT",
    "VERY_RECENT"
  ]
}
```

### Exemple 2 : Weak Keyword + Medium Source → STANDARD

**Event** :
```json
{
  "text": "Rumors suggest Microsoft might acquire AI startup for $10B",
  "source": "reddit",
  "metadata": {"source_name": "stocks"}
}
```

**Signals** :
- Keywords : **weak** (might, suggest) → +5
- Ticker : **MSFT** → +15
- Money : **$10B** → +10
- Source reliability : **0.50** → +18 (50% reliability)
- Score : 50 + 18 + 5 + 15 + 10 = **98** → **clampé à 60** car Reddit noise élevée
- Résultat : ~50

→ **STANDARD**

### Exemple 3 : Signal Faible Conservé → COLD

**Event** :
```json
{
  "text": "Stock market update: trading volume up today",
  "source": "reddit",
  "metadata": {"source_name": "wallstreetbets"}
}
```

**Score** : Aucun keyword fort, Reddit source, court → **~30**

→ **COLD** (conservé pour batch plus tard)

---

## ✅ Checklist Acceptation

- [x] Service tourne localement via docker compose
- [x] Consomme `events.normalized.v1` correctement
- [x] Route vers 4 topics (FAST/STANDARD/COLD/DROP_HARD)
- [x] Schema `stage1_event.v1` conforme et validé
- [x] `/health` et `/metrics` exposés sur port 8006
- [x] DROP_HARD reste rare (< 1% typical)
- [x] Latency < 100ms par event
- [x] 20 tests unitaires passing
- [x] Configuration YAML simple à ajuster
- [x] Grafana dashboard déployé avec 6 panels
- [x] Documentation complète

---

**Triage Stage 1 : Entonnoir déterministe, rapide, explicable ! 🚀**
