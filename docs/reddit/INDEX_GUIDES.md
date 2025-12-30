# 📚 Index des Guides - Trading Platform

Guide rapide pour trouver la documentation dont vous avez besoin.

---

## 🚀 Pour Démarrer RAPIDEMENT

**Vous voulez utiliser le système MAINTENANT sans attendre Reddit ?**

→ **[QUICKSTART_SANS_REDDIT.md](QUICKSTART_SANS_REDDIT.md)** (8 KB)
- ✅ Système déjà fonctionnel avec RSS
- ✅ Pas besoin de credentials Reddit
- ✅ Collecte de données immédiate
- ✅ Tests et vérifications

**Temps de lecture:** 5 minutes  
**Temps de mise en œuvre:** 10 minutes

---

## 📡 Pour Ajouter des Sources de Données

**Vous voulez ajouter plus de feeds RSS ou configurer Reddit ?**

→ **[MEMO_AJOUT_SOURCES.md](MEMO_AJOUT_SOURCES.md)** (8.7 KB)
- ✅ Configuration RSS (feeds recommandés)
- ✅ Configuration Reddit (quand disponible)
- ✅ Subreddits recommandés
- ✅ Monitoring et métriques
- ✅ Dépannage

**Temps de lecture:** 10 minutes  
**Temps de mise en œuvre:** 15-30 minutes

---

## 🔴 Pour Configurer Reddit (Problèmes d'API)

**Reddit vous bloque ou demande d'utiliser Devvit ?**

→ **[REDDIT_SETUP_REQUIRED.md](REDDIT_SETUP_REQUIRED.md)** (13 KB)
- ⚠️ Nouvelle politique Reddit 2024-2025
- ✅ Solutions si création d'app bloquée
- ✅ Alternative avec old.reddit.com
- ✅ Checklist complète étape par étape
- ✅ FAQ et dépannage

**Temps de lecture:** 15 minutes  
**Temps de mise en œuvre:** Variable (5 min à 48h selon compte)

---

## 🆕 Devvit vs API Classique

**Reddit vous demande d'utiliser Devvit ?**

→ **[DEVVIT_VS_API_CLASSIQUE.md](DEVVIT_VS_API_CLASSIQUE.md)** (6.4 KB)
- ❓ C'est quoi Devvit ?
- ✅ Pourquoi on n'en a PAS besoin
- ✅ API classique vs Devvit (comparaison)
- ✅ Notre cas d'usage expliqué
- ✅ Solution recommandée

**Temps de lecture:** 10 minutes  
**Réponse courte:** Utilisez l'API classique (old.reddit.com/prefs/apps)

---

## 📋 Documentation Complète

### Phase 1 - Implémentation Complète

→ **[PHASE1_COMPLETE.md](PHASE1_COMPLETE.md)** (17 KB)
- ✅ Architecture complète
- ✅ Services implémentés (RSS, Normalizer)
- ✅ Tests et validation
- ✅ Commandes de déploiement

### Phase 1.3 - Reddit Ingestor

→ **[PHASE1.3_IMPLEMENTATION.md](PHASE1.3_IMPLEMENTATION.md)** (14 KB)
- ✅ Implémentation Reddit ingestor
- ✅ Métriques Prometheus
- ✅ Dashboard Grafana
- ✅ Tests et validation

---

## 🛠️ Scripts Utiles

### Script de Vérification Rapide

```bash
cd /home/leox7/trading-platform
bash scripts/check_sources.sh
```

**Ce script vérifie:**
- Status de tous les services (RSS, Reddit, Normalizer)
- Topics Kafka
- Buckets MinIO
- Événements récents
- Configuration

### Test End-to-End

```bash
cd /home/leox7/trading-platform
python3 scripts/test_phase1_e2e.py
```

**Ce script teste:**
- Validation des schémas
- Infrastructure (topics + buckets)
- Santé des services
- Flux complet de données

---

## 🎯 Parcours Recommandé

### Si vous débutez:

1. **Lire:** [QUICKSTART_SANS_REDDIT.md](QUICKSTART_SANS_REDDIT.md)
   - Comprendre ce qui fonctionne déjà
   - Lancer les premiers tests

2. **Ajouter des feeds RSS:** [MEMO_AJOUT_SOURCES.md](MEMO_AJOUT_SOURCES.md)
   - Section RSS uniquement
   - Feeds recommandés pour trading

3. **Tester le système:**
   ```bash
   bash scripts/check_sources.sh
   python3 scripts/test_phase1_e2e.py
   ```

### Si vous voulez ajouter Reddit:

1. **Lire:** [DEVVIT_VS_API_CLASSIQUE.md](DEVVIT_VS_API_CLASSIQUE.md)
   - Comprendre la situation
   - Savoir quelle méthode utiliser

