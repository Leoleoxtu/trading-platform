# ⚠️ Configuration Requise pour Reddit

## 🎯 Ce qui doit être fait pour activer Reddit

Pour que la collecte Reddit, Kafka et les métriques fonctionnent, vous devez:

### 1. ✅ Obtenir des Credentials Reddit - NOUVEAU: Devvit (2024-2025)

**⚠️ IMPORTANT: Reddit a changé son système d'apps**

Reddit utilise maintenant **Devvit** (Developer Platform) au lieu de l'ancien système d'apps.

---

## 🆕 Option A: Utiliser Devvit (Recommandé par Reddit 2024+)

**Devvit** est la nouvelle plateforme officielle Reddit pour les développeurs.

### Étapes avec Devvit:

**1. Installer Devvit CLI**
```bash
# Installation via npm
npm install -g devvit

# Ou via homebrew (Mac)
brew install devvit
```

**2. Se connecter à Reddit**
```bash
devvit login
# Cela ouvrira votre navigateur pour vous connecter avec votre compte Reddit
```

**3. Créer une nouvelle app Devvit**
```bash
# Créer un nouveau projet
devvit new trading-data-collector

# Choisir le template: "Empty project" ou "Custom"
```

**4. Obtenir les credentials**

Devvit utilise une approche différente - il génère automatiquement les credentials lors du déploiement.

**⚠️ PROBLÈME:** Devvit est conçu pour des apps **intégrées** à Reddit (widgets, bots), pas pour de la collecte de données externe.

---

## 🔧 Option B: Utiliser l'Ancienne API (Script App) - ENCORE POSSIBLE

**Pour la collecte de données externe (notre cas), l'ancienne méthode fonctionne toujours:**

**Prérequis:**
- Compte Reddit **vérifié par email**
- Compte actif depuis 24-48h minimum
- Accepter la [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)

**Étapes:**

1. **Vérifier votre compte:**
   - https://www.reddit.com/settings/profile
   - Email vérifié ✓

