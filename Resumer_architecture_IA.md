# 🤖 RÉSUMÉ ARCHITECTURE IA - PLATEFORME TRADING

**Date de création** : 31 décembre 2025  
**Version** : 1.0  
**Statut** : ✅ Opérationnel (Phase 3 - AI Core en cours)

---

## 📊 ARCHITECTURE GLOBALE

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TRADING PLATFORM - AI LAYER                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    │                                │
        ┌───────────▼──────────┐       ┌────────────▼─────────────┐
        │   MONITORING         │       │   AI PROVIDERS           │
        │   (3 outils)         │       │   (Multi-provider)       │
        └──────────────────────┘       └──────────────────────────┘
                │                                   │
        ┌───────┴────────┐              ┌──────────┴──────────┐
        │                │              │                     │
    ┌───▼────┐   ┌──────▼─────┐   ┌───▼─────┐     ┌────────▼────────┐
    │Grafana │   │ Dashboard  │   │Anthropic│     │   LangSmith     │
    │(Infra) │   │ (AI Real-  │   │ Claude  │     │   (Tracing)     │
    │        │   │  time)     │   │ Haiku   │     │                 │
    │:3001   │   │ :8010      │   │ Sonnet  │     │ smith.langchain │
    └────────┘   └────────────┘   └─────────┘     └─────────────────┘
                                        │
                        ┌───────────────┴────────────────┐
                        │                                │
                ┌───────▼────────┐            ┌─────────▼──────────┐
                │  SCHEMAS       │            │  AGENTS (Future)   │
                │  - NewsCard    │            │  - Standardizer    │
                │  - Scenario    │            │  - Plan Builder    │
                │  - Signal      │            │  - Decision Engine │
                └────────────────┘            └────────────────────┘
```

---

## 🔧 COMPOSANTS INSTALLÉS

### 1. AI PROVIDERS (Multi-Provider Architecture)

**Localisation** : `src/agents/providers/`

```
src/agents/providers/
├── base_provider.py          # Interface abstraite
├── anthropic_provider.py     # Claude (ACTIF ✅)
└── openai_provider.py        # GPT (Désactivé ⏸️)
```

**Configuration** : `config/ai_providers.yaml`

```yaml
providers:
  - name: anthropic           # ✅ ACTIF (weight: 1.0)
    enabled: true
    models:
      fast: claude-haiku-4-5-20251001      # Rapide, $0.80/$4 per 1M tokens
      medium: claude-sonnet-4-5-20250929   # Équilibré, $3/$15 per 1M tokens
```

**Clés API** : `.env`
```bash
ANTHROPIC_API_KEY=sk-ant-api03-nSkp_yBgJ9h...
```

---

### 2. MONITORING (3 Systèmes)

#### A. Grafana (Infrastructure)
```
📍 URL: http://localhost:3001
🎯 Usage: Métriques système (CPU, RAM, Kafka, Postgres)
📊 Dashboards: Pipeline Health, Triage Stage 1/2, Feature Store
```

#### B. Dashboard Custom AI (Real-time)
```
📍 URL: http://localhost:8010
🎯 Usage: Monitoring AI en temps réel
📊 Métriques: Completions, tokens, coût, latence, modèles
🔄 WebSocket: Live updates
📁 Code: src/agents/monitor.py
```

**Démarrage** :
```bash
source venv/bin/activate
bash scripts/start_ai_monitor.sh
```

#### C. LangSmith (Tracing LLM)
```
📍 URL: https://smith.langchain.com/projects/trading-platform-prod
🎯 Usage: Traçage détaillé prompts/réponses
📊 Features: Trace chains, evaluation, A/B testing, datasets
💰 Gratuit: 5,000 traces/mois
```

**Configuration** : `.env`
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls-...
```

---

### 3. SCHEMAS (Structured Outputs)

**Localisation** : `src/agents/schemas.py`

