# 📊 Flux du Pipeline de Trading - Vue d'ensemble

## Architecture Globale

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SOURCES DE DONNÉES                               │
├──────────────┬──────────────┬──────────────┬─────────────────────────────┤
│  RSS Feeds   │    Reddit    │  Market Data │      (Twitter/News API)     │
│   (60 sec)   │   (120 sec)  │   (300 sec)  │       (optionnel)           │
└──────┬───────┴──────┬───────┴──────┬───────┴─────────────────────────────┘
       │              │              │
       ▼              ▼              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     KAFKA: events.raw.v1                                  │
│                   (Événements bruts non traités)                          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │   NORMALIZER     │
                    │   (temps réel)   │
                    └─────────┬────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                   KAFKA: events.normalized.v1                             │
│              (Événements nettoyés et dédupliqués)                         │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │ TRIAGE STAGE 1   │
                    │ (déterministe)   │
                    └─────────┬────────┘
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
    [FAST Topic]      [STANDARD Topic]    [COLD Topic]
         │                   │                  │
         └───────────┬───────┘                  │
                     ▼                          │
          ┌──────────────────┐                  │
          │ TRIAGE STAGE 2   │                  │
          │  (NLP + AI)      │                  │
          └─────────┬────────┘                  │
                    │                           │
                    ▼                           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    KAFKA: events.triaged.v1                               │
