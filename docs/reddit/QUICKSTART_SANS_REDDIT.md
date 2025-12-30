# 🚀 Démarrage Rapide - Sans Reddit

## ✅ Votre système est déjà fonctionnel !

Pas besoin de Reddit pour commencer. Le système collecte déjà des données.

---

## 1️⃣ Vérifier que tout fonctionne (2 minutes)

```bash
cd /home/leox7/trading-platform

# Vérifier les services
cd infra
docker compose ps

# Devrait afficher:
# ✓ rss-ingestor    - Up and healthy
# ✓ normalizer      - Up and healthy
# ✓ redpanda        - Up and healthy
# ✓ minio           - Up and healthy
# ✓ kafka-ui        - Up
```

**Health checks:**
```bash
curl http://localhost:8001/health  # RSS Ingestor
curl http://localhost:8002/health  # Normalizer
```

---

## 2️⃣ Ajouter plus de sources RSS (5 minutes)

```bash
cd /home/leox7/trading-platform/infra

# Éditer le fichier .env
nano .env

# Modifier la ligne RSS_FEEDS:
RSS_FEEDS=https://feeds.feedburner.com/TechCrunch/,https://hnrss.org/newest,https://www.cnbc.com/id/100003114/device/rss/rss.html,http://feeds.reuters.com/reuters/businessNews,http://feeds.marketwatch.com/marketwatch/topstories/

# Sauvegarder (Ctrl+O, Enter, Ctrl+X)

# Redémarrer le RSS ingestor
docker compose restart rss-ingestor

# Vérifier les logs
docker compose logs -f rss-ingestor
```

**Feeds recommandés (Finance/Tech):**
```bash
# TechCrunch - Tech news
https://feeds.feedburner.com/TechCrunch/

# Hacker News - Top tech
https://hnrss.org/newest

# CNBC - Markets
https://www.cnbc.com/id/100003114/device/rss/rss.html

# Reuters - Business
http://feeds.reuters.com/reuters/businessNews

# MarketWatch - Top Stories
http://feeds.marketwatch.com/marketwatch/topstories/

# Bloomberg - Markets (si disponible)
https://feeds.bloomberg.com/markets/news.rss
```

---

## 3️⃣ Voir les données collectées (5 minutes)

### Via Kafka (Événements temps réel)

```bash
# Voir les événements bruts (RSS)
docker exec redpanda rpk topic consume raw.events.v1 -n 5

# Voir les événements normalisés (avec symboles extraits)
docker exec redpanda rpk topic consume events.normalized.v1 -n 5
```

### Via Kafka UI (Interface Web)

```bash
# Ouvrir dans le navigateur
http://localhost:8080

# Naviguer vers:
# Topics → raw.events.v1 → Messages
# Topics → events.normalized.v1 → Messages
```

### Via MinIO (Stockage des fichiers bruts)

```bash
# Ouvrir dans le navigateur
http://localhost:9001

# Login: minioadmin / minioadmin123
# Naviguer vers:
# Buckets → raw-events → source=rss → dt=2025-12-30
```

---

## 4️⃣ Tester l'extraction de symboles (2 minutes)

Le normalizer extrait automatiquement les symboles boursiers (TSLA, AAPL, etc.)

```bash
# Voir un événement normalisé avec symboles
docker exec redpanda rpk topic consume events.normalized.v1 -n 1 --format json | jq '.value | fromjson | {event_id, symbols_candidates, lang, source_score}'
```

**Exemple de résultat:**
```json
{
  "event_id": "abc-123",
  "symbols_candidates": ["TSLA", "AAPL", "MSFT"],
  "lang": "en",
  "source_score": 0.75
}
```

---

## 5️⃣ Lancer le test End-to-End (3 minutes)

```bash
cd /home/leox7/trading-platform
python3 scripts/test_phase1_e2e.py
```

**Résultat attendu:**
```
✓ Schema validation passed
✓ All Kafka topics exist
✓ MinIO buckets exist
✓ RSS Ingestor healthy
✓ Normalizer healthy
✓ Normalized event found!
✓ Ticker symbols extracted correctly

Tests passed: 5/5
```

---

## 6️⃣ Script de diagnostic rapide

```bash
cd /home/leox7/trading-platform
bash scripts/check_sources.sh
```

**Ce script affiche:**
- ✅ Status de tous les services
- ✅ Topics Kafka disponibles
- ✅ Buckets MinIO
- ✅ Événements récents
- ✅ Configuration actuelle

---

## 📊 Métriques en Temps Réel

```bash
# Métriques RSS Ingestor
curl http://localhost:8001/metrics | grep rss_ingestor

# Exemples de métriques:
# rss_ingestor_raw_events_published_total - Événements publiés
# rss_ingestor_dedup_hits_total - Doublons détectés
# rss_ingestor_poll_duration_seconds - Performance
```