```python
# NewsCard : Événement financier standardisé
class NewsCard(BaseModel):
    event_id: str
    entities: List[str]        # ["Apple Inc", "Tim Cook"]
    tickers: List[str]         # ["AAPL"]
    type: EventType            # product_announcement, earnings...
    impact_direction: str      # positive, negative, neutral
    impact_strength: float     # 0.0-1.0
    confidence: float          # 0.0-1.0
    why_it_matters: List[str]  # Raisons structurées

# Scenario : Décisions hypothétiques (Plan Builder)
class Scenario(BaseModel):
    scenario_id: str
    newscard_id: str
    market_context: Dict
    proposed_actions: List[Action]

# Signal : Ordre de trading (Decision Engine)
class Signal(BaseModel):
    signal_id: str
    ticker: str
    action: str               # BUY, SELL, HOLD
    confidence: float
    rationale: str
```

---

## 🎮 GUIDE D'UTILISATION

### ⚙️ CHANGER DE MODÈLE

#### Option 1 : Changer de tier (Haiku ↔ Sonnet)

**Dans le code** :
```python
from src.agents.providers.base_provider import ModelTier

# Utiliser Haiku (rapide, pas cher)
response = await provider.complete(request, tier=ModelTier.FAST)

# Utiliser Sonnet (meilleur, plus cher)
response = await provider.complete(request, tier=ModelTier.MEDIUM)
```

**Mapping des tiers** : `config/ai_providers.yaml`
```yaml
selection_strategy:
  tier_mapping:
    HELD: fast      # Événements bloqués → Haiku
    HIGH: fast      # Priorité haute → Haiku
    NORMAL: medium  # Priorité normale → Sonnet
    LOW: medium     # Priorité basse → Sonnet
```

#### Option 2 : Changer de modèle Claude

**Éditer** : `config/ai_providers.yaml`
```yaml
models:
  fast: claude-haiku-4-5-20251001     # Changer ici
  medium: claude-sonnet-4-5-20250929  # Ou ici
  # deep: claude-opus-4-20250514      # Décommenter si besoin
```

**Redémarrer** : Services consommateurs (après modification)

#### Option 3 : Ajouter OpenAI GPT

**1. Activer dans config** : `config/ai_providers.yaml`
```yaml
providers:
  - name: anthropic
    enabled: true
    weight: 0.7        # 70% des requêtes

  - name: openai      # AJOUTER
    enabled: true     # DÉCOMMENTER
    weight: 0.3       # 30% des requêtes
    models:
      fast: gpt-4o-mini
      medium: gpt-4o
```

**2. Ajouter clé API** : `.env`
```bash
OPENAI_API_KEY=sk-proj-...
```

**3. Installer SDK** :
```bash
source venv/bin/activate
pip install openai
```

---

### ⏸️ METTRE LE SYSTÈME EN PAUSE

#### Pause Complète (Tous les AI services)

**1. Désactiver tous les providers** : `config/ai_providers.yaml`
```yaml
providers:
  - name: anthropic
    enabled: false    # ⏸️ METTRE false
    weight: 0.0       # ⏸️ METTRE 0
```

**2. Arrêter le dashboard AI** :
```bash
pkill -f "python.*ai_monitor"
# OU
ps aux | grep ai_monitor
kill <PID>
```

**3. Désactiver LangSmith** : `.env`
```bash
LANGCHAIN_TRACING_V2=false    # ⏸️ Mettre false
```

#### Pause Partielle (Garder monitoring)

**Seulement désactiver providers** : `config/ai_providers.yaml`
```yaml
providers:
  - name: anthropic
    enabled: false    # ⏸️ Services AI arrêtés, monitoring actif
```

#### Pause Dashboard uniquement

```bash
# Arrêter dashboard
pkill -f "python.*ai_monitor"

# Redémarrer plus tard
cd /home/leox7/trading-platform
source venv/bin/activate
bash scripts/start_ai_monitor.sh
```

