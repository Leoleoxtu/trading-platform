# 🚀 LangSmith - Guide de Configuration Finale

## ✅ Intégration Complète

LangSmith est maintenant **intégré dans le code** et prêt à l'emploi !

**Ce qui a été fait :**
- ✅ `langsmith` et `langchain-anthropic` installés
- ✅ Décorateur `@traceable` ajouté à `AnthropicProvider.complete()`
- ✅ Variables d'environnement configurées dans `.env`
- ✅ Test d'intégration créé : `examples/test_langsmith_integration.py`
- ✅ Documentation mise à jour

---

## 🔑 Configuration de la Clé API (Dernière Étape)

### Option 1 : Activer LangSmith (Recommandé)

**1. Créer un compte gratuit**
```bash
# Ouvrir dans le navigateur :
https://smith.langchain.com/signup
```

**2. Obtenir la clé API**
- Aller dans : **Settings → API Keys**
- Cliquer : **Create API Key**
- Copier la clé (format : `ls-abc123...`)

**3. Configurer `.env`**
```bash
# Éditer le fichier
nano /home/leox7/trading-platform/.env

# Remplacer cette ligne :
LANGCHAIN_API_KEY=ls-your-api-key-here

# Par votre vraie clé :
LANGCHAIN_API_KEY=ls-abc123def456...
```

**4. Tester**
```bash
cd /home/leox7/trading-platform
source venv/bin/activate
python examples/test_langsmith_integration.py
```

**5. Voir les traces**
```
https://smith.langchain.com/projects/trading-platform-prod
```

---

### Option 2 : Désactiver LangSmith (Gratuit)

Si vous préférez ne pas utiliser LangSmith (pas de compte), désactivez le tracing :

**Éditer `.env`**
```bash
nano /home/leox7/trading-platform/.env

# Changer cette ligne :
LANGCHAIN_TRACING_V2=true

# En :
LANGCHAIN_TRACING_V2=false
```

**Résultat** :
- ✅ Le code fonctionne normalement
- ✅ Pas d'erreurs 403
- ❌ Pas de traces dans LangSmith
- ✅ Vous pouvez toujours utiliser le dashboard custom (http://localhost:8010)

---

## 📊 Utilisation

### Avec LangSmith Activé

**Tous les appels Claude sont automatiquement tracés** :

```python
from src.agents.providers.anthropic_provider import AnthropicProvider
from src.agents.providers.base_provider import CompletionRequest, ModelTier

# Créer provider
provider = AnthropicProvider(config)

# Faire un appel (automatiquement tracé !)
response = await provider.complete(
    CompletionRequest(prompt="Analyze AAPL news"),
    tier=ModelTier.FAST
)

# → Voir dans LangSmith :
# - Prompt complet
# - Réponse complète
# - Tokens, latency, cost
# - Model (Haiku/Sonnet)
```

**Dashboard LangSmith affiche** :
- 📝 Prompt : "Analyze AAPL news"
- 💬 Response : [réponse complète]
- 🔢 Tokens : 150 (100 in, 50 out)
- ⏱️ Latency : 1234ms
- 💰 Cost : $0.0012
- 🎯 Model : claude-haiku-4-5-20251001

---

## 🔍 Test Rapide

```bash
cd /home/leox7/trading-platform
source venv/bin/activate

# Test avec configuration actuelle
python examples/test_langsmith_integration.py

# Si erreur 403 → Clé API invalide (voir Option 1)
# Si succès → Traces visibles sur smith.langchain.com
```

---

## 🆚 Comparaison : LangSmith vs Dashboard Custom

| Feature | LangSmith | Dashboard Custom |
|---------|-----------|------------------|
| **Coût** | Gratuit (5K/mois) puis $39/mois | Gratuit illimité |
| **Hosting** | Cloud (géré) | Self-hosted |
| **Setup** | Clé API | Rien |
| **Prompt/Response** | ✅ Complet | ⚠️ Limité |
| **Trace chains** | ✅ | ❌ |
| **Evaluation** | ✅ | ❌ |
| **Datasets** | ✅ | ❌ |
| **A/B testing** | ✅ | ❌ |
| **Real-time** | ✅ | ✅ |
| **Graphiques** | ✅ | ✅ |

---

## 💡 Recommandation

**Débutant / Prototype** :
- ✅ LangSmith désactivé (`LANGCHAIN_TRACING_V2=false`)
- ✅ Dashboard custom uniquement
- 💰 Coût : $0

**Développement / Debug** :
- ✅ LangSmith activé (free tier 5K traces)
- ✅ Dashboard custom pour monitoring temps réel
- 💰 Coût : $0 (jusqu'à 5K traces/mois)

**Production** :
- ✅ LangSmith Pro ($39/mois)
- ✅ Dashboard custom
- ✅ Grafana pour métriques système
- 💰 Coût : $39/mois

---

## 🐛 Troubleshooting

### Erreur 403 "Forbidden"

**Cause** : Clé API invalide ou pas configurée

**Solution** :
```bash
# Vérifier .env
cat .env | grep LANGCHAIN_API_KEY

# Si "ls-your-api-key-here" → Remplacer par vraie clé
# OU désactiver : LANGCHAIN_TRACING_V2=false
```

### Import Error "langsmith"

**Cause** : Package non installé

**Solution** :
```bash
source venv/bin/activate
pip install langsmith langchain-anthropic
```

### Pas de traces dans LangSmith

**Causes possibles** :
1. `LANGCHAIN_TRACING_V2=false` → Mettre `true`
2. Mauvaise clé API → Vérifier sur smith.langchain.com
3. Mauvais projet → Vérifier `LANGCHAIN_PROJECT` dans .env

---

## 📚 Documentation

**LangSmith** :
- Docs : https://docs.smith.langchain.com/
- Dashboard : https://smith.langchain.com
- Pricing : https://www.langchain.com/pricing

**Votre projet** :
- Guide monitoring : `docs/agents/MONITORING_GUIDE.md`
- Guide dashboard : `docs/agents/DASHBOARD_ACCESS.md`
- Documentation complète : `docs/agents/README.md`

---

## ✅ Checklist Finale

- [x] langsmith installé (`pip list | grep langsmith`)
- [x] Code modifié (`@traceable` dans anthropic_provider.py)
- [x] `.env` créé avec variables LANGCHAIN_*
- [ ] **Clé API configurée** (à faire si vous voulez activer LangSmith)
- [x] Test créé (`examples/test_langsmith_integration.py`)
- [x] Documentation mise à jour

**Prochaine étape** :
- Si vous voulez LangSmith → Obtenir clé API et configurer
- Sinon → Désactiver (`LANGCHAIN_TRACING_V2=false`)
- Puis continuer avec Task 3.3 (Prompt Templates)

---

**Status** : ✅ LangSmith intégré (à activer avec clé API)