│         (Événements enrichis avec NER + Sentiment + Score)                │
└──────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                    [Prêt pour AI Agents]
```

---

## 📥 Phase 1 : INGESTION (Collecte des Données)

### 🌐 RSS Collector
- **Fréquence** : 60 secondes
- **Sources** : Bloomberg, Reuters, TechCrunch, etc.
- **But** : Collecter les actualités financières en temps réel
- **Output** : `events.raw.v1`
- **Métriques** : 
  - Items collectés/min
  - Erreurs de fetch
  - Dernière collecte réussie

### 🔴 Reddit Collector
- **Fréquence** : 120 secondes
- **Sources** : r/wallstreetbets, r/stocks, r/investing
- **But** : Capturer le sentiment retail et les discussions
- **Output** : `events.raw.v1`
- **Filtre** : Posts avec score > 50

### 📈 Market Data Collector
- **Fréquence** : 300 secondes (5 min)
- **Sources** : yfinance (actuellement avec problèmes API)
- **But** : Collecter OHLCV (Open, High, Low, Close, Volume)
- **Output** : TimescaleDB directement
- **Tickers** : AAPL, MSFT, TSLA (configurable)

---

## 🧹 Phase 2 : NORMALISATION

### Normalizer
- **Fréquence** : Temps réel (streaming)
- **Input** : `events.raw.v1`
- **Output** : `events.normalized.v1`
- **Opérations** :
  - ✓ Nettoyage HTML
  - ✓ Normalisation Unicode
  - ✓ Suppression URLs
  - ✓ Timestamp → UTC
  - ✓ Déduplication (BloomFilter Redis)
  - ✓ Détection langue (langdetect)
  - ✓ Extraction symboles tickers ($AAPL, etc.)

**Latence moyenne** : ~50-100ms par événement

---

## 🎯 Phase 3 : TRIAGE (Filtrage Intelligent)

### Triage Stage 1 - Filtre Déterministe Rapide
- **Fréquence** : Temps réel (streaming)
- **Input** : `events.normalized.v1`
- **Output** : 3 topics
  - `events.stage1.fast.v1` → Urgent
  - `events.stage1.standard.v1` → Normal
  - `events.stage1.cold.v1` → Signal faible (à traiter en batch)

**Scoring (0-100 points)** :
- **+35 pts max** : Source fiable (Bloomberg > TechCrunch)
- **+25 pts max** : Mots-clés forts (earnings, SEC, Fed, merger)
- **+15 pts max** : Présence tickers validés
- **+10 pts max** : Montants/Pourcentages détectés
- **+10 pts max** : Récence de l'événement
- **-20 pts max** : Pénalités (clickbait, source bruyante)

**Buckets** :
- `FAST` : score ≥ 70 OU keyword critique (SEC/Fed/hack)
- `STANDARD` : score ≥ 50
- `COLD` : score < 50 (conservé pour analyse)
- `DROP_HARD` : spam évident uniquement

**Latence moyenne** : ~10-20ms par événement

---

### Triage Stage 2 - Enrichissement NLP
- **Fréquence** : Temps réel (streaming)
- **Input** : `events.stage1.fast.v1` + `events.stage1.standard.v1`
- **Output** : `events.triaged.v1`

**Traitements NLP** :
1. **Named Entity Recognition (spaCy)** :
   - Extraction : ORG, PERSON, PRODUCT
   - Extraction : MONEY, PERCENT (regex fallback)
   - Modèles : en_core_web_sm (EN) + fr_core_news_sm (FR)

2. **Analyse Sentiment (FinBERT)** :
   - Score : -1 (très négatif) à +1 (très positif)
   - Confidence : 0 à 1
   - Modèle : ProsusAI/finbert (optimisé finance)

3. **Validation Tickers** :
   - Whitelist : 53 tickers configurés
   - Cross-référence avec entités ORG extraites

**Scoring Final (0-100)** :
- **+30 pts max** : Keywords impact (earnings/regulation/macro)
- **+25 pts max** : Qualité source (hérité Stage 1)
- **+20 pts max** : Tickers validés avec confiance
- **+10 pts max** : Force des entités extraites
- **+15 pts max** : Magnitude sentiment × confiance

**Priorités attribuées** :
- **P0** : score ≥ 80 → Ultra urgent
- **P1** : score ≥ 60 → Urgent
- **P2** : score ≥ 40 → Important
- **P3** : score < 40 → Signal faible

**Latence moyenne** : ~500-1000ms par événement (NLP lourd)

---

## 📊 Phase 4 : FEATURE ENGINEERING

### Feature Store
- **Fréquence** : 60 secondes
- **Input** : 
  - TimescaleDB (OHLCV)
  - Kafka `events.enriched.v1` (événements)
- **Output** : PostgreSQL (features calculées)

**Features Calculées** :
- **Techniques** :
  - RSI (14 périodes)
  - MACD (12, 26, 9)
  - Bollinger Bands
  - ATR (Average True Range)
  - VWAP (1h, 1d)

- **Événementielles** :
  - Nombre news récentes (1h, 24h)
  - Sentiment moyen glissant
  - Vélocité des mentions

**Latence** : Calculs en batch toutes les 60s

---

## 🔄 Flux de Données Détaillé

```
1. RSS Collector (60s)
   └─> Kafka: events.raw.v1 [10 partitions]
       └─> Archive MinIO: raw-events/rss/

2. Normalizer (temps réel)
   └─> Redis: Déduplication (BloomFilter)
   └─> Kafka: events.normalized.v1 [10 partitions]

3. Triage Stage 1 (temps réel)
   └─> Redis: Cache dedup récents
   └─> Kafka: events.stage1.{fast|standard|cold}.v1 [6 partitions chacun]

4. Triage Stage 2 (temps réel sur FAST+STANDARD)
   └─> Redis: VIX/Régime marché
   └─> Kafka: events.triaged.v1 [6 partitions]
   └─> DLQ: events.triaged.dlq.v1 (erreurs)

5. Feature Store (60s)
   └─> TimescaleDB: Lectures OHLCV
   └─> PostgreSQL: Écriture features
   └─> Redis: Cache features récentes
