# 📋 LISTE DE TÂCHES DÉVELOPPEUR
## Système de Trading Algorithmique IA

**Durée estimée totale** : 56 jours (8 semaines) + 4 semaines paper trading
**Pré-requis** : Python 3.11+, Docker, Git, Compte Anthropic/OpenAI, Compte IBKR

---

## 🔧 PHASE 1 : INFRASTRUCTURE DE BASE (Semaine 1 - Jours 1-7)

### JOUR 1-2 : Setup Services Fondamentaux

#### Tâche 1.1 : Initialiser le Projet
- [ ] Créer repo Git : `git init trading-system`
- [ ] Structure de dossiers :
  ```
  trading-system/
  ├── docker-compose.yml
  ├── docker-compose.scale.yml
  ├── .env.example
  ├── requirements.txt
  ├── src/
  ├── config/
  ├── tests/
  ├── scripts/
  └── docs/
  ```
- [ ] Créer `.gitignore` (env files, __pycache__, logs, data)
- [ ] Premier commit

#### Tâche 1.2 : Docker Compose Base
- [ ] Créer `docker-compose.yml` avec services :
  - [ ] Redpanda (Kafka)
  - [ ] MinIO (S3)
  - [ ] PostgreSQL
  - [ ] Redis
  - [ ] Kafka UI
- [ ] Tester démarrage : `docker-compose up -d`
- [ ] Vérifier santé : `docker-compose ps`

#### Tâche 1.3 : Configuration Redpanda
- [ ] Créer topics Kafka :
  ```bash
  rpk topic create events.raw.v1 --partitions 10
  rpk topic create events.normalized.v1 --partitions 10
  rpk topic create events.triaged.v1 --partitions 5
  rpk topic create newscards.v1 --partitions 5
  rpk topic create market.ohlcv.v1 --partitions 20
  rpk topic create signals.final.v1 --partitions 3
  rpk topic create orders.intent.v1 --partitions 2
  rpk topic create orders.executed.v1 --partitions 2
  rpk topic create alerts.priority.v1 --partitions 5
  rpk topic create learning.outcomes.v1 --partitions 1
  ```
- [ ] Tester producer/consumer basique
- [ ] Accéder Kafka UI : http://localhost:8080

#### Tâche 1.4 : Configuration MinIO
- [ ] Créer buckets S3 :
  ```
  raw-events
  newscards-archive
  scenarios-archive
  reports
  backups
  ```
- [ ] Configurer lifecycle policy (rétention 30-90 jours)
- [ ] Tester upload/download fichier
- [ ] Accéder console : http://localhost:9001

#### Tâche 1.5 : Configuration PostgreSQL
- [ ] Créer base `trading`
- [ ] Créer user `trader` avec permissions
- [ ] Tester connexion : `psql -h localhost -U trader -d trading`

#### Tâche 1.6 : Configuration Redis
- [ ] Tester connexion : `redis-cli ping`
- [ ] Configurer maxmemory policy : `allkeys-lru`
- [ ] Tester set/get

---

### JOUR 3-4 : TimescaleDB & Monitoring

#### Tâche 1.7 : Installation TimescaleDB
- [ ] Installer extension TimescaleDB dans PostgreSQL
- [ ] Créer hypertables :
  ```sql
  CREATE TABLE ohlcv (
    time TIMESTAMPTZ NOT NULL,
    ticker VARCHAR(10),
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume BIGINT
  );
  SELECT create_hypertable('ohlcv', 'time');
  ```
- [ ] Créer continuous aggregates (VWAP 1h, 1d)
- [ ] Tester insertion données

#### Tâche 1.8 : Schéma Base de Données
- [ ] Créer tables :
  - [ ] `newscards` (event_id, ticker, type, impact, etc.)
  - [ ] `scenarios` (scenario_id, ticker, version, conditions, etc.)
  - [ ] `positions` (position_id, ticker, entry, current, pnl, etc.)
  - [ ] `orders` (order_id, ticker, action, status, etc.)
  - [ ] `decision_logs` (log_id, input_pack, signal, outcome, etc.)
  - [ ] `agent_performance` (agent_name, calls, latency, cost, etc.)
- [ ] Créer index optimisés (ticker, timestamp)
- [ ] Créer script migration : `scripts/db_migration.sql`

#### Tâche 1.9 : Setup Prometheus + Grafana
- [ ] Ajouter services au docker-compose :
  - [ ] Prometheus
  - [ ] Grafana
- [ ] Créer `config/prometheus.yml` avec scrape configs
- [ ] Accéder Grafana : http://localhost:3000 (admin/admin)
- [ ] Ajouter datasource Prometheus

#### Tâche 1.10 : Dashboards Grafana Initiaux
- [ ] Dashboard "System Health" :
  - [ ] Panels : CPU, RAM, Disk, Network
  - [ ] Panel : Redpanda throughput
  - [ ] Panel : PostgreSQL connections
- [ ] Exporter JSON : `dashboards/grafana/system_health.json`
- [ ] Test alerting : Alert si CPU > 80%

---

### JOUR 5-7 : Environment & Testing Infrastructure

