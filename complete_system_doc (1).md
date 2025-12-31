# 📊 SYSTÈME DE TRADING ALGORITHMIQUE IA
## Architecture Complète & Guide d'Implémentation

---

## TABLE DES MATIÈRES

1. [Vue d'Ensemble du Système](#vue-densemble)
2. [Philosophie & Principes de Conception](#philosophie)
3. [Stack Technologique Complète](#stack-technique)
4. [Architecture des Flux de Données](#flux-donnees)
5. [Modules du Système (Détaillés)](#modules)
6. [Régimes Temporels & Comportements](#regimes)
7. [Système d'Agents IA](#agents-ia)
8. [Gestion du Risque](#risque)
9. [Repositories GitHub Utilisés](#github-repos)
10. [Ordre de Mise en Place](#ordre-implementation)
11. [Monitoring & Observabilité](#monitoring)
12. [Frontend & Visualisation](#frontend)
13. [Modularité & Testing](#modularite)

---

## 1. VUE D'ENSEMBLE DU SYSTÈME {#vue-densemble}

### Objectif Final
Créer un système de trading **autonome** et **adaptatif** qui :
- Collecte 10,000+ actualités/jour depuis sources multiples
- Transforme le bruit en signaux structurés exploitables
- Génère des plans stratégiques avant l'ouverture du marché
- Prend des décisions en temps réel pendant les heures de trading
- Exécute via Interactive Brokers avec gestion stricte du risque
- Apprend continuellement de ses erreurs

### Philosophie Centrale
> **"PENSER QUAND C'EST CALME, AGIR QUAND C'EST OUVERT, PROTÉGER QUAND ON EST EN POSITION"**

### Chiffres Clés
- **Latence décision** : < 500ms pendant market hours
- **Coût IA quotidien** : 10-15€ (mode économique) / 300-500€ (mode performance)
- **Throughput** : 1,000-100,000 événements/seconde selon échelle
- **Uptime requis** : 99.9% pendant 09:30-16:00 ET
- **Marchés ciblés** : US équities (extensible Europe/Asie)

---

## 2. PHILOSOPHIE & PRINCIPES DE CONCEPTION {#philosophie}

### Principes Architecturaux

#### A. Séparation Temporelle
```
OVERNIGHT (20:00→04:00) : Accumulation + Deep Analysis
    ↓ [IA lourde, temps infini, qualité maximale]
    
PRE-MARKET (04:00→09:30) : Plan Generation
    ↓ [Scénarios, watchlist, triggers]
    
MARKET OPEN (09:30→16:00) : Fast Reaction
    ↓ [Match plans vs. reality, exécution rapide]
    
POST-MARKET (16:00→20:00) : Review & Learning
    ↓ [Post-mortem, mise à jour mémoire]
```

#### B. Immutabilité & Rejouabilité
- **Tout événement brut** est archivé dans MinIO (S3-compatible)
- **Toute décision** est expliquée et traçable
- **Tout trade** peut être rejoué avec contexte exact

#### C. Modularité & Interchangeabilité
```
[Collector RSS] ----┐
[Collector Twitter] ├─→ [Interface Standard] ─→ Redpanda
[Collector Reddit]  ┘

[IA Provider Claude] ----┐
[IA Provider GPT]        ├─→ [Interface Standard] ─→ Decision
[IA Provider Grok]       ┘
```
Chaque module respecte une interface commune → remplacement sans casser le système.

#### D. Defense in Depth (Sécurité Multi-Niveaux)
```
Signal IA 
    ↓
Risk Gate Soft (IA peut override)
    ↓
Risk Gate Hard (INVIOLABLE)
    ↓
Pre-Flight Check
    ↓
Broker Execution
    ↓
Position Watcher (sortie automatique si breach)
```

---

## 3. STACK TECHNOLOGIQUE COMPLÈTE {#stack-technique}

### Infrastructure de Base

| Composant | Technologie | Rôle | Scalabilité |
|-----------|-------------|------|-------------|
| **Message Broker** | Redpanda (Kafka API) | Transport événements | 10k → 1M msg/s |
| **Object Storage** | MinIO (S3 API) | Archive immutable | Infini (add disks) |
| **Time-Series DB** | TimescaleDB (PostgreSQL) | OHLCV + features | 100GB → 10TB |
| **Relational DB** | PostgreSQL | Metadata, NewsCards, Plans | 10GB → 1TB |
| **Graph DB** | Neo4j Community→Enterprise | Relations, patterns | 1M → 1B nodes |
| **Cache** | Redis | État live, watchlist | 256MB → 100GB |
| **Monitoring** | Prometheus + Grafana | Observabilité | Natif HA |
| **Container Orchestration** | Docker Compose → Kubernetes | Déploiement | 1 node → 100 nodes |

### Langages & Frameworks

| Couche | Technologie | Justification |
|--------|-------------|---------------|
| **Backend Core** | Python 3.11+ | Écosystème finance + IA |
| **Event Processing** | Faust / Kafka Streams | Stream processing natif |
| **NLP Local** | spaCy 3.7 + Transformers | Performance CPU acceptable |
| **IA Orchestration** | LangChain + **LangGraph** | Multi-agents avec cycles |
| **API Gateway** | FastAPI | Async + auto-doc |
| **Frontend** | React 18 + TanStack Query | Real-time updates |
| **Visualisation** | Recharts + D3.js | Graphiques financiers |
| **Testing** | pytest + hypothesis | Property-based testing |

### APIs Externes Utilisées

#### Données de Marché (Gratuites → Premium)
- **Tier Free** : yfinance, Alpha Vantage (25 calls/jour)
- **Tier Low** : Finnhub ($25/mois), Polygon.io Starter ($50/mois)
- **Tier Pro** : Polygon.io Premium ($200/mois), IEX Cloud ($500/mois)

#### Actualités & Sentiment
- **RSS** : Gratuit, 1000+ sources
- **Twitter/X** : API Basic (gratuit 1500 tweets/mois) → Premium ($100/mois)
- **Reddit** : PRAW (gratuit)
- **NewsAPI** : Gratuit 100/jour → Pro ($450/mois)
- **Benzinga** : Premium news ($300/mois)

#### IA / LLM
- **Anthropic Claude** : Haiku ($0.25/MTok) + Sonnet ($3/MTok) + Opus ($15/MTok)
- **OpenAI** : GPT-4o ($2.5/MTok) + o1 ($15/MTok)
- **X.AI Grok** : En beta, pricing TBD
- **Local** : Llama 3.1 70B (self-hosted, gratuit mais GPU requis)

#### Calendrier Économique
- **Trading Economics API** : Gratuit 1000 calls/mois
- **Earnings Whispers** : Gratuit avec limite
- **FRED (Fed St. Louis)** : Gratuit, données macro US

---

## 4. ARCHITECTURE DES FLUX DE DONNÉES {#flux-donnees}

### Schéma Global de Flux

```
┌─────────────────────────────────────────────────────────────────┐
│                    SOURCES EXTERNES (24/7)                      │
│  RSS | Twitter | Reddit | NewsAPI | Web Scraping | Market Data │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │   COLLECTORS    │
                    │  (Workers Pool) │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌─────────────────┐         ┌──────────────────┐
    │   MinIO (S3)    │         │  Redpanda (Kafka)│
    │  Raw Archives   │         │  events.raw.v1   │
    └─────────────────┘         └────────┬─────────┘
                                         │
                             ┌───────────┴──────────┐
                             │   NORMALIZER LAYER   │
                             │  (Dedup + Clean)     │
                             └───────────┬──────────┘
                                         │
                                events.normalized.v1
                                         │
                             ┌───────────┴──────────┐
                             │    TRIAGE LAYER      │
                             │  (2-Stage Filter)    │
                             └───────────┬──────────┘
                                         │
                          ┌──────────────┼──────────────┐
                          │              │              │
                     Priority:      Priority:      Priority:
                      HELD           HIGH          NORMAL
                          │              │              │
                          ▼              ▼              ▼
                    [Guardian      [Fast Path]    [Batch Overnight]
                     Pipeline]          │               │
                          │              │               │
                          │              ▼               ▼
                          │      ┌─────────────────────────┐
                          │      │  STANDARDIZER (IA)      │
                          │      │  GPT/Claude → NewsCards │
                          │      └──────────┬──────────────┘
                          │                 │
                          │                 ▼
                          │      ┌──────────────────────────┐
                          │      │   PostgreSQL             │
                          │      │   NewsCards Table        │
                          │      │   + TimescaleDB (OHLCV)  │
                          │      └──────────┬───────────────┘
                          │                 │
                          └─────────────────┤
                                            │
                    ┌───────────────────────┴──────────────┐
                    │      REGIME-AWARE CONTROLLER         │
                    │  (Détecte : Overnight|PreMkt|Open|   │
                    │           PostMkt + Volatility)      │
                    └───────────────────┬──────────────────┘
                                        │
          ┌─────────────────────────────┼────────────────────┐
          │                             │                    │
     OVERNIGHT                      PRE-MARKET           MARKET OPEN
          │                             │                    │
          ▼                             ▼                    ▼
  ┌───────────────┐           ┌─────────────────┐    ┌─────────────────┐
  │ Deep Analysis │           │  Plan Builder   │    │ Decision Engine │
  │ (Opus/o1)     │           │  (Opus)         │    │  (LangGraph +   │
  │ → Enrichment  │           │ → Scenarios     │    │   Sonnet/Haiku) │
  └───────┬───────┘           └────────┬────────┘    └────────┬────────┘
          │                            │                       │
          ▼                            ▼                       ▼
  ┌───────────────┐           ┌──────────────────┐   ┌────────────────┐
  │ Feature Store │           │  Scenario Bank   │   │  Signal Final  │
  │ (TimescaleDB) │           │  (PostgreSQL)    │   │  (BUY/SELL/    │
  └───────────────┘           └──────────────────┘   │   HOLD)        │
                                                      └────────┬───────┘
                                                               │
                                                      ┌────────┴────────┐
                                                      │  Risk Gate Hard │
                                                      │  + Pre-Flight   │
                                                      └────────┬────────┘
                                                               │
                                                      ┌────────┴────────┐
                                                      │ Execution Layer │
                                                      │  (IBKR Adapter) │
                                                      └────────┬────────┘
                                                               │
                                                      ┌────────┴────────┐
                                                      │   PostgreSQL    │
                                                      │ Orders+Positions│
                                                      └────────┬────────┘
                                                               │
                                                      ┌────────┴────────┐
                                                      │ Position Watcher│
                                                      │  (Guardian)     │
                                                      └─────────────────┘
```

### Topics Redpanda (Kafka)

| Topic | Producteur | Consommateur | Rétention | Partitions |
|-------|-----------|--------------|-----------|------------|
| `events.raw.v1` | Collectors | Normalizer | 7 jours | 10 |
| `events.normalized.v1` | Normalizer | Triage | 7 jours | 10 |
| `events.triaged.v1` | Triage | Standardizer | 3 jours | 5 |
| `newscards.v1` | Standardizer | Plan Builder + Decision | 30 jours | 5 |
| `market.ohlcv.v1` | Market Collector | Feature Engine | 90 jours | 20 |
| `signals.final.v1` | Decision Engine | Risk Gate | 30 jours | 3 |
| `orders.intent.v1` | Risk Gate | Execution | 90 jours | 2 |
| `orders.executed.v1` | Execution | Position Watcher | 365 jours | 2 |
| `alerts.priority.v1` | Position Watcher + Sentinels | Decision Engine | 7 jours | 5 |
| `learning.outcomes.v1` | All | Meta-Learner | 365 jours | 1 |

---

## 5. MODULES DU SYSTÈME (DÉTAILLÉS) {#modules}

### MODULE 1 : COLLECTORS (Ingestion)

**Rôle** : Aspirer données brutes depuis sources externes 24/7

#### Composants
1. **RSS Collector**
   - Fréquence : Toutes les 5 minutes
   - Sources : 500+ feeds (Les Echos, Bloomberg, Reuters, etc.)
   - Output : Raw JSON → MinIO + event → Redpanda

2. **Twitter Collector**
   - Fréquence : Stream temps réel (si Premium) ou polling 1 min
   - Filtres : Hashtags financiers, comptes vérifiés, influencers
   - Volume : 100-10,000 tweets/jour selon budget

3. **Reddit Collector**
   - Subreddits : wallstreetbets, stocks, investing, options
   - Fréquence : Polling 2 minutes
   - Filtres : Score > 50, gilded posts

4. **News API Collector**
   - Sources : NewsAPI, Finnhub, Benzinga
   - Fréquence : Polling 5 minutes (rate-limited)

5. **Web Scraper**
   - Sites : Seeking Alpha, MarketWatch, Investing.com
   - Respecte robots.txt + rate limiting 1 req/5s
   - Utilise : Playwright (navigateur headless) pour JS-rendered content

6. **Market Data Collector**
   - Sources : Polygon.io (real-time), yfinance (delayed)
   - Fréquence : Tick-by-tick (real-time) ou 1 min bars
   - Stockage direct : TimescaleDB

#### Configuration Modulaire
```yaml
collectors:
  rss:
    enabled: true
    sources: config/rss_sources.yaml
    interval_seconds: 300
  
  twitter:
    enabled: true
    api_key: ${TWITTER_API_KEY}
    stream_mode: false  # true = real-time, false = polling
    interval_seconds: 60
  
  reddit:
    enabled: true
    subreddits: [wallstreetbets, stocks, investing]
    min_score: 50
```

#### GitHub Repos Utilisés
- **feedparser** : `https://github.com/kurtmckee/feedparser` (RSS)
- **tweepy** : `https://github.com/tweepy/tweepy` (Twitter)
- **PRAW** : `https://github.com/praw-dev/praw` (Reddit)
- **Playwright** : `https://github.com/microsoft/playwright-python` (Scraping)

---

### MODULE 2 : NORMALIZER (Nettoyage)

**Rôle** : Transformer données brutes en format unifié

#### Processus
1. **Déduplication**
   - BloomFilter (Redis) : Check si déjà vu dans les 24h
   - Hash content : MD5 du texte nettoyé
   - Si doublon → Drop, sinon → Continue

2. **Nettoyage Texte**
   - Suppression HTML tags, emojis, URLs
   - Normalisation Unicode
   - Détection langue (langdetect)
   - Si non-anglais/français → Drop ou traduire (Google Translate API)

3. **Timestamp Standardisation**
   - Conversion en UTC
   - Validation (reject si futur ou > 7 jours passé)

4. **Source Quality Scoring**
   - Whitelist : Bloomberg (+10), Reuters (+9)
   - Greylist : Sites inconnus (0)
   - Blacklist : Spam domains (-10, drop)

5. **Metadata Enrichment**
   - Géolocalisation (si mention lieu)
   - Extraction entités basique (regex pour $AAPL, @mentions)

#### Output Schema (Normalized Event)
```json
{
  "event_id": "uuid-v4",
  "source": "bloomberg",
  "source_quality": 9,
  "original_url": "https://...",
  "timestamp_utc": "2025-01-15T14:23:00Z",
  "text_clean": "Apple announces...",
  "language": "en",
  "dedup_key": "md5-hash",
  "entities_raw": ["$AAPL", "@tim_cook"],
  "minio_ref": "s3://raw/2025/01/15/event-abc123.json"
}
```

#### GitHub Repos
- **langdetect** : `https://github.com/Mimino666/langdetect`
- **pybloom_live** : `https://github.com/joseph-fox/python-bloomfilter`

---

### MODULE 3 : TRIAGE (Filtrage Intelligent)

**Rôle** : Réduire volume de 10,000 → 500 événements/jour pertinents

#### Stage 1 : Filtrage Déterministe (Fast Path)
**But** : Éliminer 70% du bruit en < 10ms

Règles dures :
- Contient mot-clé finance (earnings, SEC, Fed, merger, bankruptcy)
- OU mentionne ticker watchlist/held
- OU source_quality > 7
- Si aucun match → **DROP**

#### Stage 2 : Scoring NLP (Smart Path)
**But** : Scorer pertinence 0-100 sur les 30% restants

1. **NER rapide (spaCy)**
   - Extraction : ORG, MONEY, PERCENT, DATE
   - Si 0 entités → score -30

2. **Classifieur Léger** (FinBERT local ou DistilBERT fine-tuné)
   - Labels : earnings, macro, legal, product, rumor, noise
   - Si "noise" → DROP
   - Sinon → score = confidence × 100

3. **Context Scoring**
   - Si ticker dans watchlist → +20
   - Si ticker held → +50 (priorité absolue)
   - Si calendrier catalyst proche (< 48h) → +30

4. **Seuil Adaptatif**
   ```
   IF marché fermé: seuil = 40 (on garde plus)
   IF marché ouvert: seuil = 70 (top qualité seulement)
   IF position ouverte: seuil = 30 (ultra sensible)
   ```

#### Output
- Events triaged → 3 queues selon priority
  - `priority.HELD` → Traitement immédiat
  - `priority.HIGH` → Traitement < 5 min
  - `priority.NORMAL` → Batch overnight

#### GitHub Repos
- **spaCy** : `https://github.com/explosion/spaCy`
- **transformers** (FinBERT) : `https://github.com/huggingface/transformers`

---

### MODULE 4 : STANDARDIZER (NewsCard Generation)

**Rôle** : Transformer texte brut en objet structuré exploitable

#### Processus
1. **Sélection du Modèle IA** (selon priority)
   - HELD : Claude Sonnet (rapide + précis)
   - HIGH : Claude Haiku (ultra rapide)
   - NORMAL : Batch Opus overnight (qualité max)

2. **Prompt Engineering**
```
Tu es un analyste financier expert. Transforme cette actualité en NewsCard structurée.

INPUT:
{normalized_event}

OUTPUT (JSON strict):
{
  "event_id": "...",
  "entities": ["Apple Inc", "Tim Cook"],
  "tickers": ["AAPL"],
  "type": "product_announcement|earnings|guidance|macro|legal|...",
  "impact_direction": "positive|negative|mixed|neutral",
  "impact_strength": 0.0-1.0,
  "time_horizon": "intraday|days|weeks|months",
  "novelty": "new|repeat|update",
  "confidence": 0.0-1.0,
  "uncertainties": ["regulatory approval unclear", "..."],
  "why_it_matters": [
    "Could boost iPhone sales 10-15% in Q2",
    "Competes directly with Samsung Galaxy"
  ],
  "invalidated_if": [
    "SEC rejects proposal",
    "Competitor announces superior product"
  ],
  "evidence_refs": ["minio://...", "https://..."]
}

RÈGLES:
- Confiance < 0.5 si source_quality < 5
- Si impact unclear → neutral
- Liste 3-5 points pour why_it_matters
```

3. **Validation & Calibration**
   - Parse JSON (retry si malformed)
   - Calibrate confidence (empirical adjustment)
   - Cross-check tickers avec market data (drop si ticker inexistant)

4. **Stockage**
   - PostgreSQL : Metadata + relations
   - MinIO : NewsCard complète (archive)
   - Redis : Cache last 100 NewsCards par ticker

#### Configuration Multi-Provider
```yaml
standardizer:
  providers:
    - name: anthropic
      models:
        fast: claude-haiku-4-5-20251001
        medium: claude-sonnet-4-5-20250929
        deep: claude-opus-4-20250514
      api_key: ${ANTHROPIC_KEY}
      
    - name: openai
      models:
        fast: gpt-4o-mini
        medium: gpt-4o
        deep: o1-preview
      api_key: ${OPENAI_KEY}
      
  selection_logic: |
    IF priority == HELD: use fast
    ELIF priority == HIGH: use medium
    ELSE: use deep (overnight)
```

#### GitHub Repos
- **LangChain** : `https://github.com/langchain-ai/langchain`
- **anthropic-sdk-python** : `https://github.com/anthropics/anthropic-sdk-python`
- **openai-python** : `https://github.com/openai/openai-python`

---

### MODULE 5 : PLAN BUILDER (Pré-Ouverture)

**Rôle** : Générer scénarios stratégiques avant 09:30 ET

#### Timing
- **Déclenché** : 04:00 ET (début pre-market)
- **Complétion** : Avant 09:25 ET (5 min avant ouverture)

#### Inputs
1. **NewsCards overnight** (depuis 20:00 veille)
2. **OHLCV** : 90 derniers jours + pre-market activity
3. **Positions ouvertes** (si any)
4. **Catalyst Calendar** : Événements J+0, J+1, J+2
5. **Market Regime** : Bull/Bear/Volatile/Range/Flash
6. **Scenario Bank précédent** (pour continuité)

#### Processus (par Ticker Watchlist)
1. **Synthèse Multi-NewsCards**
   - Regroupe toutes NewsCards du ticker depuis 24h
   - Détecte contradictions (impact_direction divergent)
   - Si contradiction → Trigger web research

2. **Génération Scénarios** (Claude Opus ou GPT-o1)

Prompt :
```
Tu es un stratège quantitatif. Génère 3 scénarios pour AAPL.

CONTEXT:
- NewsCards (24h): [...]
- OHLCV (90d): [...]
- Position actuelle: None
- Catalysts proches: Earnings 2025-01-30 16:30 ET
- Market Regime: TRENDING_BULL

OUTPUT (JSON):
{
  "ticker": "AAPL",
  "scenarios": [
    {
      "id": "AAPL_bullish_Q1",
      "name": "Bullish Continuation",
      "bias": "bullish",
      "probability": 0.60,
      "entry_conditions": [
        "Pre-market > 185",
        "First 30min volume > 5M shares",
        "SPY green"
      ],
      "invalidation_triggers": [
        "Price < 182",
        "Volume spike + reversal",
        "Sector rotation signal"
      ],
      "targets": {
        "entry": 185.5,
        "stop": 182.0,
        "take_profit_1": 189.0,
        "take_profit_2": 192.0
      },
      "size_max_pct": 8,
      "time_horizon": "2-5 days",
      "reassess_if": [
        "Earnings call today 16:30",
        "Price reaches 192",
        "Loss > 1.5%"
      ],
      "reasoning": [
        "Strong overnight NewsCards (+0.82 avg impact)",
        "Technical: Above 50MA, RSI 58 (room to run)",
        "Momentum: Outperforming sector by 3%"
      ]
    },
    {
      "id": "AAPL_neutral_Q1",
      "name": "Range-Bound",
      "bias": "neutral",
      "probability": 0.30,
      ...
    },
    {
      "id": "AAPL_bearish_Q1",
      "name": "Breakdown Risk",
      "bias": "bearish",
      "probability": 0.10,
      ...
    }
  ],
  "version": "v1",
  "created_at": "2025-01-15T04:23:00Z",
  "valid_until": "2025-01-15T16:00:00Z",
  "catalysts_pending": [
    {
      "type": "earnings",
      "datetime": "2025-01-30T16:30:00Z",
      "action_before": "reduce_position_50%",
      "action_after": "reassess_immediately"
    }
  ]
}
```

3. **Stockage Scenario Bank**
   - PostgreSQL : Metadata + query rapide
   - MinIO : Version complète + rapport détaillé

4. **Génération Watchlist Dynamique**
   - Top 20 tickers selon :
     - Nombre de NewsCards positives
     - Momentum technique
     - Calendrier catalyst proche
     - Corrélation faible avec positions existantes

#### Scenario Updater (toutes les 2h pendant marché)
- **11:30 ET** : Intègre 2h de prix réel, ajuste scénarios
- **13:30 ET** : Nouvelle mise à jour
- **15:30 ET** : Dernière mise à jour (bias conservateur avant clôture)

Coût : ~1.20€/jour (4 updates × 20 tickers × 0.015€)

---

### MODULE 6 : DECISION ENGINE (LangGraph Orchestration)

**Rôle** : Décider BUY/SELL/HOLD en temps réel

#### Architecture LangGraph

```
                    [START]
                       ↓
              ┌────────────────┐
              │  Load Context  │
              │  (NewsCards +  │
              │   Scenarios +  │
              │   OHLCV +      │
              │   Positions)   │
              └────────┬───────┘
                       ↓
              ┌────────────────┐
              │ Match Scenarios│
              │ (Which plan    │
              │  fits current  │
              │  reality?)     │
              └────────┬───────┘
                       ↓
                 ┌─────┴─────┐
                 │ Confidence│
                 │   Check   │
                 └─────┬─────┘
                       │
         ┌─────────────┼─────────────┐
         │ < 0.5       │             │ > 0.7
         ↓             ↓ 0.5-0.7     ↓
   ┌─────────┐   ┌──────────┐  ┌─────────┐
   │  Need   │   │  Soft    │  │  High   │
   │  More   │   │  Go      │  │  Go     │
   │  Info?  │   └────┬─────┘  └────┬────┘
   └────┬────┘        │             │
        │             │             │
        ↓             │             │
   ┌─────────┐       │             │
   │   Web   │       │             │
   │ Research│       │             │
   │(Optional)│      │             │
   └────┬────┘       │             │
        │            │             │
        └────────────┴─────────────┘
                     ↓
              ┌─────────────┐
              │ Risk Gate   │
              │   Soft      │
              └──────┬──────┘
                     ↓
              ┌─────────────┐
              │ Risk Gate   │
              │   HARD      │
              │ (INVIOLABLE)│
              └──────┬──────┘
                     ↓
              ┌─────────────┐
              │ Pre-Flight  │
              │   Check     │
              └──────┬──────┘
                     ↓
                 [Signal Final]
```

#### Agents dans LangGraph

**Agent 1 : Context Loader**
- Charge : NewsCards (fenêtre 2h), Scenarios, OHLCV (1D + 5D), Positions, Risk limits
- Output : Pack structuré

**Agent 2 : Scenario Matcher**
- Compare reality vs. plans
- "Entry conditions AAPL_bullish remplies à 85%"
- Si multiple scénarios matchent → Pondère par probability

**Agent 3 : Confidence Evaluator**
- Agrège : match_score + NewsCard.confidence + technical_confirmation
- Si < 0.5 → Route vers "Need More Info"
- Si 0.5-0.7 → Route vers "Soft Go"
- Si > 0.7 → Route vers "High Go"

**Agent 4 : Web Researcher (conditionnel)**
- Déclenché si :
  - Confidence < 0.5 ET (contradiction OU source faible OU move inexpliqué)
  - OU ticker held ET événement majeur
- Utilise : Tavily Search API ou Perplexity
- Budget : 20 recherches/jour max
- Timeout : 15 secondes
- Output : Sources datées + extraits courts

**Agent 5 : Decision Maker (LLM)**
- Modèle : Claude Sonnet (fast) ou GPT-4o (balance)
- Prompt :
```
Tu es un trader professionnel. Décide pour {ticker}.

CONTEXT:
- Scenario actif : {scenario}
- NewsCards récentes : {newscards}
- Prix actuel : {price}
- Position : {position_state}
- Constraints : {risk_limits}
- Web research : {web_results} (si any)

DÉCISION (JSON strict):
{
  "action": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "reasoning": [
    "Scenario AAPL_bullish entry conditions met (85%)",
    "NewsCard +0.82 impact strength confirms",
    "Technical: Price above VWAP, volume surge"
  ],
  "plan": {
    "order_type": "LIMIT|MARKET",
    "quantity": 10,
    "limit_price": 185.5,
    "stop_loss": 182.0,
    "take_profit": [189.0, 192.0],
    "time_stop": "16:00" (sortie avant clôture si flat)
  },
  "alternatives_considered": [
    "HOLD: Insufficient volume confirmation",
    "Rejected: Volume at 120% avg, sufficient"
  ]
}
```

**Agent 6 : Risk Gate Soft**
- Vérifie overrides IA acceptables :
  - Adjust stop/target dans range ±20%
  - Hold position si thèse intacte malgré drawdown < 3%
- Log tous les overrides + justifications

**Agent 7 : Risk Gate Hard** (NON-IA, règles pures)
```python
HARD_RULES = {
    'max_position_size': 0.10,  # 10% capital
    'max_daily_loss': 0.03,     # 3% capital
    'max_drawdown_per_position': 0.05,
    'max_open_positions': 5,
    'stop_loss_required': True,
    'no_trading_after_daily_loss_hit': True,
    'no_naked_options': True,
    'min_liquidity_adv': 500_000  # shares
}

IF any violated → REJECT order + alert
```

**Agent 8 : Pre-Flight Check**
- Dernière validation avant envoi broker :
  - Catalyst dans 30 min ? → ABORT
  - Correlation > 0.7 avec position existante ? → REDUCE size
  - Spread bid-ask > 0.5% ? → WAIT or CANCEL
  - Régime market = FLASH_CRASH ? → ABORT
  - Liquidité suffisante ? → OK

#### Configuration Multi-Model
```yaml
decision_engine:
  langgraph:
    state_schema: schemas/decision_state.json
    max_loops: 5
    timeout_seconds: 30
    
  agents:
    decision_maker:
      providers:
        - name: anthropic
          model: claude-sonnet-4-5
          weight: 0.6
        - name: openai
          model: gpt-4o
          weight: 0.4
      selection: weighted_vote  # ou round_robin, a_b_test
      
    web_researcher:
      provider: tavily
      max_calls_per_day: 20
```

#### GitHub Repos
- **LangGraph** : `https://github.com/langchain-ai/langgraph`
- **Tavily** : `https://github.com/tavily-ai/tavily-python`

---

### MODULE 7 : EXECUTION LAYER (IBKR Adapter)

**Rôle** : Traduire Signal Final en ordre broker

#### Processus
1. **Consomme** topic `signals.final.v1`
2. **Re-check Risk Gate Hard** (defense in depth)
3. **Mapping ordre** :
```python
signal.action = BUY
signal.plan.order_type = LIMIT
signal.plan.limit_price = 185.5

→ IBKR API :
order = LimitOrder(
    action="BUY",
    totalQuantity=10,
    lmtPrice=185.5,
    tif="DAY",
    outsideRth=False
)
```

4. **Bracket Orders automatiques**
   - Attache stop_loss + take_profit en même temps (OCA group)
   - Si fill → stops activent automatiquement

5. **Publish** :
   - `orders.intent.v1` : Intent logged
   - `orders.executed.v1` : Confirmation (ou rejection + reason)

#### Gestion des Rejections
- **Insufficient buying power** → Alert + retry avec size réduite
- **Outside market hours** → Queue pour pre-market (si autorisé)
- **Invalid ticker** → Alert + disable ticker watchlist

#### Configuration
```yaml
execution:
  broker: interactive_brokers
  
  ibkr:
    host: ${IB_GATEWAY_HOST}
    port: 4002  # paper trading
    client_id: 1
    
  order_defaults:
    tif: DAY
    outside_rth: false
    transmit: true  # false = stage only
    
  retry_policy:
    max_attempts: 3
    backoff_seconds: [1, 5, 15]
```

#### GitHub Repos
- **ib_insync** : `https://github.com/erdewit/ib_insync`

---

### MODULE 8 : POSITION WATCHER (Guardian)

**Rôle** : Surveiller positions ouvertes + déclencher réévaluations

#### Niveaux de Vigilance

**PASSIVE** (PnL > +2%, vol normale)
- Check : Toutes les 30 minutes
- Actions : Aucune sauf si target atteint

**ACTIVE** (Position < 2h OU PnL -1% à +2%)
- Check : Toutes les 5 minutes
- Actions : Monitor volume, spread, news flow

**ALERT** (PnL -1% à -3% OU vol spike > 2σ)
- Check : Toutes les 1 minute
- Actions :
  - Trigger web research (autorisé)
  - Re-run Decision Engine avec context "position_in_danger"
  - Ajuste stop dynamiquement si volatilité augmente

**EMERGENCY** (PnL < -3% OU approche hard stop)
- Check : Temps réel (< 5 secondes)
- Actions :
  - Exit automatique si pas de rebond en 2 minutes
  - Alert humain (SMS/call si configuré)
  - Log incident complet

#### Market Sentinel (parallèle)
Surveille **tous les tickers** (pas seulement positions) pour :
- Circuit breaker triggered
- Flash crash detected (VIX > 40)
- Sector rotation signal
- Volume spike inexpliqué (> 5σ)

Si détecté → Publish `alerts.priority.v1` → Réévaluation immédiate

#### Exit Automatique
- **Stop loss hit** → Exit market order
- **Time stop** (ex: 15:55 ET si intraday strategy) → Exit
- **Catalyst imminent** (< 5 min) → Exit 50% position
- **Emergency regime** → Exit ALL positions

---

### MODULE 9 : MEMORY & LEARNING

**Rôle** : Apprendre des erreurs, améliorer au fil du temps

#### Decision Log (chaque trade)
```json
{
  "trade_id": "uuid",
  "timestamp": "2025-01-15T10:23:00Z",
  "ticker": "AAPL",
  
  "input_pack": {
    "newscards": [...],
    "scenario": {...},
    "ohlcv": {...},
    "regime": "TRENDING_BULL"
  },
  
  "signal": {
    "action": "BUY",
    "confidence": 0.78,
    "reasoning": [...]
  },
  
  "execution": {
    "entry_price": 185.50,
    "exit_price": 189.20,
    "duration_minutes": 127,
    "exit_reason": "take_profit_1"
  },
  
  "outcome": {
    "pnl_dollars": 37.00,
    "pnl_pct": 1.99,
    "max_adverse_excursion": -0.32,
    "max_favorable_excursion": 2.15
  },
  
  "post_mortem": {
    "what_worked": [
      "Scenario entry conditions accurate",
      "NewsCard impact confirmed by price action"
    ],
    "what_failed": [],
    "luck_factor": 0.2  # 20% luck, 80% skill
  }
}
```

#### Meta-Learner (hebdomadaire, dimanche 20:00 ET)

**Étape 1 : Analyse des 50 derniers trades**
```
Agent Meta (Claude Opus):
Analyse ces 50 trades. Détecte patterns.

OUTPUT:
{
  "patterns_winning": [
    {
      "id": "PATTERN_47",
      "description": "NewsCard.type='guidance_upgrade' + Scenario.bias='neutral' + time < 11:00",
      "win_rate": 0.78,
      "sample_size": 23,
      "avg_gain": 1.8,
      "action": "boost_confidence_+15%"
    }
  ],
  "anti_patterns": [
    {
      "id": "ANTIPATTERN_12",
      "description": "NewsCard.novelty='repeat' + impact_strength > 0.8",
      "false_alarm_rate": 0.82,
      "sample_size": 17,
      "action": "penalize_confidence_-20%"
    }
  ],
  "scenario_performance": {
    "AAPL_bullish_Q1": {"win_rate": 0.65, "keep": true},
    "NVDA_bearish_Q1": {"win_rate": 0.38, "action": "revise_or_drop"}
  }
}
```

**Étape 2 : Mise à jour Confidence Modifiers**
```python
# Stocké en DB, utilisé par Decision Engine
confidence_modifiers = {
    'PATTERN_47': +0.15,
    'ANTIPATTERN_12': -0.20,
    ...
}

# Appliqué lors de décision :
base_confidence = 0.70
if matches_pattern('PATTERN_47'):
    adjusted_confidence = 0.70 + 0.15 = 0.85
```

**Étape 3 : Prompt Evolution**
- Teste variations de prompts sur trades passés
- Garde top performers
- Archive sous-performers

**Étape 4 : Rapport Weekly**
- Generate PDF report (MinIO)
- Key metrics : Win rate, Sharpe, max drawdown, top/worst trades
- Recommandations : Quels tickers ajouter/retirer watchlist

#### Confidence Calibration (mensuelle)
```python
# Après 1000 NewsCards
buckets = {
    '0.9-1.0': {'predicted': 0.95, 'actual_accuracy': 0.71},
    '0.7-0.9': {'predicted': 0.80, 'actual_accuracy': 0.68},
    ...
}

# Crée fonction calibration
def calibrate(raw_conf):
    if raw_conf > 0.9:
        return raw_conf * 0.75
    elif raw_conf > 0.7:
        return raw_conf * 0.85
    return raw_conf

# Applique à toutes nouvelles NewsCards
```

---

## 6. RÉGIMES TEMPORELS & COMPORTEMENTS {#regimes}

### Overnight (20:00→04:00 ET) — Deep Thinking

**Objectifs** :
- Accumuler toutes les news de la journée
- Nettoyer, trier, standardiser en NewsCards (qualité > vitesse)
- Analyser en profondeur (Opus, pas de limite temps)

**Comportement** :
- Collectors : Mode normal (polling 5 min)
- Triage : Seuil = 40 (on garde plus)
- Standardizer : Batch processing, Opus pour qualité max
- Coût : 70% du budget IA journalier (mais c'est ok, on a le temps)

### Pre-Market (04:00→09:30 ET) — Plan Generation

**Objectifs** :
- Générer Scenario Bank pour tous tickers watchlist
- Identifier tops opportunités
- Préparer triggers d'entrée

**Comportement** :
- Plan Builder : Activé (Opus)
- Scenario Updater : Première version (v1)
- Collectors : Mode accéléré (polling 1 min pour pré-marché)
- Deadline : 09:25 ET (plans doivent être prêts)

### Market Open (09:30→16:00 ET) — Fast React

**Objectifs** :
- Réagir aux news en < 30 secondes
- Matcher reality vs. scénarios
- Exécuter trades avec latence minimale

**Comportement** :
- Collectors : Mode temps réel (si stream available)
- Triage : Seuil = 70 (top qualité seulement)
- Standardizer : Haiku (rapide) pour priority HIGH
- Decision Engine : Actif, timeout 10 secondes
- Scenario Updater : Toutes les 2h (11:30, 13:30, 15:30)
- Position Watcher : Niveau vigilance adaptatif

**Optimisation latence** :
- Cache Redis : Last 100 NewsCards par ticker
- Pre-computed features : VWAP, RSI, MACD (TimescaleDB continuous aggregates)
- LangGraph max_loops = 3 (vs. 5 overnight)

### Post-Market (16:00→20:00 ET) — Review & Learning

**Objectifs** :
- Clôturer positions intraday
- Post-mortem trades du jour
- Mettre à jour mémoire

**Comportement** :
- Execution : Force exit positions intraday (si time_stop)
- Position Watcher : Génère post-mortem pour chaque trade fermé
- Decision Log : Enregistrement complet
- Collectors : Mode ralenti (polling 10 min)

---

## 7. SYSTÈME D'AGENTS IA {#agents-ia}

### Cartographie des Agents

| Agent | Rôle | Modèle(s) | Fréquence | Coût/call |
|-------|------|-----------|-----------|-----------|
| **Standardizer** | NewsCard generation | Haiku/Sonnet/Opus | 500-5000/jour | 0.0003-0.015€ |
| **Plan Builder** | Scenario generation | Opus/o1 | 20/jour | 0.075€ |
| **Scenario Updater** | Ajustement continu | Sonnet | 80/jour (20×4) | 0.015€ |
| **Decision Maker** | BUY/SELL/HOLD | Sonnet/GPT-4o | 30-100/jour | 0.015€ |
| **Web Researcher** | Info complémentaire | Tavily+Haiku | 0-20/jour | 0.01€ |
| **Position Guardian** | Surveillance | Haiku | 100-1000/jour | 0.0003€ |
| **Meta-Learner** | Pattern detection | Opus | 1/semaine | 0.075€ |
| **Confidence Calibrator** | Ajustement empirique | Opus | 1/mois | 0.075€ |

### Multi-Provider Strategy

**Pourquoi** :
- Résilience (si une API down, switch to autre)
- A/B testing (quel modèle performe mieux ?)
- Coût optimization (use cheap pour simple, expensive pour complex)

**Implémentation** :
```yaml
agents:
  standardizer:
    strategy: round_robin  # ou weighted_vote, a_b_test, cost_optimize
    
    providers:
      - anthropic:
          models: [haiku, sonnet, opus]
          weight: 0.6
      - openai:
          models: [gpt-4o-mini, gpt-4o, o1]
          weight: 0.4
          
  fallback_chain:
    - primary: anthropic/sonnet
    - secondary: openai/gpt-4o
    - tertiary: local/llama-70b
```

**Testing Framework** :
- Track performance par modèle
- Après 100 trades : Compare win rate Claude vs. GPT
- Auto-adjust weights selon résultats

---

## 8. GESTION DU RISQUE {#risque}

### Risk Gate Hard (Inviolable)

```python
HARD_LIMITS = {
    # Position sizing
    'max_position_pct_capital': 0.10,          # 10% max par position
    'max_correlated_exposure': 0.25,           # 25% max dans positions corrélées > 0.7
    'max_sector_exposure': 0.30,               # 30% max dans un secteur
    
    # Loss limits
    'max_daily_loss_pct': 0.03,                # 3% capital/jour
    'max_position_loss_pct': 0.05,             # 5% par position
    'max_drawdown_from_peak': 0.15,            # 15% depuis ATH
    
    # Position limits
    'max_open_positions': 5,
    'max_trades_per_day': 10,
    
    # Liquidity
    'min_daily_volume': 500_000,               # shares
    'max_spread_pct': 0.005,                   # 0.5% bid-ask
    
    # Mandatory protections
    'stop_loss_required': True,
    'max_time_in_position_minutes': 480,       # 8h max (pour intraday)
    
    # Circuit breakers
    'halt_if_vix_above': 40,
    'halt_if_market_circuit_breaker': True,
    'halt_if_daily_loss_hit': True
}
```

**Enforcement** : Code non-modifiable sans déploiement, log toute tentative violation.

### Risk Gate Soft (IA peut proposer)

```yaml
soft_limits:
  # IA peut ajuster stops
  stop_loss_adjustment_range: [-20%, +20%]
  
  # IA peut tenir position malgré drawdown
  hold_override_conditions:
    - max_drawdown: 0.025  # 2.5% max
    - thesis_intact: true
    - justification_required: true
    
  # IA peut suggérer size increase
  size_increase_conditions:
    - high_confidence: > 0.85
    - winning_streak: > 3
    - max_increase: 1.5x
```

**Validation** : Tous overrides soft nécessitent `reasoning` + sont loggés + peuvent demander approval humain.

### Pre-Flight Check

Avant chaque ordre, vérification finale :

```python
def pre_flight_check(signal, context):
    checks = []
    
    # 1. Catalyst imminent ?
    if catalyst_within_minutes(signal.ticker, 30):
        return ABORT("Catalyst < 30min")
    
    # 2. Correlation excessive ?
    corr = max_correlation_with_held(signal.ticker)
    if corr > 0.7:
        signal.plan.quantity *= 0.5  # Réduit size
        checks.append(WARN("High correlation, size reduced"))
    
    # 3. Régime market OK ?
    regime = get_market_regime()
    if regime == "FLASH_CRASH":
        return ABORT("Market in crisis mode")
    
    # 4. Liquidité OK ?
    if get_avg_daily_volume(signal.ticker) < 500_000:
        return ABORT("Insufficient liquidity")
    
    # 5. Spread raisonnable ?
    spread = get_current_spread(signal.ticker)
    if spread > 0.005:  # 0.5%
        return WAIT("Spread too wide, retry in 30s")
    
    # 6. NewsCard confidence calibrée OK ?
    if signal.confidence < 0.6:
        return ABORT("Confidence too low after calibration")
    
    # 7. Timing OK ?
    now = get_market_time()
    if now > "15:45":
        return ABORT("Too close to market close")
    
    return GO(checks)
```

### Correlation Guardian

**Rôle** : Éviter concentration sectorielle cachée

```python
# Matrice corrélation (rolling 30 jours)
correlation_matrix = calculate_rolling_correlation(
    tickers=watchlist + held_tickers,
    window_days=30
)

# Avant chaque trade
def check_correlation(new_ticker, held_positions):
    for pos in held_positions:
        corr = correlation_matrix[new_ticker][pos.ticker]
        
        if corr > 0.7:
            # Très corrélé
            if count_correlated_positions(new_ticker) >= 2:
                return REJECT("Already 2+ correlated positions")
            else:
                return REDUCE_SIZE(0.5)  # Moitié de la size prévue
        
        elif corr > 0.5:
            # Modérément corrélé
            return REDUCE_SIZE(0.75)
    
    return APPROVED()
```

**Surveillance continue** : Recalcul corrélations toutes les heures, alerte si "correlation creep" détecté.

---

## 9. REPOSITORIES GITHUB UTILISÉS {#github-repos}

### Infrastructure & Data

| Repo | URL | Usage |
|------|-----|-------|
| **Redpanda** | `https://github.com/redpanda-data/redpanda` | Kafka-compatible stream |
| **MinIO** | `https://github.com/minio/minio` | S3-compatible storage |
| **TimescaleDB** | `https://github.com/timescale/timescaledb` | Time-series PostgreSQL |
| **Neo4j** | `https://github.com/neo4j/neo4j` | Graph database |

### Data Collection

| Repo | URL | Usage |
|------|-----|-------|
| **feedparser** | `https://github.com/kurtmckee/feedparser` | RSS parsing |
| **tweepy** | `https://github.com/tweepy/tweepy` | Twitter API |
| **PRAW** | `https://github.com/praw-dev/praw` | Reddit API |
| **Playwright** | `https://github.com/microsoft/playwright-python` | Web scraping JS-rendered |
| **yfinance** | `https://github.com/ranaroussi/yfinance` | Yahoo Finance data |
| **ccxt** | `https://github.com/ccxt/ccxt` | Multi-exchange API (crypto) |

### NLP & ML

| Repo | URL | Usage |
|------|-----|-------|
| **spaCy** | `https://github.com/explosion/spaCy` | NER, POS tagging |
| **transformers** | `https://github.com/huggingface/transformers` | FinBERT, DistilBERT |
| **sentence-transformers** | `https://github.com/UKPLab/sentence-transformers` | Semantic embeddings |
| **langdetect** | `https://github.com/Mimino666/langdetect` | Language detection |

### IA & Agents

| Repo | URL | Usage |
|------|-----|-------|
| **LangChain** | `https://github.com/langchain-ai/langchain` | IA orchestration |
| **LangGraph** | `https://github.com/langchain-ai/langgraph` | Multi-agent workflows |
| **anthropic-sdk-python** | `https://github.com/anthropics/anthropic-sdk-python` | Claude API |
| **openai-python** | `https://github.com/openai/openai-python` | GPT API |
| **Tavily** | `https://github.com/tavily-ai/tavily-python` | Web research API |

### Trading & Backtesting

| Repo | URL | Usage |
|------|-----|-------|
| **ib_insync** | `https://github.com/erdewit/ib_insync` | Interactive Brokers API |
| **Backtrader** | `https://github.com/mementum/backtrader` | Backtesting framework |
| **VectorBT** | `https://github.com/polakowo/vectorbt` | Fast backtesting |
| **TA-Lib** | `https://github.com/mrjbq7/ta-lib` | Technical indicators |

### Monitoring & DevOps

| Repo | URL | Usage |
|------|-----|-------|
| **Prometheus** | `https://github.com/prometheus/prometheus` | Metrics |
| **Grafana** | `https://github.com/grafana/grafana` | Dashboards |
| **FastAPI** | `https://github.com/tiangolo/fastapi` | API backend |
| **pytest** | `https://github.com/pytest-dev/pytest` | Testing |

### Frontend

| Repo | URL | Usage |
|------|-----|-------|
| **React** | `https://github.com/facebook/react` | UI framework |
| **TanStack Query** | `https://github.com/TanStack/query` | Data fetching |
| **Recharts** | `https://github.com/recharts/recharts` | Financial charts |
| **Socket.IO** | `https://github.com/socketio/socket.io-client` | WebSocket real-time |

---

## 10. ORDRE DE MISE EN PLACE {#ordre-implementation}

### Phase 1 : Infrastructure (Semaine 1)

**Jour 1-2 : Base Services**
```bash
# Docker Compose setup
- Redpanda (Kafka)
- MinIO (S3)
- PostgreSQL + TimescaleDB
- Redis
- Prometheus + Grafana
- Kafka UI

# Validation :
✓ Redpanda : Producer/consumer test
✓ MinIO : Upload/download test
✓ TimescaleDB : Create hypertable test
✓ Redis : Set/get test
✓ Grafana : Dashboard accessibles
```

**Jour 3-4 : Market Data Pipeline**
```bash
# Modules :
- Market Data Collector (yfinance)
- TimescaleDB schema (OHLCV)
- Feature calculator (VWAP, RSI, MACD)

# Validation :
✓ 50 tickers historical data (90 jours)
✓ Real-time updates (1 min bars)
✓ Features calculées correctement
```

**Jour 5-7 : Monitoring**
```bash
# Setup :
- Prometheus scraping
- Grafana dashboards (system + trading)
- Alerting (PagerDuty/Slack)

# Dashboards créés :
1. Infrastructure (CPU, RAM, Disk, Network)
2. Redpanda (throughput, lag, errors)
3. Trading (signals/day, PnL, positions)
```

### Phase 2 : Data Collection (Semaine 2)

**Jour 8-10 : Collectors**
```bash
# Implémentation :
- RSS Collector (500 sources)
- Twitter Collector (100 tweets/jour)
- Reddit Collector (wallstreetbets, stocks)
- News API Collector (Finnhub)

# Test :
✓ 50 décisions simulées
✓ Reasoning cohérent
✓ Latence < 500ms (sans web research)
✓ Confidence scores calibrés
```

### Phase 4 : Risk & Execution (Semaine 5)

**Jour 29-31 : Risk Management**
```bash
# Implémentation :
- Risk Gate Hard (rules engine)
- Risk Gate Soft (IA overrides)
- Pre-Flight Check
- Correlation Guardian

# Test :
✓ Hard limits enforced (0 violations possibles)
✓ Soft overrides loggés
✓ Correlation matrix calculée
✓ Pre-flight rejette ordres dangereux
```

**Jour 32-35 : Execution Layer**
```bash
# Implémentation :
- IBKR connection (paper trading)
- Order adapter (signal → IBKR format)
- Bracket orders (stop + target)
- Rejection handling

# Test :
✓ Connection IBKR stable
✓ 10 ordres paper trade
✓ Stops automatiques déclenchés
✓ Fills confirmés
```

### Phase 5 : Guardian & Memory (Semaine 6)

**Jour 36-38 : Position Watcher**
```bash
# Implémentation :
- 4 niveaux vigilance
- Market Sentinel
- Auto-exit conditions
- Alerting (SMS/email)

# Test :
✓ Position surveillée en temps réel
✓ Niveaux vigilance switchent correctement
✓ Exit automatique sur stop
✓ Alertes reçues
```

**Jour 39-42 : Memory System**
```bash
# Implémentation :
- Decision Log (PostgreSQL)
- Post-mortem generator
- Meta-Learner (hebdomadaire)
- Confidence Calibrator (mensuel)

# Test :
✓ 50 trades loggés
✓ Post-mortem générés
✓ Patterns détectés
✓ Confidence modifiers appliqués
```

### Phase 6 : Frontend & Polish (Semaine 7)

**Jour 43-45 : API Backend**
```bash
# FastAPI endpoints :
- GET /positions/live
- GET /signals/today
- GET /newscards?ticker=AAPL
- GET /scenarios?ticker=AAPL
- GET /performance/metrics
- WebSocket /stream/updates

# Test :
✓ Tous endpoints répondent < 100ms
✓ WebSocket push temps réel
✓ Auth configuré (JWT)
```

**Jour 46-49 : Frontend Dashboard**
```bash
# React components :
- Portfolio Overview
- Live Positions Table
- Signals Feed (real-time)
- NewsCards Browser
- Performance Charts (PnL, Sharpe, Drawdown)
- Risk Metrics Display
- Agent Activity Monitor

# Test :
✓ UI responsive
✓ Real-time updates (WebSocket)
✓ Charts rendering correctly
```

### Phase 7 : Backtesting & Validation (Semaine 8)

**Jour 50-56 : Backtest Complet**
```bash
# Setup :
- Replay historical data (6 mois)
- Simulate entire system
- Measure : Sharpe, max DD, win rate

# Objectifs minimums :
✓ Sharpe > 1.5
✓ Max Drawdown < 15%
✓ Win rate > 52%
✓ Profit factor > 1.3

# Adjustments :
- Tune confidence thresholds
- Adjust stop/target ratios
- Refine scenario templates
```

### Phase 8 : Paper Trading (Semaine 9-12)

**4 Semaines Paper Trading**
```bash
# Objectifs :
- 200+ trades simulés
- Validation sur marché live
- Détection bugs production
- Tuning final

# Critères de passage en live :
✓ Sharpe paper > 1.3
✓ Max DD paper < 20%
✓ 0 violation risk limits
✓ Latence p95 < 1s
✓ Uptime > 99.5%
```

### Phase 9 : Live Trading (Semaine 13+)

**Déploiement Progressif**
```bash
# Semaine 13-14 : Capital limité (1000€)
- Max 1 position
- Max 2% capital/trade
- Stop agressif

# Semaine 15-16 : Si profitable (5000€)
- Max 3 positions
- Max 5% capital/trade

# Semaine 17+ : Scale progressif
- Augmente capital si Sharpe > 1.5
- Max 10% capital/trade
- Max 5 positions
```

---

## 11. MONITORING & OBSERVABILITÉ {#monitoring}

### Métriques Clés

#### Infrastructure
```yaml
system_metrics:
  - cpu_usage_pct
  - memory_usage_pct
  - disk_io_wait
  - network_throughput_mbps
  
redpanda_metrics:
  - messages_per_second
  - consumer_lag_seconds
  - partition_count
  - replication_factor
  
database_metrics:
  - query_latency_p95_ms
  - active_connections
  - cache_hit_rate_pct
  - disk_usage_pct
```

#### Trading
```yaml
trading_metrics:
  - signals_generated_per_day
  - signals_executed_pct
  - avg_latency_signal_to_order_ms
  - positions_open_count
  - pnl_daily_dollars
  - pnl_cumulative_dollars
  - sharpe_ratio_30d
  - max_drawdown_pct
  - win_rate_pct
  - profit_factor
  - avg_hold_time_minutes
  
risk_metrics:
  - risk_gate_rejections_per_day
  - correlation_max_current
  - sector_exposure_pct
  - daily_loss_pct_of_limit
  
ai_metrics:
  - api_calls_per_hour (par provider)
  - api_latency_p95_ms
  - api_cost_dollars_per_day
  - confidence_avg_pre_calibration
  - confidence_avg_post_calibration
```

### Dashboards Grafana

**1. System Health**
```
[CPU] [Memory] [Disk I/O] [Network]
[Redpanda Throughput] [Consumer Lag]
[PostgreSQL Connections] [Redis Memory]
[Alerts Active]
```

**2. Trading Overview**
```
[PnL Today] [PnL Cumulative] [Sharpe 30D]
[Positions Open] [Capital Deployed %]
[Signals Generated] [Execution Rate]
[Win Rate] [Profit Factor]
```

**3. AI Activity**
```
[API Calls/Hour] [Cost $/Day]
[Latency p95] [Provider Distribution]
[Confidence Distribution] [Calibration Drift]
```

**4. Risk Dashboard**
```
[Max Drawdown] [Daily Loss vs Limit]
[Correlation Heatmap] [Sector Exposure Pie]
[Risk Gate Rejections] [Position Sizes]
```

**5. Agent Performance**
```
[Standardizer: Throughput, Latency, Cost]
[Plan Builder: Scenarios/Day, Win Rate]
[Decision Engine: Signals/Day, Accuracy]
[Position Watcher: Alerts/Day, Exit Reasons]
```

### Alerting Rules

**Critical (PagerDuty + SMS)**
```yaml
- name: Daily Loss Limit Approaching
  condition: daily_loss_pct > 0.025  # 2.5% of 3% limit
  
- name: Max Drawdown Breached
  condition: drawdown_from_peak_pct > 0.15
  
- name: System Down
  condition: uptime_pct < 0.99 AND market_open == true
  
- name: Redpanda Consumer Lag High
  condition: consumer_lag_seconds > 60
```

**Warning (Slack)**
```yaml
- name: Win Rate Declining
  condition: win_rate_7d < 0.45
  
- name: Correlation Excessive
  condition: max_correlation > 0.75
  
- name: AI Cost Spike
  condition: ai_cost_hourly > 2x avg_last_7d
```

---

## 12. FRONTEND & VISUALISATION {#frontend}

### Architecture Frontend

```
React 18 App
├── src/
│   ├── components/
│   │   ├── Dashboard/
│   │   │   ├── PortfolioOverview.tsx
│   │   │   ├── LivePositions.tsx
│   │   │   └── PerformanceCharts.tsx
│   │   ├── Signals/
│   │   │   ├── SignalsFeed.tsx
│   │   │   ├── SignalDetail.tsx
│   │   │   └── SignalFilters.tsx
│   │   ├── NewsCards/
│   │   │   ├── NewsCardBrowser.tsx
│   │   │   ├── NewsCardTimeline.tsx
│   │   │   └── NewsCardDetail.tsx
│   │   ├── Scenarios/
│   │   │   ├── ScenarioBankView.tsx
│   │   │   └── ScenarioDetail.tsx
│   │   ├── Risk/
│   │   │   ├── RiskMetrics.tsx
│   │   │   ├── CorrelationMatrix.tsx
│   │   │   └── RiskGateLog.tsx
│   │   └── Agents/
│   │       ├── AgentActivity.tsx
│   │       └── AgentPerformance.tsx
│   ├── hooks/
│   │   ├── useWebSocket.ts
│   │   ├── useTradingData.ts
│   │   └── useRealTimeUpdates.ts
│   ├── api/
│   │   └── tradingApi.ts
│   └── utils/
│       ├── formatters.ts
│       └── calculations.ts
```

### Écrans Principaux

#### 1. Dashboard (Home)
```
┌─────────────────────────────────────────────────────────┐
│ 🏠 Trading Dashboard                     [User] [⚙️]    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  💰 PnL Today: +$127.50 (+1.27%)                       │
│  📊 Sharpe 30D: 1.87    Max DD: -8.2%                  │
│  📈 Positions: 3/5      Capital: 42% deployed          │
│                                                         │
├──────────────────┬──────────────────────────────────────┤
│ Live Positions   │  Performance Chart (30D)            │
│                  │                                      │
│ AAPL  +2.3% 🟢  │      [Line Chart: PnL curve]         │
│ NVDA  -0.8% 🔴  │                                      │
│ MSFT  +1.1% 🟢  │                                      │
│                  │                                      │
│ [View All]       │  [Sharpe] [Drawdown] [Win Rate]     │
├──────────────────┴──────────────────────────────────────┤
│ 🔔 Recent Signals                    🗞️ Latest NewsCards│
│                                                         │
│ 10:23 BUY TSLA (conf: 0.78)         AAPL: Product...   │
│ 11:45 SELL NVDA (conf: 0.82)        FED: Rate decision │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### 2. Live Positions
```
┌─────────────────────────────────────────────────────────┐
│ 📊 Live Positions                                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Ticker │ Entry  │ Current│ PnL   │ Guardian│ Action    │
│────────┼────────┼────────┼───────┼─────────┼───────────│
│ AAPL   │ 185.50 │ 189.77 │ +2.3% │ PASSIVE │ [Detail]  │
│ NVDA   │ 512.30 │ 508.12 │ -0.8% │ ACTIVE  │ [Detail]  │
│ MSFT   │ 378.20 │ 382.35 │ +1.1% │ PASSIVE │ [Detail]  │
│                                                         │
│ [Risk Metrics] [Correlation Matrix] [Add Position]     │
└─────────────────────────────────────────────────────────┘
```

#### 3. Signals Feed (Real-Time)
```
┌─────────────────────────────────────────────────────────┐
│ 🚨 Signals Feed                    [Filters ▼]          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 🟢 BUY  TSLA  @ 10:23:15  Conf: 0.78                   │
│    Scenario: Bullish continuation                      │
│    Entry: 245.50  Stop: 242.00  Target: 251.00        │
│    [View Reasoning] [Execute] [Reject]                 │
│                                                         │
│ 🔴 SELL NVDA  @ 11:45:32  Conf: 0.82                   │
│    Scenario: Take profit triggered                     │
│    Exit: 508.12  Gain: $37.50 (+0.73%)                │
│    [View Details] [✓ Executed]                         │
│                                                         │
│ ⚪ HOLD AAPL  @ 14:12:08  Conf: 0.65                   │
│    Scenario: Neutral range                             │
│    No action recommended                               │
│    [View Reasoning]                                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### 4. NewsCards Browser
```
┌─────────────────────────────────────────────────────────┐
│ 🗞️ NewsCards                      [Search] [Filters]    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 📰 AAPL: New Product Announcement                      │
│    Impact: +0.82 (positive) | Horizon: Days            │
│    Confidence: 0.87 | Novelty: New                     │
│    Why it matters:                                     │
│    • Could boost iPhone sales 10-15% in Q2             │
│    • Competes directly with Samsung Galaxy             │
│    [Full Detail] [Related Signals]                     │
│                                                         │
│ 📰 FED: Rate Decision Imminent                         │
│    Impact: -0.45 (negative) | Horizon: Intraday        │
│    Confidence: 0.92 | Novelty: Update                  │
│    [Full Detail]                                       │
│                                                         │
│ [Load More]                                            │
└─────────────────────────────────────────────────────────┘
```

#### 5. Scenario Bank
```
┌─────────────────────────────────────────────────────────┐
│ 🎯 Scenario Bank                   Ticker: [AAPL ▼]     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 📈 Bullish Continuation (v3)          Prob: 60%        │
│    Entry: Pre-market > 185, Volume > 5M                │
│    Target: 189 / 192   Stop: 182                       │
│    Status: 🟢 CONDITIONS MET (85%)                      │
│    [View Full] [History]                               │
│                                                         │
│ ➡️ Range-Bound (v2)                    Prob: 30%        │
│    Entry: Waiting for breakout                         │
│    Status: ⚪ MONITORING                                │
│    [View Full]                                         │
│                                                         │
│ 📉 Breakdown Risk (v1)                 Prob: 10%        │
│    Entry: If < 182                                     │
│    Status: ⚪ INACTIVE                                  │
│    [View Full]                                         │
│                                                         │
│ ⏰ Next Update: 11:30 ET (in 23 min)                   │
│ 📅 Catalysts: Earnings 2025-01-30 16:30 ET             │
└─────────────────────────────────────────────────────────┘
```

#### 6. Agent Activity Monitor
```
┌─────────────────────────────────────────────────────────┐
│ 🤖 Agent Activity                                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Agent          │ Status  │ Calls/H │ Latency│ Cost/H   │
│────────────────┼─────────┼─────────┼────────┼──────────│
│ Standardizer   │ 🟢 ACTIVE│ 42     │ 1.2s   │ $0.63    │
│ Decision Maker │ 🟢 ACTIVE│ 8      │ 0.4s   │ $0.12    │
│ Position Watch │ 🟢 ACTIVE│ 120    │ 0.1s   │ $0.04    │
│ Plan Builder   │ ⏸️ IDLE  │ 0      │ -      │ $0.00    │
│ Meta-Learner   │ ⏸️ IDLE  │ 0      │ -      │ $0.00    │
│                                                         │
│ 💰 Total Cost Today: $8.47 / $15 budget                │
│ 📊 Provider Distribution: Claude 70% | GPT 30%         │
└─────────────────────────────────────────────────────────┘
```

### WebSocket Updates

**Events Pushed to Frontend** :
```javascript
// Real-time events
{
  "type": "position_update",
  "data": {
    "ticker": "AAPL",
    "pnl_pct": 2.34,
    "guardian_level": "PASSIVE"
  }
}

{
  "type": "new_signal",
  "data": {
    "action": "BUY",
    "ticker": "TSLA",
    "confidence": 0.78
  }
}

{
  "type": "alert",
  "severity": "WARNING",
  "message": "Correlation threshold exceeded"
}
```

---

## 13. MODULARITÉ & TESTING {#modularite}

### Principes de Modularité

#### 1. Interface-Based Design
Chaque module expose une interface standard :

```python
# Interface abstraite
class Collector(ABC):
    @abstractmethod
    async def collect(self) -> List[RawEvent]:
        pass
    
    @abstractmethod
    def get_status(self) -> CollectorStatus:
        pass

# Implémentations concrètes
class RSSCollector(Collector):
    async def collect(self) -> List[RawEvent]:
        # Implementation
        
class TwitterCollector(Collector):
    async def collect(self) -> List[RawEvent]:
        # Implementation

# Usage : interchangeable
collectors = [
    RSSCollector(),
    TwitterCollector(),
    RedditCollector()
]

for collector in collectors:
    events = await collector.collect()  # Même interface
```

#### 2. Configuration-Driven
Tout est configurable sans code :

```yaml
# config/system.yaml
collectors:
  rss:
    enabled: true
    class: collectors.RSSCollector
    config_file: config/rss_sources.yaml
    
  twitter:
    enabled: ${TWITTER_ENABLED:-false}
    class: collectors.TwitterCollector
    api_key: ${TWITTER_API_KEY}

ai_providers:
  - name: anthropic
    enabled: true
    models:
      fast: claude-haiku-4-5
      medium: claude-sonnet-4-5
      deep: claude-opus-4
    api_key: ${ANTHROPIC_KEY}
    weight: 0.6
    
  - name: openai
    enabled: true
    models:
      fast: gpt-4o-mini
      medium: gpt-4o
      deep: o1-preview
    api_key: ${OPENAI_KEY}
    weight: 0.4
```

**Avantage** : Ajouter un nouveau collector = créer classe + entry config. Pas de refonte.

#### 3. Plugin Architecture
```python
# Plugin registry
class PluginRegistry:
    _plugins = {}
    
    @classmethod
    def register(cls, name, plugin_class):
        cls._plugins[name] = plugin_class
    
    @classmethod
    def get(cls, name):
        return cls._plugins.get(name)

# Auto-register via decorator
@register_collector("custom_news_source")
class CustomNewsCollector(Collector):
    async def collect(self):
        # Custom implementation
```

#### 4. A/B Testing Framework

```python
# Test multiple AI providers
class AIProviderSelector:
    def __init__(self, config):
        self.strategy = config.selection_strategy
        # round_robin | weighted_vote | a_b_test | cost_optimize
        
    async def select_provider(self, task):
        if self.strategy == "a_b_test":
            # 50% Claude, 50% GPT
            provider = random.choice(["anthropic", "openai"])
            
            # Log pour analyse
            log_ab_test(task_id, provider)
            
            return provider
        
        elif self.strategy == "weighted_vote":
            # Vote pondéré par performance historique
            weights = get_provider_weights()
            return weighted_random(weights)

# Après 100 calls, analyse
def analyze_ab_test():
    results = query_ab_test_results()
    
    # Claude: 78% accuracy, avg_cost 0.015€
    # GPT:    82% accuracy, avg_cost 0.012€
    
    # Conclusion : GPT meilleur
    update_weights({"anthropic": 0.3, "openai": 0.7})
```

### Testing Strategy

#### 1. Unit Tests
```python
# tests/unit/test_normalizer.py
import pytest
from src.preprocessing.normalizer import Normalizer

def test_deduplication():
    normalizer = Normalizer()
    
    event1 = {"text": "Apple announces..."}
    event2 = {"text": "Apple announces..."}  # Duplicate
    
    result1 = normalizer.process(event1)
    result2 = normalizer.process(event2)
    
    assert result1 is not None
    assert result2 is None  # Should be dropped

def test_timestamp_normalization():
    normalizer = Normalizer()
    
    event = {"timestamp": "2025-01-15 10:23:00 EST"}
    result = normalizer.process(event)
    
    assert result["timestamp_utc"].endswith("Z")
    assert result["timestamp_utc"] == "2025-01-15T15:23:00Z"
```

#### 2. Integration Tests
```python
# tests/integration/test_pipeline.py
@pytest.mark.integration
async def test_full_pipeline():
    # Setup
    redpanda = RedpandaClient(test_config)
    db = DatabaseClient(test_config)
    
    # Inject test event
    test_event = create_test_event("AAPL", "positive")
    await redpanda.publish("events.raw.v1", test_event)
    
    # Wait for processing
    await asyncio.sleep(5)
    
    # Verify NewsCard created
    newscard = await db.query_newscard(test_event.id)
    
    assert newscard is not None
    assert newscard.ticker == "AAPL"
    assert newscard.impact_direction == "positive"
```

#### 3. Backtesting Framework
```python
# tests/backtest/test_strategy.py
def test_strategy_on_historical_data():
    # Load 6 months historical data
    data = load_historical_data("2024-07-01", "2024-12-31")
    
    # Replay system
    backtest = BacktestEngine(
        data=data,
        initial_capital=10000,
        config=production_config
    )
    
    results = backtest.run()
    
    # Assert minimum performance
    assert results.sharpe_ratio > 1.5
    assert results.max_drawdown < 0.15
    assert results.win_rate > 0.52
```

#### 4. Property-Based Testing (Hypothesis)
```python
# tests/property/test_risk_gate.py
from hypothesis import given, strategies as st

@given(
    position_size=st.floats(min_value=0, max_value=1),
    capital=st.integers(min_value=1000, max_value=1000000)
)
def test_risk_gate_never_exceeds_limits(position_size, capital):
    risk_gate = RiskGateHard()
    
    # Property : aucune position > 10% capital
    max_allowed = capital * 0.10
    
    approved_size = risk_gate.check_position_size(
        position_size * capital,
        capital
    )
    
    assert approved_size <= max_allowed
```

#### 5. Chaos Engineering (Production)
```python
# tests/chaos/test_resilience.py
@pytest.mark.chaos
async def test_redpanda_failure_recovery():
    system = TradingSystem()
    await system.start()
    
    # Kill Redpanda mid-operation
    await chaos.kill_service("redpanda")
    
    # System should enter degraded mode
    await asyncio.sleep(10)
    assert system.status == "DEGRADED"
    
    # Restart Redpanda
    await chaos.restart_service("redpanda")
    
    # System should recover
    await asyncio.sleep(30)
    assert system.status == "HEALTHY"
    assert system.message_backlog_processed()
```

---

## CONCLUSION

### Récapitulatif de l'Architecture

Ce système représente une plateforme de trading algorithmique **de niveau institutionnel** conçue pour être :

✅ **Modulaire** : Chaque composant interchangeable
✅ **Scalable** : De 100 events/jour → 1M events/jour sans refonte
✅ **Résilient** : Survit aux pannes (Redpanda, IA APIs, broker)
✅ **Auditable** : Toute décision expliquée et rejouable
✅ **Adaptatif** : Apprend de ses erreurs automatiquement
✅ **Cost-Efficient** : 10-15€/jour (mode économique) avec capacité scale à 500€/jour

### Philosophie Centrale Rappelée

> **"PENSER profondément quand le marché dort, AGIR rapidement quand il est ouvert, PROTÉGER farouchement quand on est exposé"**

Cette architecture implémente cette philosophie à tous les niveaux :
- **Overnight** : Opus/o1 analysent en profondeur (temps illimité)
- **Pre-Market** : Plans stratégiques construits (scénarios robustes)
- **Market Open** : Haiku/Sonnet décident vite (latence < 500ms)
- **Guardian Mode** : Surveillance 24/7 des positions (protection active)

### Points Clés de Différenciation

**vs. Bots Retail Classiques** :
- Séparation temporelle (pense/agit/protège)
- NewsCards structurées (vs. texte brut)
- Scenario Bank (vs. réaction paniquée)
- Multi-provider IA (vs. vendor lock-in)
- Mémoire active (vs. amnésie totale)

**vs. Systèmes Institutionnels** :
- Coût 100x inférieur (utilise LLMs vs. armée d'analystes)
- Déploiement 10x plus rapide (Docker vs. infra legacy)
- Modularité maximale (vs. monolithe)
- Transparent & auditable (vs. boîte noire)

### Chemins d'Évolution Futurs

**Court Terme (3-6 mois)** :
- Multi-marchés (ajouter Europe, Asie)
- Options trading (calls/puts strategies)
- Crypto integration (24/7 trading)

**Moyen Terme (6-12 mois)** :
- Reinforcement Learning (RL agent apprend stratégies)
- Sentiment analysis avancé (audio earnings calls)
- Satellite data integration (parking lots, shipping)

**Long Terme (12+ mois)** :
- Multi-strategy portfolio (momentum + mean-reversion + arbitrage)
- Decentralized execution (MEV protection crypto)
- Automated market making (provide liquidité)

---

### Checklist Finale de Mise en Place

**Infrastructure** :
- [ ] Redpanda cluster opérationnel
- [ ] MinIO storage configuré avec rétention
- [ ] TimescaleDB + PostgreSQL schemas créés
- [ ] Redis cache configuré
- [ ] Prometheus + Grafana dashboards
- [ ] Kafka UI accessible

**Data Pipeline** :
- [ ] 5+ collectors actifs (RSS, Twitter, Reddit, News API, Market)
- [ ] Normalizer traite 1000+ events/jour
- [ ] Triage 2-stage fonctionne (70% drop stage 1)
- [ ] NewsCards générées (100+/jour)
- [ ] TimescaleDB ingère OHLCV (50+ tickers)

**IA Core** :
- [ ] Multi-provider configuré (Anthropic + OpenAI)
- [ ] Plan Builder génère scénarios (20 tickers)
- [ ] Decision Engine (LangGraph) opérationnel
- [ ] Scenario Updater tourne toutes les 2h
- [ ] Confidence calibration appliquée

**Risk & Execution** :
- [ ] Risk Gate Hard inviolable (0 violations possibles)
- [ ] Pre-Flight Check actif
- [ ] Correlation Guardian surveille
- [ ] IBKR connection stable (paper trading)
- [ ] Position Watcher 4 niveaux actif

**Memory & Learning** :
- [ ] Decision Log enregistre tous trades
- [ ] Post-mortem générés automatiquement
- [ ] Meta-Learner hebdomadaire configuré
- [ ] Confidence Calibrator mensuel

**Frontend** :
- [ ] Dashboard accessible
- [ ] WebSocket real-time updates fonctionnent
- [ ] Signals feed affiche en temps réel
- [ ] NewsCards browser opérationnel
- [ ] Scenario Bank visualisé
- [ ] Agent Activity Monitor actif

**Testing** :
- [ ] Unit tests (coverage > 80%)
- [ ] Integration tests passent
- [ ] Backtest 6 mois (Sharpe > 1.5)
- [ ] Paper trading 4 semaines (validation live)

**Production Readiness** :
- [ ] Alerting configuré (PagerDuty/Slack)
- [ ] Backup automatique (DB + MinIO)
- [ ] Disaster recovery plan documenté
- [ ] Runbook opérations créé
- [ ] Kill switch accessible

---

### Budget Estimatif (Mode Production Équilibré)

**Infrastructure (par mois)** :
- VPS/Cloud : $150-300 (selon scale)
- Redpanda Cloud : $0 (self-hosted) ou $200 (cloud)
- TimescaleDB Cloud : $0 (self-hosted) ou $150 (cloud)
- Neo4j : $0 (Community) ou $400 (Enterprise)
- MinIO : $0 (self-hosted storage)
- **Total Infra** : $150-1050/mois

**Data (par mois)** :
- NewsAPI Pro : $450
- Polygon.io Premium : $200
- Twitter API Premium : $100
- Benzinga (optionnel) : $300
- Economic Calendar : $0 (gratuit)
- **Total Data** : $750-1050/mois

**IA (par mois, 20 jours trading)** :
- Standardizer : ~$150
- Plan Builder : ~$30
- Decision Engine : ~$90
- Scenario Updater : ~$25
- Position Guardian : ~$20
- Meta-Learner : ~$3
- **Total IA** : $320/mois

**Broker** :
- Interactive Brokers : $0 frais mensuels
- Commissions : ~$0.005/action (variable selon volume)

**TOTAL MENSUEL : $1,220 - $2,420**

**ROI Requis** : Si capital géré = $50k, besoin 2.5-5% rendement/mois pour être rentable. Si capital = $200k, besoin 0.6-1.2%/mois.

---

### Contacts & Ressources

**Documentation Technique** :
- Redpanda : https://docs.redpanda.com
- TimescaleDB : https://docs.timescale.com
- LangGraph : https://langchain-ai.github.io/langgraph
- Interactive Brokers API : https://interactivebrokers.github.io

**Communautés** :
- r/algotrading (Reddit)
- QuantConnect Forums
- Quantopian Alumni Group
- Algorithmic Trading Discord

**Livres Recommandés** :
- "Advances in Financial Machine Learning" - Marcos López de Prado
- "Algorithmic Trading" - Ernest Chan
- "Machine Learning for Asset Managers" - Marcos López de Prado
- "Quantitative Trading" - Ernest Chan

---

### Avertissements Légaux & Éthiques

⚠️ **DISCLAIMER** :
- Ce système est à usage éducatif et personnel
- Trading comporte des risques de perte totale du capital
- Aucune garantie de performance future
- Respecter réglementations locales (MiFID II en Europe, SEC aux US)
- Ne constitue pas un conseil en investissement
- Tester exhaustivement en paper trading avant capital réel

⚠️ **RGPD & Données** :
- Scraping web : Respecter robots.txt et ToS des sites
- Données personnelles : Anonymiser si collecte réseaux sociaux
- Stockage : Chiffrement au repos recommandé

⚠️ **Manipulation de Marché** :
- Ne jamais publier signaux avant exécution (front-running)
- Ne pas coordonner avec d'autres bots (pump & dump)
- Respecter règles anti-manipulation ESMA/SEC

---

## ANNEXES

### A. Glossary Trading

**Alpha** : Rendement au-dessus du benchmark (ex: S&P500)
**Sharpe Ratio** : Rendement ajusté du risque (higher = better)
**Drawdown** : Perte depuis dernier pic (max acceptable : 15-20%)
**Slippage** : Différence prix espéré vs. exécuté
**VWAP** : Volume-Weighted Average Price (référence exécution)
**ATR** : Average True Range (mesure volatilité)
**RSI** : Relative Strength Index (overbought/oversold)

### B. Acronymes Techniques

**OHLCV** : Open, High, Low, Close, Volume
**NLP** : Natural Language Processing
**NER** : Named Entity Recognition
**LLM** : Large Language Model
**IBKR** : Interactive Brokers
**API** : Application Programming Interface
**SDK** : Software Development Kit
**ORM** : Object-Relational Mapping
**JWT** : JSON Web Token

### C. Commandes Utiles

```bash
# Démarrer système complet
docker-compose up -d

# Voir logs temps réel
docker-compose logs -f trading-app

# Arrêter proprement
docker-compose down

# Backup base de données
pg_dump trading > backup_$(date +%Y%m%d).sql

# Nettoyer Redpanda (reset topics)
docker exec redpanda rpk topic delete events.raw.v1

# Check santé système
curl http://localhost:8000/health

# Restart un service spécifique
docker-compose restart trading-app
```

### D. Troubleshooting Commun

**Problème** : Redpanda consumer lag élevé
**Solution** : Augmenter nombre de partitions ou parallelism consumers

**Problème** : TimescaleDB lent sur requêtes
**Solution** : Créer index sur (ticker, timestamp), activer compression

**Problème** : IA API timeout
**Solution** : Augmenter timeout, activer retry logic, check fallback provider

**Problème** : Position Watcher ne déclenche pas alertes
**Solution** : Vérifier Redis cache, check guardian_level logic, logs

**Problème** : Frontend ne reçoit pas updates WebSocket
**Solution** : Check CORS config, vérifier firewall, test WebSocket connection

---

**FIN DU DOCUMENT**

**Version** : 1.0
**Date** : Décembre 2025
**Auteur** : Architecture Trading System
**Licence** : Propriétaire - Usage Personnel

---

_Ce document constitue le blueprint complet pour implémenter un système de trading algorithmique de niveau institutionnel. Chaque section peut être approfondie selon les besoins spécifiques du déploiement._

_Pour questions ou clarifications sur des sections spécifiques, référez-vous aux repositories GitHub listés ou aux documentations officielles des technologies utilisées._

**📧 Support** : Créer issue sur repo GitHub du projet
**🔄 Mises à jour** : Check CHANGELOG.md pour évolutions

---

### REMERCIEMENTS

Ce système s'inspire des meilleures pratiques de :
- Renaissance Technologies (Medallion Fund)
- Two Sigma (machine learning approach)
- Citadel (risk management)
- Jane Street (systematic trading)

Adapté pour le retail avec technologies modernes open-source.

---

🚀 **BONNE CHANCE DANS VOTRE AVENTURE DE TRADING ALGORITHMIQUE !** 🚀
✓ 1000+ events/jour collectés
✓ Tous → MinIO + Redpanda
✓ Dedup fonctionne
```

**Jour 11-14 : Preprocessing**
```bash
# Modules :
- Normalizer (clean text, timestamps)
- Triage Stage 1 (règles dures)
- Triage Stage 2 (spaCy + FinBERT)

# Test :
✓ 70% bruit éliminé stage 1
✓ Scoring 0-100 sur 30% restants
✓ Seuil adaptatif fonctionne
```

### Phase 3 : IA Core (Semaine 3-4)

**Jour 15-18 : Standardizer**
```bash
# Implémentation :
- Prompt engineering NewsCard
- Multi-provider (Anthropic + OpenAI)
- Confidence calibration initiale
- PostgreSQL schema NewsCards

# Test :
✓ 100 NewsCards générées
✓ Validation structure JSON
✓ Stockage DB + MinIO
✓ Provider fallback fonctionne
```

**Jour 19-21 : Plan Builder**
```bash
# Implémentation :
- Scenario generation (Opus)
- Scenario Bank storage
- Watchlist dynamique
- Catalyst calendar integration

# Test :
✓ 20 scénarios générés (3 par ticker)
✓ Entry/exit conditions claires
✓ Reassessment triggers définis
```

**Jour 22-28 : Decision Engine**
```bash
# Implémentation :
- LangGraph workflow
- Context loading
- Scenario matching
- Web research (optionnel)
- Signal Final generation

# Test :   Decide    │
              │ (GPT/Claude)│
              │ → Signal    │
              └──────┬──────┘
                     ↓
              ┌─────────────┐
              │