---

### 🔄 REDÉMARRER APRÈS PAUSE

**1. Réactiver providers** : `config/ai_providers.yaml`
```yaml
providers:
  - name: anthropic
    enabled: true     # ✅ Remettre true
    weight: 1.0       # ✅ Remettre poids
```

**2. Redémarrer dashboard** :
```bash
cd /home/leox7/trading-platform
source venv/bin/activate
bash scripts/start_ai_monitor.sh
```

**3. Réactiver LangSmith** : `.env`
```bash
LANGCHAIN_TRACING_V2=true
```

**4. Vérifier** :
```bash
# Dashboard actif ?
curl http://localhost:8010/api/stats

# Provider configuré ?
python -c "
import yaml
with open('config/ai_providers.yaml') as f:
    cfg = yaml.safe_load(f)
    print(f\"Anthropic enabled: {cfg['providers'][0]['enabled']}\")
"
```

---

## 💰 CONTRÔLE DES COÛTS

### Budget Quotidien

**Configuration** : `config/ai_providers.yaml`
```yaml
budget:
  daily_limit_usd: 100.0       # 🔴 LIMITE : $100/jour
  alert_threshold: 0.8         # Alerte à 80% ($80)
  rolling_window_hours: 24
```

**Monitoring en temps réel** :
```bash
# Dashboard
curl http://localhost:8010/api/stats | jq '.total_cost_usd'

# LangSmith
# → https://smith.langchain.com/projects/trading-platform-prod
# → Onglet "Usage"
```

### Tarification Claude (Décembre 2024)

| Modèle | Input ($/1M tokens) | Output ($/1M tokens) | Usage |
|--------|--------------------:|---------------------:|-------|
| **Haiku** (fast) | $0.80 | $4.00 | Triage rapide, classification |
| **Sonnet** (medium) | $3.00 | $15.00 | Analyse détaillée, NewsCards |
| **Opus** (deep) | $15.00 | $75.00 | Décisions critiques (pas encore utilisé) |

**Estimation** :
- 1 NewsCard (Sonnet) : ~500 tokens → **$0.0075**
- 1000 NewsCards/jour → **$7.50/jour**
- Triage préalable (Haiku) : ~200 tokens → **$0.0008**

---

## 🧪 TESTS ET VALIDATION

### Test Provider Anthropic

```bash
cd /home/leox7/trading-platform
source venv/bin/activate
python examples/test_ai_providers.py
```

**Résultat attendu** :
```
✅ Test Anthropic Provider
   Model: claude-haiku-4-5-20251001
   Tokens: 150
   Cost: $0.0012
   Latency: 850ms
```

### Test LangSmith Integration

```bash
source venv/bin/activate
python examples/test_langsmith_integration.py
```

**Résultat attendu** :
```
✅ Test 1: Simple completion - PASSED
✅ Test 2: Structured completion - PASSED
✅ Test 3: Multi-turn conversation - PASSED

🔍 View traces: https://smith.langchain.com/projects/trading-platform-prod
```

### Test Dashboard

```bash
# Vérifier dashboard actif
curl http://localhost:8010/api/stats

# Tester WebSocket
curl http://localhost:8010
```

---

## 📁 FICHIERS CLÉS

### Configuration

```
config/ai_providers.yaml        # 🔴 PRINCIPAL : Configuration providers
.env                            # 🔴 CLÉS API (secret)
requirements.txt                # Dépendances Python
```

### Code Source

```
src/agents/
├── providers/
│   ├── base_provider.py       # Interface abstraite
│   ├── anthropic_provider.py  # Claude (✅ actif)
│   └── openai_provider.py     # GPT (⏸️ inactif)
├── schemas.py                 # NewsCard, Scenario, Signal
└── monitor.py                 # Dashboard real-time
```

### Scripts