#### Tâche 1.11 : Configuration Environnement
- [ ] Créer `.env.example` :
  ```
  # Databases
  DATABASE_URL=postgresql://trader:password@localhost:5432/trading
  REDIS_URL=redis://localhost:6379
  
  # Kafka
  KAFKA_BROKERS=localhost:9092
  
  # MinIO
  MINIO_ENDPOINT=localhost:9000
  MINIO_ACCESS_KEY=minioadmin
  MINIO_SECRET_KEY=minioadmin
  
  # AI APIs
  ANTHROPIC_API_KEY=sk-ant-...
  OPENAI_API_KEY=sk-...
  
  # Data APIs
  TWITTER_API_KEY=
  REDDIT_CLIENT_ID=
  NEWSAPI_KEY=
  FINNHUB_KEY=
  
  # Broker
  IB_GATEWAY_HOST=localhost
  IB_GATEWAY_PORT=4002
  ```
- [ ] Copier vers `.env` : `cp .env.example .env`
- [ ] Remplir clés API réelles

#### Tâche 1.12 : Requirements Python
- [ ] Créer `requirements.txt` :
  ```
  # Core
  python-dotenv==1.0.0
  pydantic==2.5.0
  loguru==0.7.2
  
  # Kafka
  aiokafka==0.8.1
  
  # Databases
  psycopg2-binary==2.9.9
  sqlalchemy==2.0.23
  redis==5.0.1
  
  # S3
  boto3==1.34.10
  
  # Data Collection
  feedparser==6.0.10
  tweepy==4.14.0
  praw==7.7.1
  requests==2.31.0
  beautifulsoup4==4.12.2
  playwright==1.40.0
  
  # NLP
  spacy==3.7.2
  transformers==4.36.2
  torch==2.1.2
  sentence-transformers==2.2.2
  langdetect==1.0.9
  
  # AI
  langchain==0.1.0
  langgraph==0.0.20
  anthropic==0.8.1
  openai==1.6.1
  
  # Market Data
  yfinance==0.2.33
  ccxt==4.1.92
  ib-insync==0.9.86
  
  # Analysis
  pandas==2.1.4
  numpy==1.26.2
  ta-lib==0.4.28
  
  # API
  fastapi==0.108.0
  uvicorn==0.25.0
  websockets==12.0
  
  # Testing
  pytest==7.4.3
  pytest-asyncio==0.21.1
  hypothesis==6.92.1
  ```
- [ ] Créer venv : `python -m venv venv`
- [ ] Installer : `pip install -r requirements.txt`

#### Tâche 1.13 : Structure Code Base
- [ ] Créer arborescence `src/` :
  ```
  src/
  ├── __init__.py
  ├── ingestion/
  ├── preprocessing/
  ├── nlp/
  ├── agents/
  ├── knowledge/
  ├── strategy/
  ├── execution/
  ├── backtesting/
  ├── learning/
  ├── monitoring/
  └── utils/
  ```
- [ ] Créer `__init__.py` dans chaque dossier

#### Tâche 1.14 : Framework de Test
- [ ] Créer structure `tests/` :
  ```
  tests/
  ├── unit/
  ├── integration/
  ├── e2e/
  └── fixtures/
  ```
- [ ] Créer `pytest.ini`
- [ ] Test basique : `pytest --version`

---

## 📊 PHASE 2 : DATA COLLECTION (Semaine 2 - Jours 8-14)

### JOUR 8-10 : Collectors Core

#### Tâche 2.1 : Interface Abstraite Collector
- [ ] Créer `src/ingestion/base.py` :
  ```python
  from abc import ABC, abstractmethod
  from dataclasses import dataclass
  
  @dataclass
  class RawEvent:
      source: str
      url: str
      text: str
      timestamp: str
      metadata: dict
  
  class Collector(ABC):
      @abstractmethod
      async def collect(self) -> List[RawEvent]:
          pass
  ```

#### Tâche 2.2 : RSS Collector
- [ ] Créer `src/ingestion/rss_collector.py`
- [ ] Charger sources depuis `config/rss_sources.yaml`
- [ ] Parser avec feedparser
- [ ] Publier vers `events.raw.v1` (Redpanda)
- [ ] Archiver dans MinIO (`raw-events/rss/`)
- [ ] Test unitaire : 10 feeds mock
- [ ] Métriques Prometheus (feeds_processed, errors)

#### Tâche 2.3 : Configuration RSS Sources
- [ ] Créer `config/rss_sources.yaml` :
  ```yaml
  sources:
    - name: Bloomberg
      url: https://www.bloomberg.com/feed/...
      priority: high
      quality: 9
    - name: Reuters
      url: https://www.reutersagency.com/feed/...
      priority: high
      quality: 9
    # ... 50+ sources
  ```
- [ ] Ajouter catégories (tech, finance, macro, etc.)

#### Tâche 2.4 : Twitter Collector
- [ ] Créer `src/ingestion/twitter_collector.py`
- [ ] Setup Tweepy avec API key
- [ ] Filtres : #stocks, #trading, comptes vérifés
- [ ] Rate limiting (300 calls/15min)
- [ ] Publier vers Redpanda
- [ ] Test avec API sandbox

#### Tâche 2.5 : Reddit Collector
- [ ] Créer `src/ingestion/reddit_collector.py`
- [ ] Setup PRAW avec credentials
- [ ] Subreddits : wallstreetbets, stocks, investing
- [ ] Filtrer posts score > 50
- [ ] Polling interval : 2 minutes
- [ ] Test unitaire

#### Tâche 2.6 : News API Collector
- [ ] Créer `src/ingestion/news_api_collector.py`
- [ ] Intégration NewsAPI, Finnhub
- [ ] Rate limiting par provider
- [ ] Retry logic avec backoff
- [ ] Fallback si API down

