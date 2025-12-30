# Guide Grafana & Prometheus - Trading Platform

Guide complet pour visualiser et analyser vos données de la plateforme de trading.

---

## 📊 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Accéder aux interfaces](#accéder-aux-interfaces)
3. [Prometheus : Requêtes et Métriques](#prometheus-requêtes-et-métriques)
4. [Grafana : Dashboards et Visualisations](#grafana-dashboards-et-visualisations)
5. [Métriques Principales par Service](#métriques-principales-par-service)
6. [Exemples de Requêtes Utiles](#exemples-de-requêtes-utiles)
7. [Troubleshooting](#troubleshooting)

---

## 🎯 Vue d'ensemble

### Architecture de Monitoring

```
Services (RSS, Reddit, Market, NLP, Feature Store)
        ↓ (exposent /metrics)
   Prometheus (collecte toutes les 5s)
        ↓ (stocke time-series)
   Grafana (visualise)
        ↓
   Dashboards & Alertes
```

### Services Monitorés

| Service | Port | Endpoint Metrics | Description |
|---------|------|------------------|-------------|
| RSS Ingestor | 8001 | `/metrics` | Ingestion flux RSS |
| Normalizer | 8002 | `/metrics` | Normalisation des événements |
| Reddit Ingestor | 8003 | `/metrics` | Ingestion Reddit |
| Market Ingestor | 8004 | `/metrics` | Données de marché (OHLCV) |
| NLP Enricher | 8005 | `/metrics` | Enrichissement NLP |
| Feature Store | 8006 | `/metrics` | Feature vectors |
| Kafka Exporter | 9308 | `/metrics` | Métriques Kafka/Redpanda |

---

## 🚀 Accéder aux Interfaces

### Prometheus

**URL** : http://localhost:9090

- Pas d'authentification requise
- Interface simple pour requêter les métriques
- Idéal pour debug et exploration rapide

### Grafana

**URL** : http://localhost:3001

**Credentials** :
- Username : `admin`
- Password : `admin`

**Fonctionnalités** :
- Dashboards visuels
- Alertes configurables
- Exploration interactive des données

---

## 📈 Prometheus : Requêtes et Métriques

### Interface Prometheus

1. Ouvrir http://localhost:9090
2. Barre de recherche en haut : **"Expression"**
3. Taper une métrique → Cliquer **"Execute"**
4. Choisir l'onglet **"Graph"** ou **"Table"**

### Types de Métriques

#### 1. **Counter** (compteur qui ne fait qu'augmenter)
```promql
# Exemples
rss_ingestor_items_fetched_total
nlp_enricher_events_enriched_total
feature_store_feature_vectors_upserted_total
```

#### 2. **Gauge** (valeur instantanée)
```promql
# Exemples
feature_store_cached_events
market_ingestor_last_success_timestamp
```

#### 3. **Histogram** (distribution de valeurs)
```promql
# Exemples
normalizer_processing_duration_seconds_bucket
market_ingestor_fetch_duration_seconds_bucket
```

### Requêtes de Base

#### Voir toutes les métriques d'un service
```promql
{job="rss-ingestor"}
```

#### Vérifier les services actifs
```promql
up
```

#### Calculer un taux (rate)
```promql
# Items RSS par seconde
rate(rss_ingestor_items_fetched_total[5m])
```

#### Agrégation
```promql
# Total de tous les services actifs
sum(up)

# Moyenne des durées de processing
avg(rate(normalizer_processing_duration_seconds_sum[5m]))
```

### Opérateurs Utiles

```promql
# Addition
rss_ingestor_items_fetched_total + 100

# Filtrage par label
up{job="rss-ingestor"}

# Regex
up{job=~".*ingestor"}

# Différence entre deux métriques
nlp_enricher_events_consumed_total - nlp_enricher_events_enriched_total
```

---

## 🎨 Grafana : Dashboards et Visualisations

### Menu Principal

```
┌─────────────────────────┐
│ [≡] Grafana             │
│ ├─ 🏠 Home              │  ← Page d'accueil
│ ├─ 📊 Dashboards        │  ← Liste des dashboards
│ ├─ 🧭 Explore           │  ← Requêtes ad-hoc
│ ├─ 🔔 Alerting          │  ← Gestion des alertes
│ ├─ ⚙️  Configuration    │  ← Datasources, users, etc.
│ └─ ...                  │
└─────────────────────────┘
```

### Dashboards Disponibles

#### 1. **Trading Platform - Quick Start**
- Vue d'ensemble rapide
- Services actifs
- Métriques clés (RSS, NLP, Features)
- Taux de traitement en temps réel

#### 2. **Pipeline Health**
- Santé des ingestors (RSS, Reddit)
- Performance du Normalizer
- Enrichissement NLP
- Deduplication stats

#### 3. **Market Health**
- Données OHLCV ingérées
- Latence des fetch Yahoo Finance
- Candles manquants
- Fraîcheur des données

#### 4. **Feature Store Health**
- Feature vectors calculés
- Événements en cache
- Latence des calculs
- Quality flags

---

## 🔍 Mode Explore (Grafana)

### Comment Utiliser Explore

1. **Menu gauche** → Cliquer sur **🧭 Explore**
2. **Data source** (en haut) → Sélectionner **"Prometheus"**
3. **Metric browser** → Cliquer pour voir toutes les métriques
4. Taper votre requête → **Run query**

### Fonctionnalités Explore

```
┌─────────────────────────────────────────────────┐
│ Data source: [Prometheus ▼]                    │
│                                                  │
│ Metric: [rss_ingestor_items_fetched_total]     │
│ [+ Add query] [Run query]                      │
│                                                  │
│ ┌──────────────────────────────────────────┐   │
│ │  📈 Graphique                            │   │
│ │                                          │   │
│ │  7585 ────────────────                  │   │
│ │            /                             │   │
│ │         /                                │   │
│ │     /                                    │   │
│ │  ──/                                     │   │
│ └──────────────────────────────────────────┘   │
│                                                  │
│ [Table] [JSON] [Stats] [Logs]                  │
└─────────────────────────────────────────────────┘
```

### Astuces Explore

- **Shift + Enter** : Exécuter la requête
- **Ctrl + Space** : Auto-complétion
- **Cliquer sur une métrique** : Voir les détails
- **Inspector** : Voir la requête brute et les données JSON

---

## 📊 Métriques Principales par Service

### 1. RSS Ingestor

```promql
# Items récupérés (total cumulé)
rss_ingestor_items_fetched_total

# Taux de fetch (items/seconde)
rate(rss_ingestor_items_fetched_total[5m])

# Events publiés avec succès
rss_ingestor_raw_events_published_total

# Dedup hits (items déjà vus)
rss_ingestor_dedup_hits_total

# Durée des polls RSS
rate(rss_ingestor_poll_duration_seconds_sum[5m]) / 
rate(rss_ingestor_poll_duration_seconds_count[5m])
```

### 2. Normalizer

```promql
# Events consommés
normalizer_raw_events_consumed_total

# Events normalisés et publiés
normalizer_normalized_events_published_total

# Dedup rate
rate(normalizer_dedup_hits_total[5m])

# Durée moyenne de processing (ms)
rate(normalizer_processing_duration_seconds_sum[5m]) / 
rate(normalizer_processing_duration_seconds_count[5m]) * 1000

# Taux d'erreurs (DLQ)
rate(normalizer_dlq_published_total[5m])
```

### 3. NLP Enricher

```promql
# Events enrichis
nlp_enricher_events_enriched_total

# Taux d'enrichissement
rate(nlp_enricher_events_enriched_total[5m])

# Distribution des catégories
nlp_enricher_category_total

# Sentiment moyen
nlp_enricher_sentiment_mean

# Durée de processing NLP
histogram_quantile(0.95, rate(nlp_enricher_processing_duration_seconds_bucket[5m]))

# Events à faible confiance
nlp_enricher_low_confidence_total
```

### 4. Market Ingestor

```promql
# Candles insérés
market_ingestor_candles_upserted_total

# Taux d'insertion par timeframe
sum by(timeframe) (rate(market_ingestor_candles_upserted_total[5m]))

# Erreurs de fetch
market_ingestor_fetch_failed_total

# Durée des fetch (p95)
histogram_quantile(0.95, rate(market_ingestor_fetch_duration_seconds_bucket[5m]))

# Candles manquants détectés
market_ingestor_missing_candles_detected_total

# Fraîcheur des données (secondes depuis dernier succès)
time() - market_ingestor_last_success_timestamp
```

### 5. Feature Store

```promql
# Feature vectors calculés
feature_store_feature_vectors_upserted_total

# Events en cache
feature_store_cached_events

# Taux de calcul
rate(feature_store_compute_runs_total[5m])

# Durée de calcul (p95)
histogram_quantile(0.95, rate(feature_store_compute_duration_seconds_bucket[5m]))

# Erreurs de calcul
rate(feature_store_compute_failed_total[5m])

# Quality flags
feature_store_quality_flag_total
```

### 6. Reddit Ingestor

```promql
# Items récupérés (submissions/comments)
reddit_ingestor_items_fetched_total

# Events publiés
reddit_ingestor_raw_events_published_total

# Dedup hits
reddit_ingestor_dedup_hits_total

# Durée des polls
rate(reddit_ingestor_poll_duration_seconds_sum[5m]) / 
rate(reddit_ingestor_poll_duration_seconds_count[5m])
```

---

## 🎓 Exemples de Requêtes Utiles

### Santé Globale

```promql
# Nombre de services actifs
count(up == 1)

# Services en erreur
up{job=~".*ingestor|.*enricher|normalizer|feature-store"} == 0

# Uptime (secondes)
time() - process_start_time_seconds
```

### Throughput (Débit)

```promql
# Total d'events dans le pipeline (par seconde)
sum(rate(rss_ingestor_raw_events_published_total[5m])) +
sum(rate(reddit_ingestor_raw_events_published_total[5m]))

# Throughput du normalizer
rate(normalizer_normalized_events_published_total[5m])

# Throughput du NLP enricher
rate(nlp_enricher_events_enriched_total[5m])
```

### Latence

```promql
# Latence moyenne du normalizer (ms)
rate(normalizer_processing_duration_seconds_sum[5m]) / 
rate(normalizer_processing_duration_seconds_count[5m]) * 1000

# P50, P95, P99 de la durée de fetch market
histogram_quantile(0.50, rate(market_ingestor_fetch_duration_seconds_bucket[5m]))
histogram_quantile(0.95, rate(market_ingestor_fetch_duration_seconds_bucket[5m]))
histogram_quantile(0.99, rate(market_ingestor_fetch_duration_seconds_bucket[5m]))
```

### Erreurs et DLQ

```promql
# Taux d'erreur normalizer
rate(normalizer_dlq_published_total[5m]) / 
rate(normalizer_raw_events_consumed_total[5m]) * 100

# Taux d'erreur NLP
rate(nlp_enricher_dlq_published_total[5m]) / 
rate(nlp_enricher_events_consumed_total[5m]) * 100

# Total erreurs dans le pipeline
sum(rate(normalizer_dlq_published_total[5m])) +
sum(rate(nlp_enricher_dlq_published_total[5m]))
```

### Deduplication

```promql
# Taux de dedup RSS (%)
rate(rss_ingestor_dedup_hits_total[5m]) / 
rate(rss_ingestor_items_fetched_total[5m]) * 100

# Taux de dedup Normalizer
rate(normalizer_dedup_hits_total[5m]) / 
rate(normalizer_raw_events_consumed_total[5m]) * 100

# Total dedups dans le pipeline
sum(rate(rss_ingestor_dedup_hits_total[5m])) +
sum(rate(normalizer_dedup_hits_total[5m]))
```

### Qualité des Données

```promql
# Ratio events enrichis / events normalisés
rate(nlp_enricher_events_enriched_total[5m]) / 
rate(normalizer_normalized_events_published_total[5m])

# Sentiment moyen (entre -1 et 1)
nlp_enricher_sentiment_mean

# Events à faible confiance NLP (%)
rate(nlp_enricher_low_confidence_total[5m]) / 
rate(nlp_enricher_events_enriched_total[5m]) * 100
```

---

## 🛠️ Créer vos Propres Dashboards

### Étape 1 : Créer un Dashboard

1. **Dashboards** → **New** → **New Dashboard**
2. **Add visualization**
3. Sélectionner **Prometheus** comme data source

### Étape 2 : Ajouter un Panel

#### Panel "Stat" (Nombre)

```
Query: rss_ingestor_items_fetched_total
Title: RSS Items Fetched
Type: Stat
```

#### Panel "Time series" (Graphique)

```
Query: rate(nlp_enricher_events_enriched_total[5m])
Title: NLP Enrichment Rate
Type: Time series
Legend: {{service}}
```

#### Panel "Gauge" (Jauge)

```
Query: count(up == 1)
Title: Active Services
Type: Gauge
Min: 0
Max: 10
```

### Étape 3 : Variables de Dashboard

Créer des variables pour filtrer dynamiquement :

```
Variable name: service
Query: label_values(up, service)
Type: Query
```

Utiliser dans une requête :
```promql
up{service="$service"}
```

---

## 🔔 Alertes Prometheus

### Exemple de Règles d'Alerte

Créer un fichier `alerts.yml` :

```yaml
groups:
  - name: trading-platform
    interval: 30s
    rules:
      # Service down
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.service }} is down"
          
      # High error rate
      - alert: HighErrorRate
        expr: rate(normalizer_dlq_published_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate in normalizer"
          
      # Stale data
      - alert: StaleMarketData
        expr: (time() - market_ingestor_last_success_timestamp) > 600
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Market data is stale (> 10 min)"
```

---

## 🆘 Troubleshooting

### Problème : Pas de Données dans Prometheus

**Diagnostic** :
```bash
# 1. Vérifier que les services exposent /metrics
curl http://localhost:8001/metrics | head -20

# 2. Vérifier les targets Prometheus
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool

# 3. Vérifier les logs Prometheus
docker compose logs prometheus --tail 50
```

**Solutions** :
- Vérifier que les services sont en `healthy`
- Vérifier `prometheus.yml` : scrape configs
- Redémarrer Prometheus : `docker compose restart prometheus`

### Problème : Grafana Affiche "No Data"

**Diagnostic** :
```bash
# 1. Tester depuis Grafana → Prometheus
docker compose exec grafana wget -qO- http://prometheus:9090/api/v1/query?query=up

# 2. Vérifier la datasource
# Grafana → Configuration → Data sources → Prometheus → Save & Test
```

**Solutions** :
- Vérifier que data source = **"Prometheus"** (pas "-- Grafana --")
- URL de la datasource : `http://prometheus:9090`
- Vérifier les logs : `docker compose logs grafana --tail 50`
- Redémarrer Grafana : `docker compose restart grafana`

### Problème : Graphiques Vides dans Dashboard

**Causes possibles** :
1. **Pas assez de données** : Attendre 2-3 minutes
2. **Mauvaise time range** : Changer à "Last 1 hour"
3. **Requête incorrecte** : Tester dans Explore d'abord
4. **Service pas actif** : Vérifier `docker compose ps`

---

## 📚 Ressources Utiles

### Documentation Officielle

- **Prometheus** : https://prometheus.io/docs/
- **Grafana** : https://grafana.com/docs/
- **PromQL** : https://prometheus.io/docs/prometheus/latest/querying/basics/

### PromQL Cheatsheet

```promql
# Sélecteurs
{job="rss-ingestor"}               # Exact match
{job=~".*ingestor"}                # Regex
{job!="kafka-exporter"}            # Not equal

# Fonctions de temps
rate(metric[5m])                   # Taux par seconde
increase(metric[1h])               # Augmentation sur 1h
delta(metric[5m])                  # Delta sur 5 min

# Agrégation
sum(metric)                        # Somme
avg(metric)                        # Moyenne
max(metric)                        # Maximum
count(metric)                      # Comptage

# Groupement
sum by(service) (metric)           # Grouper par service
avg without(instance) (metric)     # Exclure instance

# Opérateurs
metric1 + metric2                  # Addition
metric1 / metric2 * 100            # Pourcentage
metric > 100                       # Filtre
```

### Raccourcis Clavier Grafana

| Raccourci | Action |
|-----------|--------|
| `g + h` | Go to Home |
| `g + d` | Go to Dashboards |
| `g + e` | Go to Explore |
| `Ctrl + S` | Save dashboard |
| `Ctrl + K` | Open search |
| `Shift + Enter` | Run query (Explore) |

---

## 🎯 Checklist Rapide

### Monitoring Quotidien

- [ ] Vérifier que tous les services sont `up`
- [ ] Vérifier le throughput (events/sec)
- [ ] Vérifier les erreurs (DLQ)
- [ ] Vérifier la latence (< 100ms normalizer)
- [ ] Vérifier la fraîcheur des données market

### En Cas de Problème

1. **Prometheus** → Status → Targets (vérifier health)
2. **Grafana** → Explore → Requête `up` (voir les services)
3. **Logs** → `docker compose logs <service> --tail 100`
4. **Métriques** → Vérifier les counters d'erreurs

---

## ✅ Résumé

| Outil | Usage | URL |
|-------|-------|-----|
| **Prometheus** | Requêtes ad-hoc, debug | http://localhost:9090 |
| **Grafana** | Dashboards visuels | http://localhost:3001 |
| **Metrics endpoints** | Voir métriques brutes | http://localhost:800X/metrics |

**Métriques clés à surveiller** :
- `up` : Services actifs
- `*_total` : Compteurs cumulatifs
- `*_duration_seconds` : Latences
- `*_dlq_*` : Erreurs

**Tips** :
- Utilisez `rate()` pour les counters
- P95/P99 pour les latences
- Alertes sur `up == 0` et DLQ rate
- Time range : "Last 1 hour" par défaut

---

**Bon monitoring ! 🚀📊**