```
scripts/start_ai_monitor.sh    # Démarrer dashboard AI
examples/test_ai_providers.py  # Test providers
examples/test_langsmith_integration.py  # Test LangSmith
```

### Documentation

```
docs/agents/
├── README.md                  # Documentation complète
├── MONITORING_GUIDE.md        # Comparaison outils monitoring
├── LANGSMITH_SETUP.md         # Configuration LangSmith
└── DASHBOARD_ACCESS.md        # Accès dashboard custom
```

---

## 🚨 TROUBLESHOOTING

### ❌ Erreur "Authentication failed"

**Cause** : Clé API invalide ou expirée

**Solution** :
```bash
# Vérifier clé
cat .env | grep ANTHROPIC_API_KEY

# Tester clé
source venv/bin/activate
python -c "
from anthropic import Anthropic
client = Anthropic(api_key='sk-ant-...')
print('✅ Clé valide')
"
```

### ❌ Dashboard ne démarre pas (port 8010)

**Cause** : Port déjà utilisé

**Solution** :
```bash
# Trouver processus
lsof -i :8010
# OU
netstat -tulpn | grep 8010

# Tuer processus
kill <PID>

# Redémarrer
bash scripts/start_ai_monitor.sh
```

### ❌ LangSmith 403 Forbidden

**Cause** : Clé API placeholder ou invalide

**Solution** :
```bash
# Éditer .env
nano .env

# Remplacer
LANGCHAIN_API_KEY=ls-your-api-key-here

# Par vraie clé de smith.langchain.com
LANGCHAIN_API_KEY=ls-abc123...

# OU désactiver
LANGCHAIN_TRACING_V2=false
```

### ❌ Budget dépassé

**Symptôme** : Logs "Daily budget exceeded"

**Solution immédiate** :
```bash
# Désactiver temporairement
nano config/ai_providers.yaml
# enabled: false

# Attendre 24h (rolling window)
# OU augmenter budget
# daily_limit_usd: 200.0
```

---

## 📈 FLUX DE DONNÉES

```
┌─────────────────────────────────────────────────────────────┐
│  1. INGESTION (Reddit, RSS, Market Data)                    │
│     ↓                                                        │
│  2. NORMALISATION (events.normalized.v1)                    │
│     ↓                                                        │
│  3. TRIAGE STAGE 1 (events.triaged.stage1.v1)              │
│     ↓                                                        │
│  4. TRIAGE STAGE 2 (events.triaged.v1)                     │
│     ↓                                                        │
│  ┌──▼────────────────────────────────────────────────┐     │
│  │  5. AI STANDARDIZER 🤖 (FUTUR - Task 3.3-3.4)    │     │
│  │     • Consomme: events.triaged.v1                 │     │
│  │     • Provider: AnthropicProvider                  │     │
│  │     • Prompt: NewsCard template                    │     │
│  │     • Output: NewsCard (validé par schema)        │     │
│  │     • Publie: newscards.v1                        │     │
│  └───────────────────────────────────────────────────┘     │
│     ↓                                                        │
│  6. PLAN BUILDER 🤖 (FUTUR - Phase 3)                      │
│     • Input: NewsCard                                       │
│     • Output: Scenario                                      │
│     ↓                                                        │
│  7. DECISION ENGINE 🤖 (FUTUR - Phase 3)                   │
│     • Input: Scenario + Market Context                      │
│     • Output: Signal (BUY/SELL/HOLD)                       │
│     ↓                                                        │
│  8. EXECUTION (FUTUR - Phase 4)                            │
└─────────────────────────────────────────────────────────────┘
```

**État actuel** : ✅ Phase 1-2 complètes, 🚧 Phase 3 en cours (AI Core)

---

## 🎯 PROCHAINES ÉTAPES (Roadmap AI)

### ✅ TERMINÉ

- [x] Task 3.1 : Multi-Provider Setup
- [x] Task 3.2 : NewsCard Schema
- [x] LangSmith Integration
- [x] Dashboard Real-time
- [x] Grafana Infrastructure