#### Tâche 2.7 : Web Scraper
- [ ] Créer `src/ingestion/web_scraper.py`
- [ ] Playwright setup
- [ ] Sites cibles : Seeking Alpha, MarketWatch
- [ ] Respecter robots.txt
- [ ] Rate limiting 1 req/5s
- [ ] Rotating user-agents

---

### JOUR 11-14 : Market Data & Preprocessing

#### Tâche 2.8 : Market Data Collector
- [ ] Créer `src/ingestion/market_collector.py`
- [ ] yfinance pour données delayed
- [ ] Polygon.io pour real-time (si API key)
- [ ] Tickers watchlist depuis config
- [ ] Insertion directe TimescaleDB
- [ ] Scheduling : 1 min bars pendant market hours

#### Tâche 2.9 : Feature Calculator
- [ ] Créer `src/ingestion/features.py`
- [ ] Calculer indicateurs :
  - [ ] VWAP (1h, 1d)
  - [ ] RSI (14 périodes)
  - [ ] MACD (12, 26, 9)
  - [ ] Bollinger Bands
  - [ ] ATR (Average True Range)
- [ ] Stocker dans TimescaleDB
- [ ] Test avec données mock

#### Tâche 2.10 : Normalizer
- [ ] Créer `src/preprocessing/normalizer.py`
- [ ] Consumer Kafka : `events.raw.v1`
- [ ] Nettoyage texte :
  - [ ] Strip HTML tags
  - [ ] Normaliser Unicode
  - [ ] Supprimer URLs
- [ ] Timestamp vers UTC
- [ ] Déduplication (BloomFilter Redis)
- [ ] Publier vers `events.normalized.v1`
- [ ] Tests unitaires

#### Tâche 2.11 : Triage Stage 1 (Déterministe)
Objectif du Stage 1

Mettre un entonnoir déterministe qui :

ne jette presque rien (objectif 100k/jour, garder les signaux faibles)

attribue un score initial 0–100, une priority hint et des raisons

route les événements vers une voie :

FAST (à traiter immédiatement par NLP Stage 2)

STANDARD (à traiter normalement)

COLD (à conserver et traiter plus tard / batch / sampling)

DROP_HARD (spam évident uniquement)

Le Stage 1 doit être ultra rapide, stable, configurable, observable.

A) Topics & routing (obligatoire)
A1) Entrée

Consommer Kafka depuis events.normalized.v1

Consumer group : triage-stage1-v1

A2) Sorties (recommandées)

Créer 3 topics de sortie (et 3 DLQ optionnels si tu veux) :

events.stage1.fast.v1 (6 partitions)

events.stage1.standard.v1 (6 partitions)

events.stage1.cold.v1 (6 partitions)

Optionnel :
4) events.stage1.dropped.v1 (1 partition) uniquement pour audit (pas obligatoire)
5) DLQ unique : events.stage1.dlq.v1 (1 partition)

👉 But : Stage 2 consommera fast + standard en temps réel, et cold en batch.

Mettre à jour infra/redpanda/init-topics.sh pour créer ces topics (idempotent).

B) Contrat de sortie : stage1_event.v1 (obligatoire)

Créer un schéma strict schemas/stage1_event.v1.json.

Champs minimum requis
Identité & traçabilité

schema_version = "stage1_event.v1"

event_id (UUID)

triaged_at_utc (UTC)

pipeline_version

source_type, source_name

event_time_utc (si dispo)

canonical_url (nullable)

lang

dedup_key (si dispo depuis normalized)

normalized_text_hash (sha256 du texte normalisé utilisé)

Triage stage 1

triage_score_stage1 (0–100)

triage_bucket enum : FAST|STANDARD|COLD|DROP_HARD

priority_hint enum : P0|P1|P2|P3

triage_reasons : array de tags (liste fermée, faible cardinalité)

signals : objet résumant les features cheap calculées, ex :

has_ticker_candidate bool

ticker_candidates_count int

has_numbers bool

has_percent bool

has_money bool

text_length int

keyword_hits array (optionnel mais faible cardinalité)

source_reliability number 0..1

source_noise number 0..1

recency_seconds int (now - event_time)

normalized_event : (optionnel) soit tu copies un sous-ensemble minimal (title/text/url), soit tu mets une référence.

Recommandé v1 : inclure le strict minimum utile à Stage 2 sans re-fetch (mais attention taille).

Minimum : normalized_text, symbols_candidates (si existant), source_score si existant.

Quality flags

quality_flags array : LOW_TEXT, LANG_UNKNOWN, CLICKBAIT_SUSPECT, SPAM_SUSPECT, etc.

Règles :

additionalProperties: false

fournir sample schemas/samples/stage1_event_valid.json

mettre à jour scripts de validation des schémas.

C) Configuration Stage 1 (obligatoire)

Créer un fichier de config versionné (dans repo) :

config/triage_stage1.yaml

Contenu minimum :

strong_keywords (liste) : mots clés “market-moving” (earnings, SEC, Fed, merger, bankruptcy, hack, breach, guidance…)

weak_keywords (liste) : signaux faibles (rumor, reported, might, sources say…)

clickbait_keywords (liste) : “shocking”, “you won’t believe”, etc (pénalité)

source_scores :