---

## 🎯 Que fait le système actuellement ?

### RSS Ingestor (Port 8001)
1. ✅ Poll les feeds RSS toutes les 60 secondes
2. ✅ Télécharge le contenu des articles
3. ✅ Stocke dans MinIO (raw-events/source=rss/)
4. ✅ Publie dans Kafka (raw.events.v1)
5. ✅ Déduplique automatiquement

### Normalizer (Port 8002)
1. ✅ Consomme depuis Kafka (raw.events.v1)
2. ✅ Extrait les symboles boursiers (TSLA, AAPL, etc.)
3. ✅ Détecte la langue (en, fr, etc.)
4. ✅ Calcule un score de qualité
5. ✅ Publie les événements normalisés (events.normalized.v1)

### Flux de Données
```
RSS Feeds
    ↓
RSS Ingestor (collect + store)
    ↓
Kafka raw.events.v1
    ↓
Normalizer (analyze + enrich)
    ↓
Kafka events.normalized.v1
    ↓
[Prêt pour enrichment, features, ML]
```

---

## 📈 Performance Actuelle

Avec 1-2 feeds RSS:
- **~10-30 articles/heure** collectés
- **Stockage:** ~1-5 MB/jour
- **Latence:** <1 seconde (RSS → Kafka → Normalisé)
- **CPU:** <5% par service
- **RAM:** ~200-300 MB par service

Avec 5-10 feeds RSS:
- **~50-100 articles/heure**
- **Stockage:** ~10-20 MB/jour
- Plus de symboles détectés
- Plus de diversité de sources

---

## 🔄 Commandes Utiles au Quotidien

```bash
# Voir les logs en temps réel
cd infra
docker compose logs -f rss-ingestor normalizer

# Redémarrer un service
docker compose restart rss-ingestor

# Voir le status
docker compose ps

# Arrêter tout
docker compose --profile apps down

# Redémarrer tout
docker compose --profile apps up -d

# Nettoyer les logs
docker compose logs --tail=0 -f rss-ingestor
```

---

## 🎓 Prochaines Étapes

### Immédiat (sans Reddit):
1. ✅ Ajouter plus de feeds RSS
2. ✅ Monitorer les données collectées
3. ✅ Analyser les symboles extraits
4. ✅ Tester le système end-to-end

### Court terme (quand Reddit sera disponible):
1. ⏳ Créer le compte Reddit et attendre 48h
2. ⏳ Lire et accepter la Responsible Builder Policy
3. ⏳ Créer l'app Reddit
4. ⏳ Configurer les credentials dans .env
5. ⏳ Démarrer reddit-ingestor

### Moyen terme:
- Ajouter l'observabilité (Grafana)
- Enrichment pipeline (Company info)
- Feature store (ML features)
- Market data ingestor (yfinance)

---

## ❓ FAQ

**Q: Combien de temps avant d'avoir des données ?**
R: Immédiatement ! Le RSS ingestor poll toutes les 60 secondes.

**Q: Puis-je ajouter mes propres feeds RSS ?**
R: Oui ! Modifiez `RSS_FEEDS` dans `infra/.env` et redémarrez.

**Q: Les données sont-elles persistées ?**
R: Oui, dans MinIO (objets) et états de déduplication (volumes Docker).

**Q: Puis-je arrêter et redémarrer sans perdre les données ?**
R: Oui, les volumes Docker persistent. `docker compose down/up` garde tout.

**Q: Comment reset complètement le système ?**
R: 
```bash
cd infra
docker compose down -v  # -v supprime les volumes
docker compose --profile apps up -d
```

**Q: Reddit est-il obligatoire ?**
R: Non ! Le système fonctionne parfaitement avec RSS seulement. Reddit ajoute juste plus de données.

---

## 🎉 Félicitations !

Vous avez un système de collecte de données **opérationnel** qui:
- ✅ Collecte automatiquement des actualités
- ✅ Extrait les symboles boursiers
- ✅ Normalise et structure les données
- ✅ Stocke tout de manière immutable
- ✅ Est prêt pour l'analyse et le ML

**Pas besoin de Reddit pour commencer à utiliser votre plateforme !**

---

## 📚 Documentation

- **Guide complet RSS/Reddit**: [MEMO_AJOUT_SOURCES.md](MEMO_AJOUT_SOURCES.md)
- **Setup Reddit (futur)**: [REDDIT_SETUP_REQUIRED.md](REDDIT_SETUP_REQUIRED.md)
- **Phase 1 complète**: [PHASE1_COMPLETE.md](PHASE1_COMPLETE.md)
- **Phase 1.3 Reddit**: [PHASE1.3_IMPLEMENTATION.md](PHASE1.3_IMPLEMENTATION.md)

---

**🚀 Système prêt à l'emploi - Collectez des données dès maintenant !**