### 🚧 EN COURS

- [ ] **Task 3.3** : Prompt Template NewsCard
  - Créer template avec variables {normalized_event}, {context}
  - Few-shot examples (3-5)
  - JSON output format

- [ ] **Task 3.4** : Standardizer Core
  - Consumer Kafka : events.triaged.v1
  - LLM call avec prompt template
  - Validation avec NewsCard schema
  - Publisher : newscards.v1

- [ ] **Task 3.5** : Confidence Calibration
  - Mesure de qualité des predictions
  - Ajustement dynamique des seuils

### 📅 FUTUR

- [ ] Task 3.6-3.7 : Plan Builder Agent
- [ ] Task 3.8-3.9 : Decision Engine
- [ ] Phase 4 : Backtesting & Execution

---

## 🔐 SÉCURITÉ

### Clés API (à protéger)

```bash
# NE JAMAIS COMMIT .env dans Git
echo ".env" >> .gitignore

# Vérifier
cat .gitignore | grep .env

# Sauvegarder ailleurs (secure vault)
cp .env .env.backup
```

### Variables Sensibles

```
ANTHROPIC_API_KEY=sk-ant-...     # 🔴 SECRET
OPENAI_API_KEY=sk-proj-...       # 🔴 SECRET (si ajouté)
LANGCHAIN_API_KEY=ls-...         # 🔴 SECRET
```

### Rate Limits

**Anthropic** :
- Tier 1 (défaut) : 50 req/min, 40,000 tokens/min
- Tier 2 : 1,000 req/min, 80,000 tokens/min

**Protection** :
- Retry automatique avec exponential backoff
- Rate limit detection et pause
- Budget quotidien configurable

---

## 📊 MÉTRIQUES À SURVEILLER

### Dashboard AI (:8010)

```
✅ total_completions        # Nombre total d'appels
✅ total_tokens            # Tokens consommés
✅ total_cost_usd          # Coût cumulé
✅ completions_by_model    # Distribution Haiku/Sonnet
✅ errors_count            # Erreurs
✅ avg_latency_ms          # Latence moyenne
```

### Grafana (:3001)

```
✅ ai_completions_total{provider, model, tier}
✅ ai_cost_usd_total{provider, model}
✅ ai_latency_seconds{provider, tier}
✅ ai_active_requests
✅ ai_errors_total{provider, error_type}
```

### LangSmith (cloud)

```
✅ Traces individuelles (prompt + response)
✅ Token usage par run
✅ Cost par run
✅ Latency distribution
✅ Error traces complètes
✅ Conversation chains
```

---

## 💡 BONNES PRATIQUES

### 1. Choix du Modèle

```python
# ✅ BON : Triage rapide avec Haiku
if task == "classification_simple":
    tier = ModelTier.FAST  # Haiku - $0.80/$4

# ✅ BON : Analyse détaillée avec Sonnet
if task == "newscard_generation":
    tier = ModelTier.MEDIUM  # Sonnet - $3/$15

# ❌ ÉVITER : Opus pour tout (trop cher)
tier = ModelTier.DEEP  # Opus - $15/$75 (réserver aux cas critiques)
```

### 2. Gestion des Erreurs

```python
from src.agents.providers.base_provider import (
    RateLimitError, 
    AuthenticationError,
    ProviderError
)

try:
    response = await provider.complete(request)
except RateLimitError:
    # Retry après pause
    await asyncio.sleep(60)
except AuthenticationError:
    # Vérifier clé API
    logger.error("Invalid API key")
except ProviderError as e:
    # Fallback ou alert
    logger.error(f"Provider failed: {e}")
```

### 3. Monitoring