mapping par source_type puis source_name → reliability (0–1) + noise (0–1)

ex : rss: { "ft.com": {reliability:0.95, noise:0.1}, ... }

thresholds :

score thresholds pour bucket FAST/STANDARD/COLD

limits :

max text length analysé

min text length

Doit être simple à ajuster sans toucher au code (l’agent doit documenter comment).

D) Logique Stage 1 (obligatoire, orientée “garder”)
D1) Extraction “cheap signals”

À partir du normalized event (texte + metadata) :

text_length

has_numbers / has_percent / has_money (regex)

keyword hits (strong + weak + clickbait)

ticker candidates (from symbols_candidates ou regex légère si absent)

recency_seconds (si event_time dispo)

source reliability/noise depuis YAML

duplicate_recent (si dedup_key déjà vu récemment par Stage 1, optionnel)

D2) Score Stage 1 (0–100) — déterministe & explicable

Construire un score composé, ex (structure, pas de code) :

+0..35 : source_reliability (gros poids)

+0..25 : strong keywords hits (cap)

+0..15 : ticker candidates (plus si plusieurs, mais cap)

+0..10 : numbers/percent/money (cap)

+0..10 : recency (plus récent = plus haut)

-0..20 : pénalités source_noise, clickbait, texte trop court, etc.

Chaque composant ajouté/pénalisé doit aussi ajouter un tag triage_reasons :

HIGH_SOURCE_RELIABILITY

STRONG_KEYWORDS

HAS_TICKER_CANDIDATES

HAS_MONEY_OR_PERCENT

VERY_RECENT

HIGH_SOURCE_NOISE

CLICKBAIT_SUSPECT

SHORT_TEXT
etc.

D3) Buckets (FAST/STANDARD/COLD/DROP_HARD)
Principe (important)

DROP_HARD uniquement pour spam évident (rare)

COLD = on garde, mais on traite plus tard

FAST/STANDARD = on traite maintenant

Règles recommandées :

DROP_HARD si :

texte vide/illisible ou

clickbait + source inconnue + aucune entité/ticker + très court

FAST si :

score >= FAST_THRESHOLD (config)

OU présence keyword ultra fort (SEC/Fed/earnings/merger/bankruptcy/hack) + source >= moyen

STANDARD si :

score >= STANDARD_THRESHOLD

COLD sinon (par défaut)

D4) Priority hint (P0..P3)

P0 pour FAST (top urgent)

P1 pour FAST (moins urgent) / STANDARD haut

P2 pour STANDARD bas

P3 pour COLD (signal faible conservé)

E) Déduplication légère (recommandée)

Stage 1 peut avoir un dedup minimal pour limiter flood :

stocker récemment vus (dedup_key + TTL) dans :

Redis si dispo (idéal), sinon SQLite ou fichier persistant (volume)

si duplicate récent : ne pas drop forcément, mais :

baisser score

ou router en COLD

et ajouter reason DUPLICATE_RECENT

F) Service services/preprocessing/triage_stage1 (obligatoire)

Créer un nouveau service dockerisé :

services/preprocessing/triage_stage1/

Dockerfile

app (consumer kafka + producer kafka)

requirements

expose :

GET /health

GET /metrics

port recommandé : 8006

Ajout dans infra/docker-compose.yml :

service triage-stage1 dans profile apps

env vars : bootstrap kafka, path config YAML, etc.

Prometheus scrape ajouté (profil observability)

G) Observabilité Prometheus (obligatoire)

Exposer métriques stables :

Counters :

triage_stage1_events_consumed_total

triage_stage1_events_routed_total{bucket="FAST|STANDARD|COLD|DROP_HARD"}

triage_stage1_events_failed_total{reason="schema|produce|config|runtime"}

triage_stage1_dedup_hits_total
Histograms :

triage_stage1_processing_duration_seconds

triage_stage1_score_histogram (histogram ou summary)
Gauges :

triage_stage1_last_success_timestamp

H) Grafana panels (obligatoire)

Mettre à jour dashboard existant ou créer “Triage Health” avec :

rate routed FAST/STANDARD/COLD/DROP_HARD

p95 latency stage1

score distribution (histogram)

dedup hits rate

drop_hard rate (doit rester faible)

last success age

Provisionner automatiquement.

I) Tests & validation (obligatoire)

Créer un test d’intégration simple :

injecter 8 events normalisés variés dans events.normalized.v1 :

fort keyword + source fiable → FAST

source moyenne + ticker → STANDARD

signal faible (rumor) mais ticker → COLD (pas drop)

spam évident → DROP_HARD

vérifier qu’on retrouve les events dans les bons topics

vérifier conformité schéma stage1_event.v1

J) Documentation (obligatoire)

Créer docs/triage_stage1.md :

philosophie funnel (on garde, on priorise)

explication score + buckets + priority

comment éditer config/triage_stage1.yaml

comment surveiller sur Grafana

comment ajuster thresholds pour viser 100k/j

Critères d’acceptation (DoD)

Le service tourne en local via docker compose --profile apps --profile observability up -d

Il consomme events.normalized.v1 et route correctement vers events.stage1.fast.v1, standard, cold

DROP_HARD reste rare et justifié (audit possible)

/metrics expose toutes les métriques clés

Dashboard montre la distribution et la latence

Tests d’intégration passent

#### Tâche 2.12 : Triage Stage 2 (NLP)
But du Stage 2

