# 📰 Mémo - Ajout de Sources d'Actualités

Guide rapide pour configurer les sources de données (RSS, Reddit, etc.)

## 🔧 Configuration Initiale

### 1. Créer le fichier de configuration

```bash
cd infra
cp .env.example .env
```

### 2. Éditer le fichier `.env`

```bash
nano .env  # ou vim, code, etc.
```

---

## 📡 Sources Disponibles

### RSS Feeds (✅ Actif par défaut)

**Aucune configuration requise** - Fonctionne immédiatement

**Ajouter/Modifier des feeds:**
```bash
# Dans infra/.env
RSS_FEEDS=https://feeds.feedburner.com/TechCrunch/,https://hnrss.org/newest,https://www.cnbc.com/id/100003114/device/rss/rss.html
RSS_POLL_SECONDS=60
```

**Feeds recommandés pour le trading:**
- **TechCrunch**: `https://feeds.feedburner.com/TechCrunch/`
- **Hacker News**: `https://hnrss.org/newest`
- **CNBC Markets**: `https://www.cnbc.com/id/100003114/device/rss/rss.html`
- **Bloomberg**: `https://feeds.bloomberg.com/markets/news.rss`
- **Reuters Business**: `http://feeds.reuters.com/reuters/businessNews`
- **MarketWatch**: `http://feeds.marketwatch.com/marketwatch/topstories/`

---

### Reddit (⚠️ Nécessite configuration)

#### Étape 1: Obtenir les Credentials

1. **Aller sur**: https://www.reddit.com/prefs/apps
2. **Se connecter** avec votre compte Reddit
3. **Cliquer** sur "Create App" ou "Create Another App"
4. **Remplir le formulaire:**
   - **Name**: `trading-platform-ingestor` (ou autre nom)
   - **App type**: Sélectionner **"script"**
   - **Description**: `Data collection for trading platform` (optionnel)
   - **About URL**: Laisser vide
   - **Redirect URI**: `http://localhost:8080` (requis mais non utilisé)
5. **Cliquer** sur "Create app"
6. **Récupérer les informations:**
   - **Client ID**: Sous le nom de l'app (chaîne courte)
   - **Secret**: Visible après création (chaîne longue)

#### Étape 2: Configurer dans `.env`

```bash
# Dans infra/.env
REDDIT_CLIENT_ID=VoTrE_cLiEnT_iD_IcI
REDDIT_CLIENT_SECRET=VoTrE_sEcReT_IcI_LoNg
REDDIT_USER_AGENT=trading-platform-ingestor/1.0
```

#### Étape 3: Choisir les Subreddits

```bash
# Subreddits recommandés pour le trading
REDDIT_SUBREDDITS=wallstreetbets,stocks,investing,StockMarket,options,CryptoCurrency

# Mode de collecte
REDDIT_MODE=submissions  # submissions | comments | both

# Fréquence
REDDIT_POLL_SECONDS=60

# Limite par poll
REDDIT_LIMIT_PER_POLL=50
```

**Subreddits populaires trading/finance:**
- `wallstreetbets` - Discussions populaires sur les actions
- `stocks` - Actualités et analyses d'actions
- `investing` - Stratégies d'investissement
- `StockMarket` - Actualités du marché
- `options` - Trading d'options
- `CryptoCurrency` - Crypto-monnaies
- `Forex` - Marché des devises
- `algotrading` - Trading algorithmique

---

## 🚀 Démarrage des Services

### Démarrer tout (Infrastructure + Apps)

```bash
cd infra
docker compose --profile apps up -d
```

### Démarrer uniquement Reddit

```bash
cd infra
docker compose up -d reddit-ingestor
```

### Vérifier l'état

```bash
docker compose ps
```

---

## ✅ Vérification que ça fonctionne

### 1. Health Check

```bash
# RSS Ingestor
curl http://localhost:8001/health | jq .

# Reddit Ingestor
curl http://localhost:8003/health | jq .

# Normalizer
curl http://localhost:8002/health | jq .
```

**Résultat attendu:**
```json
{
  "status": "healthy",
  "service": "reddit-ingestor",
  "seen_items": 0,
  "stats": {
    "items_fetched": 0,
    "events_published": 0,
    "dedup_hits": 0
  }
}
```

### 2. Logs en Temps Réel

```bash
# Reddit
docker compose logs -f reddit-ingestor

# RSS
docker compose logs -f rss-ingestor

# Tous
docker compose logs -f rss-ingestor reddit-ingestor normalizer
```

**Ce que vous devriez voir:**
```
reddit-ingestor | {"message": "Polling Reddit...", "subreddits": ["wallstreetbets", "stocks"]}
reddit-ingestor | {"message": "Items fetched", "count": 25, "kind": "submission"}
reddit-ingestor | {"message": "Raw event published", "event_id": "..."}
```

### 3. Données dans Kafka

```bash
# Voir tous les événements bruts
docker exec redpanda rpk topic consume raw.events.v1 -n 5

# Filtrer seulement Reddit
docker exec redpanda rpk topic consume raw.events.v1 --filter 'source_type=="reddit"' -n 5

# Voir les événements normalisés
docker exec redpanda rpk topic consume events.normalized.v1 -n 5
```

### 4. Données dans MinIO

