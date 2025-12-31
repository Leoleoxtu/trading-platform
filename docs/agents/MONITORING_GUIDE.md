# 🔍 Monitoring AI/LLM - Guide Complet

## Vue d'Ensemble des Solutions

### 📊 Architecture de Monitoring Recommandée

```
┌─────────────────────────────────────────────────────────────┐
│                    MONITORING STACK                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   GRAFANA    │    │  LANGSMITH   │    │   DASHBOARD  │ │
│  │   (Metrics)  │    │  (LLM Trace) │    │   (Real-time)│ │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘ │
│         │                   │                    │          │
│  ┌──────▼───────────────────▼────────────────────▼───────┐ │
│  │            PROMETHEUS (Métriques)                      │ │
│  └──────────────────────────────────────────────────────┬─┘ │
│                                                          │   │
│  ┌──────────────────────────────────────────────────────▼─┐ │
│  │        AI PROVIDERS (Claude Haiku/Sonnet)              │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. ✅ Grafana (Déjà Configuré)

### Métriques Actuelles Disponibles

**Port** : http://localhost:3001
**Datasource** : Prometheus (PBFA97CFB590B2093)

#### Dashboards Existants
- ✅ Triage Stage 1 Health
- ✅ Triage Stage 2 - NLP Pipeline
- ✅ Market Health
- ✅ Feature Store Health
- ✅ Pipeline Health
- ✅ Quick Start

#### Métriques AI Disponibles

```promql
# Métriques du dashboard custom AI (port 8010)
ai_completions_total{provider="anthropic", model="claude-haiku-4-5-20251001"}
ai_completions_total{provider="anthropic", model="claude-sonnet-4-5-20250929"}

# Coût total
ai_cost_usd_total{provider="anthropic"}

# Latence
ai_latency_seconds{provider="anthropic", tier="fast"}
ai_latency_seconds{provider="anthropic", tier="medium"}

# Requêtes actives
ai_active_requests
```

### Créer un Dashboard AI dans Grafana

**Panels recommandés :**
1. **Completions Rate** (completions/min)
2. **Token Usage** (tokens/sec)
3. **Cost** ($/hour)
4. **Latency P95** (ms)
5. **Error Rate** (%)
6. **Model Distribution** (pie chart)

---

## 2. 🔥 LangSmith (Recommandé pour LLMs)

### Pourquoi LangSmith ?

**Avantages sur Grafana pour les LLMs :**
- ✅ Trace **chaque prompt/réponse** en détail
- ✅ Debug interactif des conversations
- ✅ Evaluation de qualité des réponses
- ✅ Datasets pour testing
- ✅ Comparaison de modèles
- ✅ Coût par conversation
- ✅ UI spécialisée pour LLMs

### Installation

```bash
pip install langsmith langchain
```

### Configuration

**1. Créer un compte** : https://smith.langchain.com

**2. Obtenir API Key** : Settings → API Keys

**3. Configurer `.env`** :
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=ls-...
LANGCHAIN_PROJECT=trading-platform-prod
```

### Intégration avec le Code Existant

#### Option A : Wrapper Automatique (Simple)

```python
# Dans src/agents/providers/anthropic_provider.py
from langsmith import traceable
from langsmith.run_helpers import trace_as_chain_group

class AnthropicProvider(BaseProvider):
    
    @traceable(
        run_type="llm",
        name="claude_completion",
        project_name="trading-platform"
    )
    async def complete(
        self,
        request: CompletionRequest,
        tier: ModelTier = ModelTier.MEDIUM
    ) -> CompletionResponse:
        """Execute completion using Claude - traced by LangSmith"""
        
        # Tout le code existant reste identique
        # LangSmith capture automatiquement :
        # - Input (prompt)
        # - Output (response)
        # - Latency
        # - Model
        # - Tokens
        # - Cost
        
        # ... code existant ...
```

#### Option B : Intégration LangChain Complète