Transformer un événement “normalized” ou “stage1” en un événement triaged qui contient :

NER (spaCy) : ORG, PERSON + signaux MONEY / PERCENT (au minimum)

Sentiment finance (FinBERT local) : score + confidence

Un score final 0–100 + raisons (explainable)

Une priority exploitable (P0..P3)

Un seuil adaptatif selon le régime (marché + charge pipeline)

Publication vers events.triaged.v1 (et DLQ)

Important : on ne veut pas “tout jeter”. Même des liens faibles doivent passer, mais avec priorité basse et/ou marquage.

A) Entrée / sortie
Input topic

Consommer depuis events.stage1.v1 (si Stage 1 existe)
sinon consommer depuis events.normalized.v1.

Consumer group : triage-nlp-v1

Output topics

events.triaged.v1 (6 partitions)

events.triaged.dlq.v1 (1 partition)

Mettre à jour le script init topics Redpanda pour créer ces topics.

B) Schéma de sortie : triaged_event.v1

Créer un schéma JSON strict schemas/triaged_event.v1.json (contract-first). Champs minimum :

Identité & traçabilité

schema_version = "triaged_event.v1"

event_id (UUID)

triaged_at_utc

pipeline_version

source_type, source_name

canonical_url (nullable)

lang

dedup_key (si dispo) + normalized_text_hash

Résultats NLP

entities : liste d’objets {type, text, confidence} (ORG, PERSON, PRODUCT minimum)

money_mentions : bool + (optionnel) liste de montants extraits si simple

percent_mentions : bool + (optionnel) liste de pourcentages extraits

Sentiment (FinBERT)

sentiment.score dans [-1,1]

sentiment.confidence dans [0,1]

sentiment.model="finbert"

Score & décision

triage_score (0–100)

priority enum P0|P1|P2|P3

triage_reasons : array de tags explicatifs (faible cardinalité)

thresholds : objet qui log la valeur de seuil utilisée (pour audit)

regime : objet {market_regime, load_regime}

Erreurs / flags

quality_flags : array (ex: LOW_TEXT, LANG_UNKNOWN, NER_EMPTY, FINBERT_LOW_CONF)

DLQ : définir un format DLQ stable contenant event_id, error_type, error_message, failed_stage, et (si possible) l’input minimal.

C) NLP Pipeline (Stage 2)
C1) Modèles spaCy (NER)

Installer et télécharger en + fr :

en_core_web_sm

fr_core_news_sm

Sélectionner le modèle selon lang de l’event (sinon fallback “en”).

Sorties attendues :

ORG et PERSON au minimum

si le modèle fournit MONEY/PERCENT directement : les utiliser

sinon : extraire MONEY/PERCENT via regex légère (mais garder cette logique stable/déterministe)

C2) FinBERT local (sentiment finance)

Utiliser un modèle FinBERT adapté au sentiment (local).

Définir une stratégie performance pour 100k/j :

batch inference (par paquet) pour amortir le coût

limiter la longueur texte (ex: max tokens) et stocker un flag “TEXT_TRUNCATED”

Sortie :

score : map vers [-1,1]

confidence : probabilité du label choisi

C3) Résolution tickers “mieux que regex”

Même si ce service s’appelle triage, il doit aider à éviter les faux positifs :

Entrée : symbols_candidates (du normalizer) + ORG entities spaCy

Validation minimale acceptable :

“whitelist” tickers configurable (CSV) OU

table DB (Timescale / Postgres) des tickers connus (si disponible)

Sortie :

tickers: liste {symbol, confidence, method}

D) Scoring 0–100 (explainable)

Construire un score composé de sous-scores (et produire les reasons) :

D1) Sous-scores recommandés

Impact keywords (macro/earnings/SEC/merger/bankruptcy/security hack) : +0..30

Source quality (hérité Stage 1 si dispo) : +0..25

Ticker confidence : +0..20

Entity strength (ORG/PERSON) : +0..10

Sentiment magnitude (|score|) et confiance : +0..15
(mais pénaliser si confidence faible)

Score final = clamp 0..100.

D2) “Reasons” obligatoires

À chaque boost/pénalité, ajouter un tag dans triage_reasons (liste fermée) :

HIGH_SOURCE_QUALITY

HAS_VALID_TICKER

KEYWORD_EARNINGS

KEYWORD_REGULATION

KEYWORD_MACRO

KEYWORD_SECURITY

STRONG_SENTIMENT

LOW_SENTIMENT_CONF

SHORT_TEXT

NER_EMPTY
etc.

E) Seuil adaptatif selon régime (marché + charge)

On ne “drop” pas agressivement : on adapte surtout la priority et le routing.

E1) Market regime (simple, déterministe)

Définir 3 régimes :

CALM

NORMAL

STRESS

Méthode minimale :

utiliser un indicateur externe si déjà dispo (ex: VIX) sinon

calculer un proxy à partir de SPY/QQQ dans Timescale (vol récente)

en stress : abaisser les seuils pour mettre plus de choses en P0/P1

E2) Load regime (pipeline)

Définir 3 états :

LOW_LOAD, NORMAL_LOAD, HIGH_LOAD

Déclencheurs possibles (choisir au moins 2) :

consumer lag > X

latence p95 > Y

taux d’erreurs/DLQ > Z

CPU/mémoire au-dessus d’un seuil (si métriques dispo)

En HIGH_LOAD :

ne pas jeter : dégrader :