```bash
# Via Web UI
open http://localhost:9001
# Login: minioadmin / minioadmin123
# Naviguer vers: Buckets → raw-events → source=reddit/

# Via CLI
docker run --rm --network infra_trading-platform --entrypoint /bin/sh minio/mc -c \
  'mc alias set local http://minio:9000 minioadmin minioadmin123 && \
   mc ls --recursive local/raw-events/source=reddit/ | head -10'
```

### 5. Métriques Prometheus

```bash
# Métriques Reddit
curl http://localhost:8003/metrics | grep reddit_ingestor

# Métriques RSS
curl http://localhost:8001/metrics | grep rss_ingestor
```

---

## 🎯 Checklist de Vérification

Après configuration, vérifier que:

- [ ] Le fichier `infra/.env` existe et contient les credentials
- [ ] Les services démarrent sans erreur: `docker compose ps`
- [ ] Health endpoints répondent "healthy"
- [ ] Les logs montrent des items fetched
- [ ] Des événements apparaissent dans Kafka topic `raw.events.v1`
- [ ] Des fichiers JSON apparaissent dans MinIO bucket `raw-events/`
- [ ] Les métriques augmentent: `curl localhost:8003/metrics`
- [ ] Le normalizer traite les événements (topic `events.normalized.v1`)

---

## 🐛 Dépannage

### Reddit ne démarre pas

```bash
# Vérifier les logs
docker compose logs reddit-ingestor

# Erreurs communes:
# - "Invalid credentials" → Vérifier REDDIT_CLIENT_ID et REDDIT_CLIENT_SECRET
# - "Rate limit exceeded" → Augmenter REDDIT_POLL_SECONDS (ex: 120)
# - "Subreddit not found" → Vérifier l'orthographe des subreddits
```

### Pas de données dans Kafka

```bash
# Vérifier que les topics existent
docker exec redpanda rpk topic list

# Vérifier la connectivité Kafka
docker exec redpanda rpk cluster info

# Redémarrer le service
docker compose restart reddit-ingestor
```

### Trop de doublons (dedup_hits élevé)

**C'est normal !** Le système déduplique automatiquement. Après le premier poll, vous verrez surtout des doublons. Attendez quelques heures pour voir de nouveaux posts.

### Erreur "No module named praw"

L'image Docker n'est pas à jour:
```bash
docker compose build --no-cache reddit-ingestor
docker compose up -d reddit-ingestor
```

---

## 📊 Monitoring avec Grafana (Optionnel)

### Démarrer Grafana

```bash
cd infra
docker compose --profile observability up -d
```

### Accéder à Grafana

- **URL**: http://localhost:3001
- **Login**: admin / admin
- **Dashboard**: "Pipeline Health"

**Vous verrez:**
- Throughput par source (RSS, Reddit)
- Taux d'erreurs
- Hits de déduplication
- Latences MinIO/Kafka

---

## 🎓 Exemples de Configuration

### Configuration Légère (peu d'API calls)

```bash
# Dans .env
REDDIT_SUBREDDITS=wallstreetbets,stocks
REDDIT_MODE=submissions
REDDIT_POLL_SECONDS=120
REDDIT_LIMIT_PER_POLL=25
```

### Configuration Intensive (max de données)

```bash
# Dans .env
REDDIT_SUBREDDITS=wallstreetbets,stocks,investing,StockMarket,options,CryptoCurrency,Forex
REDDIT_MODE=both
REDDIT_POLL_SECONDS=60
REDDIT_LIMIT_PER_POLL=100
```

### RSS Feeds Trading Complet

```bash
RSS_FEEDS=https://feeds.feedburner.com/TechCrunch/,https://hnrss.org/newest,https://www.cnbc.com/id/100003114/device/rss/rss.html,http://feeds.reuters.com/reuters/businessNews,http://feeds.marketwatch.com/marketwatch/topstories/,https://feeds.bloomberg.com/markets/news.rss
RSS_POLL_SECONDS=60
```

---

## 📝 Notes Importantes

1. **Reddit Rate Limits**: Maximum ~60 requêtes/minute. Avec 6 subreddits et 60s de poll, vous êtes safe.

2. **Credentials Sécurité**: Ne **jamais** commit le fichier `.env` dans Git (déjà dans `.gitignore`).

3. **Déduplication**: Les items sont mémorisés **indéfiniment**. Pour reset:
   ```bash
   docker compose down reddit-ingestor
   docker volume rm infra_reddit_ingestor_data
   docker compose up -d reddit-ingestor
   ```

4. **Coûts**: Reddit API est **gratuite** pour usage non-commercial.

5. **Legal**: Respecter les Terms of Service de Reddit et des flux RSS.

---

## 🚀 Commandes Rapides

```bash
# Tout démarrer
cd infra && docker compose --profile apps up -d

# Voir tous les logs
docker compose logs -f

# Status rapide
docker compose ps && curl -s localhost:8001/health | jq . && curl -s localhost:8003/health | jq .

# Consommer les derniers événements
docker exec redpanda rpk topic consume raw.events.v1 -n 10

# Arrêter tout
docker compose --profile apps down
```

---

**🎉 C'est tout ! Votre plateforme collecte maintenant des données en temps réel depuis RSS et Reddit.**