2. **Aller sur:** https://old.reddit.com/prefs/apps
   - ⚠️ Utiliser **old.reddit.com** (l'ancienne interface fonctionne mieux)

3. **Créer une app "script":**
   ```
   Name:         trading-platform-ingestor
   App type:     ⚫ script  ← IMPORTANT
   Description:  Data collection for trading analysis
   About URL:    (vide)
   Redirect URI: http://localhost:8080
   ```

4. **Récupérer les credentials:**
   - **Client ID**: Sous le nom de l'app (14 chars)
   - **Secret**: Ligne "secret:" (longue chaîne)

---

## 🤔 Quelle Option Choisir ?

### Pour notre cas d'usage (collecte de données):

**✅ Recommandation: Option B (Ancienne API)**

**Pourquoi ?**
- Notre code utilise PRAW (Python Reddit API Wrapper)
- Devvit est fait pour des apps Reddit intégrées (bots, widgets)
- L'ancienne API fonctionne toujours pour les scripts
- Pas besoin de redévelopper tout le code

**❌ Devvit n'est PAS adapté si:**
- Vous voulez collecter des données depuis l'extérieur
- Vous utilisez PRAW ou l'API REST classique
- Vous faites de l'analyse de données batch

**✅ Devvit EST adapté si:**
- Vous créez un bot Reddit interactif
- Vous voulez créer des widgets/posts personnalisés
- Vous développez une app intégrée à Reddit

---

## 🚀 Solution Rapide (Recommandée)

**Étape 1: Essayer l'ancienne interface**
```
1. Aller sur: https://old.reddit.com/prefs/apps
2. Si vous voyez "Create another app", c'est bon !
3. Suivre les étapes de l'Option B ci-dessus
```

**Étape 2: Si ça ne marche pas**
```
1. Vérifier que l'email est confirmé
2. Attendre 48h que le compte soit éligible
3. Réessayer sur old.reddit.com/prefs/apps
```

**Étape 3: Alternative temporaire**
```bash
# En attendant, utiliser seulement RSS
# Voir: QUICKSTART_SANS_REDDIT.md
```

---

## 📋 Résumé Simple

| Méthode | Pour Quoi ? | Notre Code Compatible ? |
|---------|-------------|-------------------------|
| **Devvit** | Apps intégrées Reddit | ❌ Non (nécessite réécriture) |
| **Script App (old.reddit.com)** | Collecte données externe | ✅ Oui (code actuel) |
| **RSS seulement** | Alternative sans Reddit | ✅ Oui (déjà fonctionnel) |

**→ Utiliser: old.reddit.com/prefs/apps (Option B)**

### 2. ✅ Configurer le fichier .env

```bash
cd infra
nano .env  # ou vim, code, gedit...
```

**Remplacer ces lignes:**
```bash
REDDIT_CLIENT_ID=your_reddit_client_id_here
REDDIT_CLIENT_SECRET=your_reddit_client_secret_here
```

**Par vos vraies valeurs:**
```bash
REDDIT_CLIENT_ID=xYz123AbCdEfGh
REDDIT_CLIENT_SECRET=Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv
```

**Optionnel - Personnaliser les subreddits:**
```bash
# Par défaut: wallstreetbets,stocks
REDDIT_SUBREDDITS=wallstreetbets,stocks,investing,CryptoCurrency
```

### 3. ✅ Démarrer le Service Reddit

```bash
cd infra

# Option 1: Démarrer seulement Reddit
docker compose up -d reddit-ingestor

# Option 2: Tout redémarrer avec Reddit inclus
docker compose --profile apps up -d
```

### 4. ✅ Vérifier que ça marche

**Vérification rapide (2 minutes):**

```bash
# 1. Vérifier que le service est démarré
docker compose ps reddit-ingestor

# 2. Vérifier le health check
curl http://localhost:8003/health

# Résultat attendu:
# {"status": "healthy", "service": "reddit-ingestor", "seen_items": 0, ...}

# 3. Voir les logs en temps réel
docker compose logs -f reddit-ingestor

# Vous devriez voir:
# - "Polling Reddit..."
# - "Items fetched: X"
# - "Raw event published"
```

**Vérification des données (5 minutes):**

```bash
# 1. ✅ Vérifier Kafka - Événements Reddit publiés
docker exec redpanda rpk topic consume raw.events.v1 -n 5

# 2. ✅ Vérifier MinIO - Fichiers bruts stockés
# Web UI: http://localhost:9001 (minioadmin/minioadmin123)
# Naviguer: Buckets → raw-events → source=reddit

# 3. ✅ Vérifier Métriques Prometheus
curl http://localhost:8003/metrics | grep reddit_ingestor_raw_events_published_total
```

---

## 📊 Ce que vous obtiendrez

Une fois configuré, vous aurez:

### ✅ Collecte Automatique Reddit
- Posts de r/wallstreetbets, r/stocks, etc.
- Poll toutes les 60 secondes
- Déduplication automatique (pas de doublons)

### ✅ Publication Kafka
- Topic: `raw.events.v1`
- Format standardisé: `raw_event.v1.json`
- Compatible avec le normalizer

### ✅ Métriques en Temps Réel
```
# Métriques disponibles:
reddit_ingestor_items_fetched_total          # Items collectés
reddit_ingestor_raw_events_published_total   # Événements publiés
reddit_ingestor_raw_events_failed_total      # Erreurs
reddit_ingestor_dedup_hits_total             # Doublons évités
reddit_ingestor_poll_duration_seconds        # Performance
```

### ✅ Stockage Immutable
- **MinIO**: Archive brute de tous les posts/comments
- **Format**: `source=reddit/dt=2025-12-30/{event_id}.json`
- **Retention**: Illimitée (configurable)

---

## � Problèmes de Création d'App Reddit

### ❌ "Read our full policies here" - Impossible de créer l'app

**Problème:** Reddit demande d'accepter la Responsible Builder Policy

**Solutions:**

**Solution 1: Vérifier l'email du compte**
```
1. Aller sur: https://www.reddit.com/settings/profile
2. Section "Email address"
3. Si pas vérifié, cliquer sur "Resend verification email"
4. Vérifier votre boîte mail et cliquer sur le lien
5. Réessayer de créer l'app
```

**Solution 2: Attendre que le compte soit éligible**
```
Reddit peut exiger:
- Compte actif depuis 24-48h minimum
- Email vérifié
- Pas de restrictions sur le compte

→ Créer le compte, vérifier l'email, attendre 48h, réessayer
```

**Solution 3: Utiliser un compte Reddit existant**
```
Si vous avez déjà un compte Reddit plus ancien:
- Se connecter avec ce compte
- Réessayer la création d'app
- Les comptes établis ont moins de restrictions
```

**Solution 4: Alternative - Utiliser seulement RSS (temporaire)**
```bash
# Le système fonctionne déjà sans Reddit!
# Vous collectez déjà des données via RSS:
cd infra
docker compose ps rss-ingestor

# Ajouter plus de feeds RSS en attendant:
# Dans infra/.env:
RSS_FEEDS=https://feeds.feedburner.com/TechCrunch/,https://hnrss.org/newest,https://www.cnbc.com/id/100003114/device/rss/rss.html,http://feeds.reuters.com/reuters/businessNews,http://feeds.marketwatch.com/marketwatch/topstories/
```

**Solution 5: Utiliser old.reddit.com**
```
L'ancienne interface fonctionne mieux pour créer des script apps:
1. Aller sur: https://old.reddit.com/prefs/apps
2. Cliquer sur "Create another app" (bouton en bas)
3. Remplir le formulaire (type: script)
4. Les credentials apparaissent immédiatement
```

**Solution 6: Contact Reddit Support**
```
Si le problème persiste après 48h:
- https://www.reddithelp.com/hc/en-us/requests/new
- Sujet: "Unable to create API application"
- Expliquer votre use case (data analysis, non-commercial)
```

---

## �🐛 Dépannage

### ❌ "Invalid credentials" dans les logs

**Problème:** Client ID ou Secret incorrect

**Solution:**
```bash
# Vérifier le .env
cat infra/.env | grep REDDIT_CLIENT

# Corriger et redémarrer
docker compose restart reddit-ingestor
```

### ❌ "Rate limit exceeded"

**Problème:** Trop de requêtes API

**Solution:** Augmenter le délai de poll
```bash
# Dans infra/.env
REDDIT_POLL_SECONDS=120  # Au lieu de 60
```

### ❌ Service ne démarre pas

```bash
# Vérifier les logs détaillés
docker compose logs --tail=100 reddit-ingestor

# Rebuild l'image si nécessaire
docker compose build --no-cache reddit-ingestor
docker compose up -d reddit-ingestor
```

### ❌ Pas de données dans Kafka

**Attendre 1-2 minutes** après le démarrage pour que le premier poll se fasse.

```bash
# Forcer un check immédiat
docker compose restart reddit-ingestor

# Vérifier qu'il poll
docker compose logs -f reddit-ingestor | grep -i "poll"
```

---

## 📈 Performance Attendue

**Après 5 minutes de fonctionnement:**
- 50-100 posts Reddit collectés
- 50-100 événements dans Kafka
- 50-100 fichiers JSON dans MinIO
- Normalizer traite automatiquement les événements

**Après 1 heure:**
- 500-1000 posts (selon nombre de subreddits)
- Extraction automatique de symboles (TSLA, AAPL, etc.)
- Détection de langue (en, fr, etc.)
- Score de qualité calculé

---

## ✅ Checklist Complète

Cochez au fur et à mesure:

- [ ] Compte Reddit créé
- [ ] App Reddit créée sur /prefs/apps
- [ ] Client ID copié
- [ ] Secret copié
- [ ] Fichier `infra/.env` édité avec les credentials
- [ ] Service redémarré: `docker compose up -d reddit-ingestor`
- [ ] Health check OK: `curl localhost:8003/health`
- [ ] Logs montrent "Items fetched": `docker compose logs reddit-ingestor`
- [ ] Événements dans Kafka: `rpk topic consume raw.events.v1`
- [ ] Fichiers dans MinIO: http://localhost:9001
- [ ] Métriques disponibles: `curl localhost:8003/metrics`

---

## 🎓 Utilisation Avancée

### Monitorer avec Grafana

```bash
# Démarrer Grafana
cd infra
docker compose --profile observability up -d

# Accéder à Grafana
open http://localhost:3001
# Login: admin / admin
# Dashboard: "Pipeline Health"
```

### Ajouter plus de subreddits

```bash
# Dans infra/.env
REDDIT_SUBREDDITS=wallstreetbets,stocks,investing,StockMarket,options,CryptoCurrency,Forex,algotrading,pennystocks,dividends

# Redémarrer
docker compose restart reddit-ingestor
```

### Collecter aussi les commentaires

```bash
# Dans infra/.env
REDDIT_MODE=both  # submissions + comments

# ⚠️ Attention: Volume de données beaucoup plus élevé!
```

---

## 📞 Besoin d'aide ?

**Script de diagnostic:**
```bash
cd /home/leox7/trading-platform
bash scripts/check_sources.sh
```

**Ce script vérifie:**
- ✅ Status de tous les services
- ✅ Topics Kafka
- ✅ Buckets MinIO
- ✅ Événements récents
- ✅ Configuration Reddit

---

## 💡 Note Importante

**Le système fonctionne déjà sans Reddit !**

Actuellement, vous collectez déjà des données via:
- ✅ **RSS Ingestor** - Actif (TechCrunch, etc.)
- ✅ **Normalizer** - Traite les événements RSS
- ✅ **Kafka** - Flux de données opérationnel
- ✅ **MinIO** - Stockage des données brutes

**Reddit est optionnel** et ajoute:
- Plus de volume de données
- Discussions communautaires
- Sentiments en temps réel
- Mais nécessite configuration API

**En attendant d'avoir les credentials Reddit**, vous pouvez:
1. Ajouter plus de feeds RSS (voir MEMO_AJOUT_SOURCES.md)
2. Utiliser les données RSS existantes
3. Tester tout le pipeline avec RSS uniquement
4. Créer le compte Reddit et attendre qu'il soit éligible

---

**🚀 Système fonctionnel avec RSS - Reddit optionnel mais recommandé !**