plus d’events basculent en P3 (COLD) au lieu de P1/P2

sampling optionnel sur P3 pour Stage 2 si besoin, mais conserver en MinIO/artefacts

E3) Définir les seuils

Exemple de logique (à implémenter de façon documentée) :

P0 si score >= T0

P1 si score >= T1

P2 si score >= T2

P3 sinon

Avec adaptation :

en STRESS : (T0,T1,T2) diminuent

en HIGH_LOAD : (T0,T1,T2) augmentent légèrement, mais P3 reste conservé (pas drop)

Logguer thresholds et regime dans l’event triagé.

F) Publication & priorité

Publier vers events.triaged.v1 :

champ priority dans le JSON

(optionnel) ajouter un header Kafka x-priority=P0..P3 si supporté, mais la vérité reste le champ JSON.

DLQ :

publier vers events.triaged.dlq.v1 sur toute exception, avec contexte.

G) Observabilité (obligatoire)

Exposer /health et /metrics (Prometheus) :

throughput in/out

latence p95 processing

ratio P0/P1/P2/P3

DLQ rate

distribution des scores (histogram)

drift simple :

moyenne mobile sentiment

répartition catégories / reasons (faible cardinalité)

Mettre à jour Prometheus scrape + ajouter panels Grafana :

triage_nlp_rate_in, triage_nlp_rate_out

triage_nlp_latency_p95

triage_priority_distribution

triage_dlq_rate

sentiment_mean (drift)

H) Tests & validation (obligatoire)

Créer un test d’intégration qui :

injecte 5 events normalisés variés (FR/EN, avec/sans ticker, avec keywords)

vérifie qu’ils ressortent dans events.triaged.v1

vérifie que :

schéma validé

priority attribuée

entities présentes sur au moins 1 event

sentiment présent + confidence

thresholds/regime présents

I) Documentation (obligatoire)

Ajouter docs/triage_stage2.md :

scoring expliqué + reasons

régime et seuils adaptatifs

comment lire le dashboard

comment ajuster : keywords, seuils, whitelist tickers

Output attendu

Topics + init

Schéma triaged_event.v1

Service Stage 2 (Docker + endpoints health/metrics)

Prometheus/Grafana panels

Tests + docs

Aucun code trading / agents dans cette tâche

#### Tâche 2.13 : Orchestration Collectors
- [ ] Créer `src/ingestion/orchestrator.py`
- [ ] Schedule tous collectors (APScheduler)
- [ ] RSS : 5 min
- [ ] Twitter : 1 min (si stream)
- [ ] Reddit : 2 min
- [ ] Market : 1 min (pendant heures ouverture)
- [ ] Health checks
- [ ] Graceful shutdown

#### Tâche 2.14 : Tests Integration Data Pipeline
- [ ] Test end-to-end :
  - [ ] Inject event → RSS collector
  - [ ] Vérifier Redpanda (`events.raw.v1`)
  - [ ] Vérifier MinIO (archive)
  - [ ] Vérifier Normalizer traite
  - [ ] Vérifier Triage filtre
- [ ] Mesurer latency totale (< 5s acceptable)

---

## 🤖 PHASE 3 : AI CORE (Semaine 3-4 - Jours 15-28)

### JOUR 15-18 : Standardizer (NewsCards)

#### Tâche 3.1 : Multi-Provider Setup
- [ ] Créer `src/agents/providers/` :
  - [ ] `anthropic_provider.py`
  - [ ] `openai_provider.py`
  - [ ] `base_provider.py` (interface)
- [ ] Config `config/ai_providers.yaml` :
  ```yaml
  providers:
    - name: anthropic
      models:
        fast: claude-haiku-4-5-20251001
        medium: claude-sonnet-4-5-20250929
        deep: claude-opus-4-20250514
      weight: 0.6
    - name: openai
      models:
        fast: gpt-4o-mini
        medium: gpt-4o
        deep: o1-preview
      weight: 0.4
  ```

#### Tâche 3.2 : NewsCard Schema
- [ ] Créer `src/agents/schemas.py` :
  ```python
  from pydantic import BaseModel
  
  class NewsCard(BaseModel):
      event_id: str
      timestamp: str
      entities: List[str]
      tickers: List[str]
      type: str
      impact_direction: str
      impact_strength: float
      time_horizon: str
      novelty: str
      confidence: float
      uncertainties: List[str]
      why_it_matters: List[str]
      invalidated_if: List[str]
      evidence_refs: List[str]
  ```

#### Tâche 3.3 : Prompt Template NewsCard
- [ ] Créer `src/agents/prompts/newscard_prompt.txt`
- [ ] Variables : {normalized_event}, {context}
- [ ] Output strict JSON
- [ ] Examples few-shot (3-5)

#### Tâche 3.4 : Standardizer Core
- [ ] Créer `src/agents/standardizer.py`
- [ ] Consumer Kafka : `events.triaged.v1`
- [ ] Sélection provider/model selon priority
- [ ] Appel LLM avec prompt
- [ ] Parse JSON response
- [ ] Retry si malformed (max 3)
- [ ] Validation schema Pydantic
- [ ] Stockage :
  - [ ] PostgreSQL (metadata)
  - [ ] MinIO (NewsCard complète)
  - [ ] Redis (cache last 100 par ticker)
- [ ] Publier vers `newscards.v1`

