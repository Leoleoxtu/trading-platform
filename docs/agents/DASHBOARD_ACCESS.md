# 🤖 Dashboard de Monitoring Claude - Guide d'Accès

## ✅ Le Dashboard est Opérationnel !

### 📊 Accès au Dashboard

**URL Principale** : http://localhost:8010

Ouvrez simplement cette URL dans votre navigateur pour voir :
- ✅ Activité en temps réel de toutes les interactions avec Claude
- ✅ Statistiques : nombre de completions, tokens, coûts
- ✅ Détails de chaque appel : prompt, réponse, latence, coût
- ✅ Mise à jour automatique via WebSocket

---

## 🔧 Commandes Utiles

### Démarrer le Dashboard
```bash
cd /home/leox7/trading-platform
source venv/bin/activate
python -m src.agents.monitor
```

Ou avec le script :
```bash
bash scripts/start_ai_monitor.sh
```

### En Arrière-Plan (déjà lancé)
```bash
nohup bash scripts/start_ai_monitor.sh > logs/ai_monitor.log 2>&1 &
```

### Vérifier le Status
```bash
# Voir les logs
tail -f logs/ai_monitor.log

# Tester l'API
curl http://localhost:8010/api/stats

# Voir si le processus tourne
ps aux | grep monitor
```

### Arrêter le Dashboard
```bash
pkill -f "src.agents.monitor"
```

---

## 🌐 Endpoints Disponibles

### 1. Dashboard Web (Interface Graphique)
**URL** : http://localhost:8010
- Interface graphique en temps réel
- Mise à jour automatique
- Design moderne et responsive