```python
# src/agents/langchain_wrapper.py
from langchain_anthropic import ChatAnthropic
from langchain.callbacks.tracers import LangChainTracer
from langchain.schema import HumanMessage, SystemMessage

class LangChainClaudeProvider:
    """Wrapper LangChain pour Claude avec tracing automatique"""
    
    def __init__(self, config):
        self.haiku = ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            anthropic_api_key=config.api_key,
            temperature=0.3,
        )
        
        self.sonnet = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            anthropic_api_key=config.api_key,
            temperature=0.3,
        )
        
        # LangSmith tracer (automatique si env vars configurées)
        self.tracer = LangChainTracer(project_name="trading-platform")
    
    async def complete(self, request: CompletionRequest, tier: ModelTier):
        """Completion with automatic LangSmith tracing"""
        
        model = self.haiku if tier == ModelTier.FAST else self.sonnet
        
        messages = []
        if request.system_prompt:
            messages.append(SystemMessage(content=request.system_prompt))
        messages.append(HumanMessage(content=request.prompt))
        
        # Appel automatiquement tracé par LangSmith
        response = await model.ainvoke(
            messages,
            config={"callbacks": [self.tracer]}
        )
        
        return response
```

### Utilisation

Une fois configuré, **chaque appel est automatiquement tracé** :

```python
# Votre code reste identique
response = await provider.complete(request, tier=ModelTier.FAST)

# Mais LangSmith capture tout automatiquement !
# Voir sur : https://smith.langchain.com/projects/<your-project>
```

### Dashboard LangSmith

**Accès** : https://smith.langchain.com

**Fonctionnalités** :
- 📊 Vue d'ensemble des runs
- 🔍 Recherche par prompt/réponse
- 📈 Métriques (latency, cost, tokens)
- 🐛 Debug de conversations complètes
- ⭐ Feedback/rating des réponses
- 📁 Datasets pour testing
- 🔬 Evaluation automatique

---

## 3. 🎨 LangFlow (UI Builder)

### C'est Quoi ?

**Interface visuelle** pour créer des workflows LangChain sans code :
- Drag & drop de composants
- Connexion visuelle LLM → Prompt → Output
- Export en Python
- Utile pour prototyper rapidement

### Installation

```bash
pip install langflow
langflow run
```

**Accès** : http://localhost:7860

### Cas d'Usage

**Bon pour** :
- ✅ Prototypage rapide
- ✅ Démonstrations
- ✅ Tests de prompts
- ✅ Non-développeurs

**Moins bon pour** :
- ❌ Production à grande échelle
- ❌ Logique complexe
- ❌ Intégration avec système existant

**Recommandation** : Utiliser pour prototyper, puis coder en Python.

---

## 4. 🎯 Recommandation Finale

### Stack de Monitoring Idéal

```
┌─────────────────────────────────────────────────────────┐
│  INFRASTRUCTURE METRICS (Grafana + Prometheus)          │
│  - CPU, RAM, Disk                                       │
│  - Pipeline throughput                                  │
│  - Service health                                       │
│  → Dashboard : http://localhost:3001                    │
└─────────────────────────────────────────────────────────┘
                         +
┌─────────────────────────────────────────────────────────┐
│  AI METRICS (Dashboard Custom)                          │
│  - Completions count                                    │
│  - Token usage                                          │
│  - Cost tracking                                        │
│  - Model distribution                                   │
│  → Dashboard : http://localhost:8010                    │
└─────────────────────────────────────────────────────────┘
                         +
┌─────────────────────────────────────────────────────────┐
│  LLM TRACING (LangSmith)                               │
│  - Detailed prompts/responses                           │
│  - Conversation flows                                   │
│  - Quality evaluation                                   │
│  - A/B testing                                          │
│  → Dashboard : https://smith.langchain.com              │
└─────────────────────────────────────────────────────────┘
```

### Implémentation Progressive

**Phase 1 : Actuellement ✅**
- Grafana (metrics infra)
- Dashboard custom (metrics AI basiques)

**Phase 2 : Ajouter LangSmith (Recommandé)**
- Tracing détaillé des LLMs
- Debug et evaluation
- Datasets de test