#### Tâche 3.5 : Confidence Calibration
- [ ] Créer `src/agents/calibration.py`
- [ ] Function empirical_calibrate(raw_confidence)
- [ ] Placeholder (linéaire) :
  ```python
  def calibrate(conf):
      if conf > 0.9: return conf * 0.75
      elif conf < 0.6: return conf * 1.1
      return conf
  ```
- [ ] Appliquer avant stockage NewsCard

#### Tâche 3.6 : Tests Standardizer
- [ ] Mock API responses
- [ ] Test 10 events variés
- [ ] Validation JSON structure
- [ ] Test fallback provider si primary fail
- [ ] Test calibration

---

### JOUR 19-21 : Plan Builder

#### Tâche 3.7 : Catalyst Calendar Integration
- [ ] Créer `src/knowledge/calendar.py`
- [ ] API Trading Economics (gratuit)
- [ ] Earnings dates via yfinance
- [ ] Fed meetings (hardcodé + API)
- [ ] Stocker dans PostgreSQL (`catalysts` table)
- [ ] Fonction `get_upcoming_catalysts(ticker, days=7)`

#### Tâche 3.8 : Market Regime Detector
- [ ] Créer `src/strategy/regime_detector.py`
- [ ] Calculer :
  - [ ] VIX actuel
  - [ ] SPY return 5D
  - [ ] SPY volatility 30D
- [ ] Classifier :
  ```python
  if vix > 35: return "FLASH_CRASH"
  elif vix < 12 and vol < 0.005: return "LOW_VOL_GRIND"
  elif vix > 25 and ret_5d < -0.01: return "TRENDING_BEAR"
  elif vix < 15 and ret_5d > 0.01: return "TRENDING_BULL"
  else: return "VOLATILE_RANGE"
  ```
- [ ] Cacher dans Redis (update toutes les 5 min)

#### Tâche 3.9 : Scenario Schema
- [ ] Créer `src/agents/schemas.py` (ajouter) :
  ```python
  class Scenario(BaseModel):
      scenario_id: str
      ticker: str
      name: str
      version: str
      bias: str  # bullish/bearish/neutral
      probability: float
      entry_conditions: List[str]
      invalidation_triggers: List[str]
      targets: dict
      size_max_pct: float
      time_horizon: str
      reassess_if: List[str]
      reasoning: List[str]
      catalysts_pending: List[dict]
  ```

#### Tâche 3.10 : Prompt Template Scenario
- [ ] Créer `src/agents/prompts/scenario_prompt.txt`
- [ ] Input : NewsCards 24h, OHLCV 90D, Catalysts, Regime
- [ ] Output : 3 scénarios (bullish/neutral/bearish)
- [ ] JSON strict

#### Tâche 3.11 : Plan Builder Core
- [ ] Créer `src/agents/plan_builder.py`
- [ ] Trigger : Cron 04:00 ET
- [ ] Pour chaque ticker watchlist :
  - [ ] Charger NewsCards depuis 20:00 veille
  - [ ] Charger OHLCV 90D
  - [ ] Charger catalysts proches
  - [ ] Get market regime
  - [ ] Appel LLM (Opus/o1)
  - [ ] Parse scenarios
  - [ ] Stockage PostgreSQL + MinIO
- [ ] Génération watchlist dynamique (top 20)

#### Tâche 3.12 : Scenario Updater
- [ ] Créer `src/agents/scenario_updater.py`
- [ ] Trigger : 11:30, 13:30, 15:30 ET
- [ ] Pour chaque ticker avec position OU scénario actif :
  - [ ] Charger dernières 2h données
  - [ ] Re-run prompt (Sonnet)
  - [ ] Update scénarios (version++)
  - [ ] Mark old version superseded
- [ ] Métriques (scenarios_updated, cost)

#### Tâche 3.13 : Tests Plan Builder
- [ ] Mock NewsCards (10 pour AAPL)
- [ ] Mock OHLCV historique
- [ ] Test génération 3 scénarios
- [ ] Validation structure JSON
- [ ] Test catalyst injection

---

### JOUR 22-28 : Decision Engine (LangGraph)

#### Tâche 3.14 : LangGraph Workflow Setup
- [ ] Créer `src/agents/decision_engine.py`
- [ ] Définir StateGraph :
  ```python
  from langgraph.graph import StateGraph
  
  workflow = StateGraph(DecisionState)
  workflow.add_node("load_context", load_context_node)
  workflow.add_node("match_scenarios", match_scenarios_node)
  workflow.add_node("evaluate_confidence", evaluate_confidence_node)
  workflow.add_node("web_research", web_research_node)
  workflow.add_node("decide", decide_node)
  workflow.add_node("risk_soft", risk_soft_node)
  
  workflow.set_entry_point("load_context")
  workflow.add_edge("load_context", "match_scenarios")
  workflow.add_conditional_edges(
      "evaluate_confidence",
      route_by_confidence,
      {"low": "web_research", "medium": "decide", "high": "decide"}
  )
  ```

#### Tâche 3.15 : Node: Load Context
- [ ] Fonction `load_context_node(state)`
- [ ] Charger :
  - [ ] NewsCards (fenêtre 2h)
  - [ ] Scenarios actifs
  - [ ] OHLCV (1D + 5D)
  - [ ] Positions actuelles
  - [ ] Risk limits
- [ ] Return updated state