### 2. API - Activités Récentes
**URL** : http://localhost:8010/api/activities
**Paramètre** : `?limit=50` (nombre d'activités)
```bash
curl http://localhost:8010/api/activities?limit=20
```

### 3. API - Statistiques
**URL** : http://localhost:8010/api/stats
```bash
curl http://localhost:8010/api/stats | python3 -m json.tool
```

Résultat :
```json
{
    "total_completions": 0,
    "total_tokens": 0,
    "total_cost_usd": 0.0,
    "completions_by_model": {},
    "errors_count": 0
}
```

### 4. WebSocket (Temps Réel)
**URL** : ws://localhost:8010/ws
- Connexion automatique depuis le dashboard web
- Reçoit chaque nouvelle activité instantanément

---

## 📈 Ce Que Vous Verrez

### Dashboard Principal
```
┌─────────────────────────────────────────────┐
│      🤖 Claude AI Monitor                   │
│      🟢 Connected                           │
├─────────────────────────────────────────────┤
│  Total Completions │ Total Tokens │ Cost   │
│        42          │    12,458    │ $0.15  │
├─────────────────────────────────────────────┤
│  📊 Activité en Temps Réel                  │
│                                             │
│  ✅ claude-sonnet [14:32:15]               │
│     Event: evt_20241231_143215_001         │
│     📥 125 tokens │ 📤 234 tokens          │
│     💰 $0.0045   │ ⏱️ 1,234ms            │
│     Prompt: Analyze this news: Apple...    │
│     Response: This is a positive...        │
│                                             │
│  ✅ claude-haiku [14:32:10]                │
│     Event: evt_20241231_143210_001         │
│     📥 89 tokens  │ 📤 156 tokens          │
│     💰 $0.0012   │ ⏱️ 856ms              │
│                                             │
└─────────────────────────────────────────────┘
```

### Types d'Événements

**🔵 COMPLETION_START** (Bleu)
- L'IA commence à traiter une requête

**🟢 COMPLETION_SUCCESS** (Vert)
- Réponse réussie
- Affiche tokens, coût, latence
- Prévisualisation prompt/réponse

**🔴 COMPLETION_ERROR** (Rouge)
- Erreur durant le traitement
- Affiche le message d'erreur

**🟡 RETRY** (Jaune)
- Tentative de nouvelle requête après erreur

**🟠 RATE_LIMIT** (Orange)
- Limite de taux atteinte

---

## 🎨 Fonctionnalités du Dashboard

### Mise à Jour en Temps Réel
- ✅ Connexion WebSocket automatique
- ✅ Nouvel événement = animation d'apparition
- ✅ Stats mises à jour instantanément

### Informations Détaillées
Pour chaque appel à Claude :
- **Modèle utilisé** : Haiku ou Sonnet (badge coloré)
- **Tier** : fast, medium, ou deep
- **Event ID** : identifiant unique
- **Tokens** : entrée et sortie
- **Coût** : en USD (précision 4 décimales)
- **Latence** : en millisecondes
- **Prompt** : 100 premiers caractères
- **Réponse** : 200 premiers caractères

### Historique
- Garde les 50 dernières activités
- Scroll automatique pour nouvelles entrées
- Défilement manuel disponible

---

## 🧪 Tester le Dashboard

### Test Simple

1. **Ouvrir le dashboard** : http://localhost:8010
2. **Exécuter un test** :

```bash
cd /home/leox7/trading-platform
source venv/bin/activate
python examples/test_ai_providers.py
```

3. **Observer** : Les activités apparaissent en temps réel !

### Test Manuel avec Python

```python
import asyncio
from src.agents.providers import AnthropicProvider, ProviderConfig, CompletionRequest, ModelTier

# Configuration
config = ProviderConfig(
    name="anthropic",
    api_key=os.getenv("ANTHROPIC_API_KEY"),  # Load from .env
    models={
        "fast": "claude-haiku-4-5-20251001",
        "medium": "claude-sonnet-4-5-20250929",
    }
)

provider = AnthropicProvider(config)

# Requête test
request = CompletionRequest(
    prompt="Explain AI in 3 words",
    temperature=0.3,
    max_tokens=50
)

# Exécuter (et voir dans le dashboard !)
response = await provider.complete(request, tier=ModelTier.FAST)
print(response.content)
```

---

## 🔍 Dépannage

### Dashboard ne répond pas
```bash
# Vérifier le processus
ps aux | grep monitor

# Relancer
pkill -f "src.agents.monitor"
bash scripts/start_ai_monitor.sh
```

### Erreur "Module not found"
```bash
# Réinstaller dépendances
cd /home/leox7/trading-platform
source venv/bin/activate
pip install fastapi uvicorn websockets anthropic
```

### Port 8010 déjà utilisé
```bash
# Trouver le processus
lsof -i :8010

# Tuer le processus
kill -9 <PID>
```

### Clé API invalide
Vérifier dans `.env` :
```bash
cat .env | grep ANTHROPIC_API_KEY
```

---

## 📱 Accès depuis un autre appareil

### Sur le réseau local
1. Trouver l'IP de votre machine :
```bash
hostname -I
```

2. Ouvrir : `http://<VOTRE_IP>:8010`

### Via tunnel (accès public temporaire)
```bash
# Avec ngrok (installer d'abord)
ngrok http 8010
```

---

## 🎯 Intégration avec le Pipeline

Le monitoring est **automatique** dès que vous utilisez les providers Claude :

```python
# Dans votre code
from src.agents.providers import AnthropicProvider

# Chaque appel est automatiquement loggé dans le dashboard
response = await provider.complete(request, tier=ModelTier.MEDIUM)

# ✅ Visible instantanément sur http://localhost:8010
```

---

## 💡 Conseils d'Utilisation

### Pendant le Développement
- 🖥️ Gardez le dashboard ouvert dans un onglet séparé
- 👀 Surveillez les coûts en temps réel
- 🐛 Déboguez en voyant les prompts/réponses exacts
- ⏱️ Optimisez la latence en comparant fast vs medium

### En Production
- 📊 Utilisez l'API `/api/stats` pour monitoring automatisé
- 💰 Configurez des alertes sur les coûts
- 📈 Exportez les métriques vers Grafana (à venir)
- 🔍 Analysez les patterns d'erreurs

---

## 🚀 Prochaines Étapes

Une fois le dashboard opérationnel :

1. **Tester les providers** : `python examples/test_ai_providers.py`
2. **Créer les prompts** : Tâche 3.3 (NewsCard prompt template)
3. **Implémenter le Standardizer** : Tâche 3.4
4. **Observer en temps réel** : Voir chaque NewsCard générée !

---

**Status** : ✅ Dashboard opérationnel sur http://localhost:8010
**Documentation** : Ce fichier
**Support** : Voir logs dans `logs/ai_monitor.log`