2. **Configurer:** [REDDIT_SETUP_REQUIRED.md](REDDIT_SETUP_REQUIRED.md)
   - Créer l'app sur old.reddit.com
   - Obtenir les credentials
   - Configurer .env

3. **Vérifier:** [MEMO_AJOUT_SOURCES.md](MEMO_AJOUT_SOURCES.md)
   - Section Reddit
   - Démarrage et monitoring

### Si Reddit vous bloque:

1. **Solutions:** [REDDIT_SETUP_REQUIRED.md](REDDIT_SETUP_REQUIRED.md)
   - Section "Problèmes de Création d'App"
   - 6 solutions proposées

2. **Alternative:** [QUICKSTART_SANS_REDDIT.md](QUICKSTART_SANS_REDDIT.md)
   - Utiliser RSS en attendant
   - Système déjà fonctionnel

---

## 📊 Tableaux de Référence Rapide

### Status Actuel du Système

| Service | Port | Status | Documentation |
|---------|------|--------|---------------|
| RSS Ingestor | 8001 | ✅ Actif | PHASE1_COMPLETE.md |
| Normalizer | 8002 | ✅ Actif | PHASE1_COMPLETE.md |
| Reddit Ingestor | 8003 | ⏳ Nécessite config | REDDIT_SETUP_REQUIRED.md |
| Kafka UI | 8080 | ✅ Actif | - |
| MinIO Console | 9001 | ✅ Actif | - |

### Sources de Données Disponibles

| Source | Type | Status | Configuration |
|--------|------|--------|---------------|
| RSS Feeds | Pull | ✅ Actif | .env: RSS_FEEDS |
| Reddit | Pull | ⏳ Config | .env: REDDIT_CLIENT_* |
| Twitter/X | Pull | ❌ Future | Phase 2 |
| Market Data | Pull | ❌ Future | Phase 1.4 |

### Fichiers de Configuration

| Fichier | Description |
|---------|-------------|
| `infra/.env` | Variables d'environnement (credentials, config) |
| `infra/docker-compose.yml` | Services et dépendances |
| `infra/observability/prometheus.yml` | Métriques Prometheus |
| `schemas/*.json` | Schémas de validation |

---

## 🆘 Aide Rapide

### Problème: "Reddit ne fonctionne pas"
→ [REDDIT_SETUP_REQUIRED.md](REDDIT_SETUP_REQUIRED.md) - Section Dépannage

### Problème: "Impossible de créer l'app Reddit"
→ [REDDIT_SETUP_REQUIRED.md](REDDIT_SETUP_REQUIRED.md) - Section "Problèmes de Création d'App"

### Question: "Devvit est-il obligatoire ?"
→ [DEVVIT_VS_API_CLASSIQUE.md](DEVVIT_VS_API_CLASSIQUE.md) - Non, utilisez l'API classique

### Question: "Comment démarrer sans Reddit ?"
→ [QUICKSTART_SANS_REDDIT.md](QUICKSTART_SANS_REDDIT.md) - Système déjà fonctionnel avec RSS

### Question: "Comment ajouter plus de feeds ?"
→ [MEMO_AJOUT_SOURCES.md](MEMO_AJOUT_SOURCES.md) - Section RSS

---

## 🔗 Liens Externes Utiles

### Reddit
- **Créer une app:** https://old.reddit.com/prefs/apps
- **API Docs:** https://www.reddit.com/dev/api/
- **PRAW Docs:** https://praw.readthedocs.io/
- **Responsible Builder Policy:** https://support.reddithelp.com/hc/en-us/articles/42728983564564

### Feeds RSS Trading
- **CNBC Markets:** https://www.cnbc.com/id/100003114/device/rss/rss.html
- **Reuters Business:** http://feeds.reuters.com/reuters/businessNews
- **MarketWatch:** http://feeds.marketwatch.com/marketwatch/topstories/

### Outils
- **Kafka UI:** http://localhost:8080
- **MinIO Console:** http://localhost:9001 (minioadmin/minioadmin123)

---

## 📝 Notes Importantes

1. **Le système fonctionne DÉJÀ sans Reddit** - RSS collecte des données en temps réel
2. **Reddit est optionnel** - Ajoute plus de volume mais pas obligatoire
3. **Devvit n'est PAS nécessaire** - API classique suffit pour notre cas
4. **old.reddit.com fonctionne mieux** - Pour créer les apps script
5. **Attendre 48h** - Si compte Reddit nouveau

---

## 🎓 Pour Aller Plus Loin

- **Observabilité:** Phase 1.2 (Prometheus + Grafana)
- **Enrichment:** Phase 1.4 (Company info, validation)
- **Feature Store:** Phase 1.5 (ML features)
- **Market Data:** Phase 1.6 (yfinance, Finnhub)

---

**🚀 Commencez par QUICKSTART_SANS_REDDIT.md pour utiliser le système immédiatement !**