#### Tâche 3.16 : Node: Match Scenarios
- [ ] Fonction `match_scenarios_node(state)`
- [ ] Pour chaque scénario :
  - [ ] Vérifier entry_conditions
  - [ ] Calculer match_score (0-100)
- [ ] Garder top 2 scénarios
- [ ] Update state

#### Tâche 3.17 : Node: Evaluate Confidence
- [ ] Fonction `evaluate_confidence_node(state)`
- [ ] Agrège :
  - [ ] match_score scenarios
  - [ ] NewsCard.confidence (calibrée)
  - [ ] Technical confirmation (RSI, MACD)
- [ ] Output : confidence finale (0-1)

#### Tâche 3.18 : Node: Web Research (optionnel)
- [ ] Créer `src/agents/web_researcher.py`
- [ ] Tavily API ou Perplexity
- [ ] Budget : 20 calls/jour max
- [ ] Timeout : 15s
- [ ] Return : sources + extraits

#### Tâche 3.19 : Node: Decide
- [ ] Fonction `decide_node(state)`
- [ ] Prompt LLM (Sonnet/GPT-4o) :
  - [ ] Input : full context
  - [ ] Output : Signal JSON
    ```json
    {
      "action": "BUY|SELL|HOLD",
      "confidence": 0.78,
      "reasoning": [...],
      "plan": {
        "order_type": "LIMIT",
        "quantity": 10,
        "limit_price": 185.5,
        "stop_loss": 182.0,
        "take_profit": [189.0, 192.0]
      }
    }
    ```

#### Tâche 3.20 : Node: Risk Soft Gate
- [ ] Fonction `risk_soft_node(state)`
- [ ] Vérifier overrides IA :
  - [ ] Stop ajustement dans ±20%
  - [ ] Hold malgré drawdown < 2.5%
- [ ] Logger tous overrides
- [ ] Return approved/rejected

#### Tâche 3.21 : Decision Engine Orchestration
- [ ] Consumer Kafka : `newscards.v1` (pour positions held)
- [ ] Consumer Kafka : `alerts.priority.v1` (pour réévaluations)
- [ ] Pour chaque trigger :
  - [ ] Run LangGraph workflow
  - [ ] Publier Signal vers `signals.final.v1`
- [ ] Métriques (decisions/hour, latency, cost)

#### Tâche 3.22 : Tests Decision Engine
- [ ] Mock context complet
- [ ] Test workflow end-to-end
- [ ] Test routing confidence (low/medium/high)
- [ ] Test web research trigger
- [ ] Validation Signal output

---

## 🛡️ PHASE 4 : RISK & EXECUTION (Semaine 5 - Jours 29-35)

### JOUR 29-31 : Risk Management

#### Tâche 4.1 : Risk Gate Hard
- [ ] Créer `src/execution/risk_gate.py`
- [ ] Config `config/risk_limits.yaml` :
  ```yaml
  hard_limits:
    max_position_pct: 0.10
    max_daily_loss_pct: 0.03
    max_drawdown_pct: 0.15
    max_open_positions: 5
    max_trades_per_day: 10
    stop_loss_required: true
    halt_if_vix_above: 40
  ```
- [ ] Function `check_hard_limits(signal, portfolio)` :
  - [ ] Return GO | REJECT + reason
  - [ ] Aucune exception possible
  - [ ] Log violations

#### Tâche 4.2 : Correlation Guardian
- [ ] Créer `src/strategy/correlation_guardian.py`
- [ ] Calculer matrice corrélation rolling 30D
- [ ] Stocker dans Redis (update 1x/heure)
- [ ] Function `check_correlation(new_ticker, held_positions)` :
  - [ ] Si corr > 0.7 : REDUCE size 50%
  - [ ] Si 2+ positions corrélées : REJECT
- [ ] Alert si "correlation creep" détecté

#### Tâche 4.3 : Pre-Flight Check
- [ ] Créer `src/execution/preflight.py`
- [ ] Checks :
  ```python
  def preflight_check(signal):
      checks = []
      
      # Catalyst imminent ?
      if catalyst_within_minutes(signal.ticker, 30):
          return ABORT
      
      # Correlation OK ?
      corr = max_correlation(signal.ticker)
      if corr > 0.7:
          signal.quantity *= 0.5
          checks.append(WARN("Correlation high"))
      
      # Régime OK ?
      if get_regime() == "FLASH_CRASH":
          return ABORT
      
      # Liquidité OK ?
      if get_volume(signal.ticker) < 500_000:
          return ABORT
      
      # Spread OK ?
      if get_spread(signal.ticker) > 0.005:
          return WAIT
      
      return GO(checks)
  ```

#### Tâche 4.4 : Tests Risk Management
- [ ] Test hard limits (position size, daily loss, etc.)
- [ ] Test correlation checks
- [ ] Test preflight avec scenarios variés
- [ ] Valider aucun bypass possible

---

### JOUR 32-35 : Execution Layer

#### Tâche 4.5 : Interactive Brokers Setup
- [ ] Installer IB Gateway ou TWS
- [ ] Configuration paper trading :
  - [ ] Port 4002
  - [ ] Enable API connections
  - [ ] Client ID : 1
- [ ] Test connexion : `ib-insync`

#### Tâche 4.6 : Execution Adapter
- [ ] Créer `src/execution/ibkr_adapter.py`
- [ ] Consumer Kafka : `signals.final.v1`
- [ ] Pour chaque signal :
  - [ ] Re-check