```

---

## 📈 Métriques et Observabilité

### Dashboards Grafana Disponibles

1. **Pipeline Health** : Vue d'ensemble flux
   - Throughput (events/sec) par étape
   - Latence p95 de chaque composant
   - Taux d'erreurs / DLQ

2. **Triage Stage 1** : Filtre déterministe
   - Distribution FAST/STANDARD/COLD
   - Score distribution (histogram)
   - Dedup hits rate
   - Last success age

3. **Triage Stage 2 - NLP Pipeline** : 
   - Events consommés vs triés
   - Distribution priorités P0/P1/P2/P3
   - Sentiment drift (moyenne mobile)
   - DLQ rate
   - Latence NLP p95

4. **Market Health** :
   - Candles upserted (TimescaleDB)
   - Fetch errors par ticker
   - Last candle timestamp

5. **Feature Store Health** :
   - Compute runs/min
   - Features vectors upserted
   - Quality flags raised
   - Compute latency p95

---

## ⚡ Performances Actuelles

| Composant | Latence | Throughput | État |
|-----------|---------|------------|------|
| RSS Collector | ~1-2s | 100-200 items/min | ✅ OK |
| Reddit Collector | ~1-3s | 20-50 posts/min | ✅ OK |
| Normalizer | ~50ms | 1000+ events/sec | ✅ OK |
| Triage Stage 1 | ~15ms | 2000+ events/sec | ✅ OK |
| Triage Stage 2 | ~800ms | 100 events/sec | ✅ OK (NLP lourd) |
| Market Ingestor | N/A | 0 (API bloquée) | ⚠️ Yahoo Finance problème |
| Feature Store | ~2s | 1 compute/min | ✅ OK |

---

## 🎯 Objectifs de Performance

| Métrique | Cible | Actuel |
|----------|-------|--------|
| Latence end-to-end (RSS→Triaged) | < 5s | ~2-3s ✅ |
| Throughput total | 100k events/jour | ~10k/jour 📊 |
| Taux de réussite | > 99% | ~95% ⚠️ |
| DLQ rate | < 1% | ~3% ⚠️ |

---

## 🔧 Configuration et Ajustements

### Fichiers de Configuration Clés

1. **`config/rss_sources.yaml`** : Sources RSS et leurs priorités
2. **`config/triage_stage1.yaml`** : Keywords, seuils, source scores
3. **`config/triage_stage2.yaml`** : Config NLP, keywords impact
4. **`config/tickers_whitelist.csv`** : Liste des tickers surveillés

### Ajuster les Seuils

**Triage Stage 1** (`config/triage_stage1.yaml`):
```yaml
thresholds:
  fast: 70      # FAST si score ≥ 70
  standard: 50  # STANDARD si score ≥ 50
  # < 50 = COLD
```

**Triage Stage 2** (`config/triage_stage2.yaml`):
```yaml
thresholds:
  baseline:
    P0: 80  # Ultra urgent
    P1: 60  # Urgent
    P2: 40  # Important
    # < 40 = P3
```

---

## 🚀 Prochaines Étapes (Phase 3+)

1. **NewsCards AI** : LLM pour structurer événements
2. **Scenario Builder** : Générer scénarios de trading
3. **Decision Engine** : LangGraph pour décisions
4. **Risk Management** : Gates de contrôle risque
5. **Execution** : Interface Interactive Brokers

---

## 📞 Support et Monitoring

**Accès aux dashboards** :
- Grafana : http://localhost:3001 (admin/admin)
- Kafka UI : http://localhost:8080
- MinIO Console : http://localhost:9001

**Ports des services** :
- RSS Ingestor : 8001
- Normalizer : 8002
- Triage Stage 1 : 8006
- Triage Stage 2 : 8009
- Market Ingestor : 8004
- Feature Store : 8007
- Prometheus : 9090

**Métriques endpoints** : `http://localhost:<port>/metrics`

---

## 🐛 Problèmes Connus

1. **Market Ingestor** : Yahoo Finance API bloquée → Nécessite alternative (Polygon/Alpha Vantage)
2. **Triage Stage 1** : Affiche "DEGRADED" si pas d'événements depuis 60s (comportement normal)
3. **Feature Store** : Dépend des données market → Impacté par problème Market Ingestor

---

**Dernière mise à jour** : 2025-12-31
**Version Pipeline** : v1.0.0