**Phase 3 : Optimisation**
- Exporter métriques LangSmith → Prometheus
- Dashboard unifié dans Grafana
- Alertes automatiques

---

## 5. 🚀 Implémentation LangSmith (Quick Start)

### Étape 1 : Installation

```bash
cd /home/leox7/trading-platform
source venv/bin/activate
pip install langsmith langchain-anthropic
```

### Étape 2 : Configuration

Ajouter à `.env` :
```bash
# LangSmith Configuration
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=ls-xxx  # Obtenir sur smith.langchain.com
LANGCHAIN_PROJECT=trading-platform-prod
```

### Étape 3 : Modifier le Provider

```bash
# Ajouter le décorateur @traceable
nano src/agents/providers/anthropic_provider.py
```

### Étape 4 : Vérifier

```python
# Test
python examples/test_ai_providers.py

# Voir les traces sur :
# https://smith.langchain.com/projects/trading-platform-prod
```

---

## 6. 📊 Métriques Disponibles par Outil

| Métrique | Grafana | Dashboard Custom | LangSmith |
|----------|---------|------------------|-----------|
| **Infrastructure** | ✅ | ❌ | ❌ |
| CPU/RAM/Network | ✅ | ❌ | ❌ |
| Service Health | ✅ | ❌ | ❌ |
| **AI - Agrégats** | ⚠️ | ✅ | ✅ |
| Completions/min | ⚠️ | ✅ | ✅ |
| Token usage | ⚠️ | ✅ | ✅ |
| Cost tracking | ⚠️ | ✅ | ✅ |
| Latency P95 | ⚠️ | ✅ | ✅ |
| **AI - Détails** | ❌ | ⚠️ | ✅ |
| Prompt complet | ❌ | ⚠️ | ✅ |
| Réponse complète | ❌ | ⚠️ | ✅ |
| Conversation flow | ❌ | ❌ | ✅ |
| Evaluation qualité | ❌ | ❌ | ✅ |
| A/B testing | ❌ | ❌ | ✅ |
| Datasets | ❌ | ❌ | ✅ |

**Légende** :
- ✅ Supporté nativement
- ⚠️ Possible mais limité
- ❌ Non supporté

---

## 7. 💰 Coûts

| Outil | Coût | Limites |
|-------|------|---------|
| **Grafana** | Gratuit (self-hosted) | Aucune |
| **Prometheus** | Gratuit (self-hosted) | Aucune |
| **Dashboard Custom** | Gratuit | Aucune |
| **LangSmith** | Gratuit : 5K traces/mois | Puis $39-99/mois |
| **LangFlow** | Gratuit (self-hosted) | Aucune |

---

## 8. 🎓 Ressources

### Documentation
- **Grafana** : https://grafana.com/docs/
- **LangSmith** : https://docs.smith.langchain.com/
- **LangChain** : https://python.langchain.com/docs/
- **LangFlow** : https://docs.langflow.org/

### Tutoriels
- LangSmith Quick Start : https://docs.smith.langchain.com/old/tracing/quick_start
- Grafana AI Dashboard : https://grafana.com/grafana/dashboards/

---

## ✅ Conclusion

**Pour votre projet** :

1. **Garder Grafana** pour l'infra et le pipeline
2. **Garder Dashboard Custom** (http://localhost:8010) pour metrics AI basiques
3. **Ajouter LangSmith** pour tracing détaillé des LLMs
4. **Skip LangFlow** (pas nécessaire, vous codez déjà)

**Installation recommandée** :
```bash
# 1. Installer LangSmith
pip install langsmith langchain-anthropic

# 2. Configurer .env (ajouter LANGCHAIN_*)

# 3. Ajouter @traceable aux providers

# 4. Profiter ! 🎉
```

**Vous aurez alors** :
- 📊 Grafana : Métriques système (déjà ✅)
- 🤖 Dashboard : Métriques AI temps réel (déjà ✅)
- 🔍 LangSmith : Tracing détaillé LLM (à ajouter)