```python
# ✅ BON : Log chaque appel pour monitoring
from src.agents.monitor import monitor, AIActivity

monitor.log_activity(AIActivity(
    provider="anthropic",
    model="claude-haiku-4-5-20251001",
    tokens=150,
    cost_usd=0.0012,
    latency_ms=850,
    success=True
))

# Dashboard et LangSmith reçoivent automatiquement
```

### 4. Cost Optimization

```python
# ✅ BON : Prompt court et précis
prompt = "Classify: {text}\nCategories: A, B, C"

# ❌ ÉVITER : Prompt verbeux
prompt = """
Please analyze the following text in great detail and 
provide a comprehensive classification considering all
aspects and nuances... [500 words de fluff]
"""

# 💡 Résultat : 10x moins de tokens = 10x moins cher
```

---

## 🎓 RESSOURCES

### Documentation Officielle

- **Anthropic Claude** : https://docs.anthropic.com
- **LangSmith** : https://docs.smith.langchain.com
- **LangChain** : https://python.langchain.com/docs

### Documentation Projet

- **README AI** : `docs/agents/README.md`
- **Monitoring Guide** : `docs/agents/MONITORING_GUIDE.md`
- **LangSmith Setup** : `docs/agents/LANGSMITH_SETUP.md`
- **Dashboard Access** : `docs/agents/DASHBOARD_ACCESS.md`

### Support

- **GitHub Issues** : (votre repo)
- **Anthropic Support** : support@anthropic.com
- **LangSmith Support** : https://smith.langchain.com/support

---

## 📞 CONTACTS ET ACCÈS RAPIDES

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3001 | admin / admin |
| **Dashboard AI** | http://localhost:8010 | Aucun (public local) |
| **LangSmith** | https://smith.langchain.com | Votre compte |
| **Anthropic Console** | https://console.anthropic.com | Votre compte |

---

## ✅ CHECKLIST MAINTENANCE

### Hebdomadaire

- [ ] Vérifier coûts cumulés (Dashboard + LangSmith)
- [ ] Vérifier latences moyennes (< 2s pour Haiku, < 5s pour Sonnet)
- [ ] Vérifier taux d'erreur (< 1%)
- [ ] Vérifier logs dashboard : `tail -f logs/ai_monitor.log`

### Mensuel

- [ ] Analyser distribution Haiku/Sonnet (optimiser cost)
- [ ] Review traces LangSmith (qualité des réponses)
- [ ] Mettre à jour modèles si nouvelles versions
- [ ] Backup configuration : `cp config/ai_providers.yaml config/ai_providers.yaml.backup`

### Avant Déploiement Production

- [ ] Tester failover (désactiver Anthropic, vérifier erreurs gracieuses)
- [ ] Configurer alertes (budget > 80%, latency > 5s)
- [ ] Sauvegarder `.env` dans vault sécurisé
- [ ] Documenter runbook incident response

---

## 🏁 RÉSUMÉ EXÉCUTIF

**Ce qui fonctionne aujourd'hui** :
- ✅ Infrastructure AI multi-provider (Anthropic Claude actif)
- ✅ 3 systèmes de monitoring (Grafana, Dashboard custom, LangSmith)
- ✅ Schemas structurés (NewsCard, Scenario, Signal)
- ✅ Tests automatisés et validés
- ✅ Documentation complète

**Commandes essentielles** :
```bash
# Démarrer dashboard
bash scripts/start_ai_monitor.sh

# Tester provider
python examples/test_ai_providers.py

# Voir status
curl http://localhost:8010/api/stats

# Pause AI
nano config/ai_providers.yaml  # enabled: false

# Redémarrer AI
nano config/ai_providers.yaml  # enabled: true
```

**Coût actuel** : ~$0/jour (pas encore en production)  
**Coût estimé production** : $5-15/jour (selon volume NewsCards)

**Next step** : Task 3.3 - Prompt Template NewsCard

---

**Dernière mise à jour** : 31 décembre 2025  
**Maintenu par** : Équipe Trading Platform  
**Version** : 1.0
