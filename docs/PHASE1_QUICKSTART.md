# 🚀 Phase 1 - Infrastructure Validation Quick Start

## Ce qui a été ajouté

### ✅ Nouveaux fichiers créés

#### Scripts de validation (`/scripts/`)
- `validate_kafka.sh` - Teste Kafka/Redpanda (topics, producer, consumer)
- `validate_minio.sh` - Teste MinIO (buckets, upload, download)
- `validate_redis.sh` - Teste Redis (SET/GET, maxmemory-policy)
- `validate_postgres.sh` - Teste PostgreSQL/TimescaleDB (tables, hypertables)
- `validate_phase1_complete.sh` - Master script qui lance tous les tests

#### Base de données (`/infra/timescale/`)
- `trading_system_init.sql` - 6 tables métier ajoutées :
  - `newscards` - Événements news structurés
  - `scenarios` - Scénarios de trading IA
  - `positions` - Positions ouvertes/fermées
  - `orders` - Ordres broker (IBKR)
  - `decision_logs` - Logs de décisions IA
  - `agent_performance` - Performance des agents IA

#### Docker Compose
- Service **Redis** ajouté avec maxmemory-policy `allkeys-lru`
- Continuous aggregates **VWAP 1h** et **VWAP 1d** dans TimescaleDB

#### Documentation
- `docs/phase du projet réalisé/PHASE1_INFRASTRUCTURE_AUDIT.md` - Audit complet Phase 1

---

## 🔧 Appliquer les changements

### 1. Recréer le volume TimescaleDB (pour les nouvelles tables)

```bash
cd /home/leox7/trading-platform/infra

# Arrêter les services
docker compose down

# Supprimer le volume TimescaleDB (⚠️ efface les données existantes)
docker volume rm infra_timescale_data

# Redémarrer avec les profils infra + data
docker compose --profile infra --profile data up -d

# Attendre 30 secondes pour l'initialisation
sleep 30
```

### 2. Vérifier les services

```bash
# Voir les services actifs
docker compose ps

# Vérifier les logs TimescaleDB (doit afficher "initialization complete")
docker compose logs timescaledb | tail -20
```

### 3. Lancer la validation complète

```bash
cd /home/leox7/trading-platform

# Lancer tous les tests
bash scripts/validate_phase1_complete.sh
```

**Résultat attendu** :
```
==========================================
  VALIDATION SUMMARY
==========================================

Total tests:  6
Passed:       6
Failed:       0

✓✓✓ ALL TESTS PASSED ✓✓✓
Phase 1 infrastructure is ready!
```

---

## 📊 Vérifier les nouvelles tables

### Via psql

```bash
docker compose exec -e PGPASSWORD=market_secret_change_me timescaledb psql -U market -d market

# Lister toutes les tables
\dt

# Vérifier les hypertables
SELECT * FROM timescaledb_information.hypertables;

# Vérifier les continuous aggregates
SELECT view_name, refresh_interval FROM timescaledb_information.continuous_aggregates;

# Quitter
\q
```

### Tables attendues

```
                List of relations
 Schema |         Name          | Type  | Owner  
--------+-----------------------+-------+--------
 public | agent_performance     | table | market
 public | decision_logs         | table | market
 public | feature_quality_log   | table | market
 public | feature_vectors       | table | market
 public | newscards             | table | market
 public | ohlcv                 | table | market
 public | ohlcv_quality_log     | table | market
 public | orders                | table | market
 public | positions             | table | market
 public | scenarios             | table | market
(10 rows)
```

---

## 🧪 Tester Redis

```bash
# Test basique
docker compose exec redis redis-cli ping
# Réponse : PONG

# Vérifier la policy
docker compose exec redis redis-cli CONFIG GET maxmemory-policy
# Réponse : allkeys-lru

# Test SET/GET
docker compose exec redis redis-cli SET test:key "Hello Redis"
docker compose exec redis redis-cli GET test:key
# Réponse : Hello Redis

# Script complet
bash scripts/validate_redis.sh
```

---

## 📈 Vérifier les VWAP aggregates

```bash
# Connexion à TimescaleDB
docker compose exec -e PGPASSWORD=market_secret_change_me timescaledb psql -U market -d market

# Voir les continuous aggregates
SELECT view_name, materialization_hypertable_name 
FROM timescaledb_information.continuous_aggregates;

# Exemple : Insérer des données OHLCV
INSERT INTO ohlcv (instrument_id, timeframe, ts, open, high, low, close, volume, source)
VALUES 
  ('AAPL', '1m', NOW(), 150.0, 152.0, 149.5, 151.5, 10000, 'test'),
  ('AAPL', '1m', NOW() - INTERVAL '1 minute', 149.0, 150.5, 148.0, 150.0, 8000, 'test');

# Rafraîchir les aggregates (automatique, mais forçable)
CALL refresh_continuous_aggregate('ohlcv_vwap_1h', NOW() - INTERVAL '2 hours', NOW());

# Voir les VWAP calculés
SELECT * FROM ohlcv_vwap_1h WHERE instrument_id = 'AAPL' ORDER BY bucket DESC LIMIT 5;
```

---

## 🎯 Prochaines étapes

Une fois que tous les tests passent :

1. **Commit les changements**
   ```bash
   git add .
   git commit -m "Phase 1: Add Redis, trading tables, VWAP aggregates, validation scripts"
   git push
   ```

2. **Lire l'audit complet**
   - Ouvrir : `docs/phase du projet réalisé/PHASE1_INFRASTRUCTURE_AUDIT.md`
   - Statut : 95% complété
   - Recommandation : **Prêt pour Phase 2**

3. **Optionnel : Ajouter lifecycle policy MinIO**
   ```bash
   docker compose exec minio mc ilm add local/raw-events --expiry-days 90
   docker compose exec minio mc ilm add local/pipeline-artifacts --expiry-days 30
   ```

---

## 🆘 Troubleshooting

### Erreur : "volume is in use"

```bash
# Arrêter TOUS les conteneurs
docker compose down

# Forcer la suppression du volume
docker volume rm -f infra_timescale_data

# Redémarrer
docker compose --profile infra --profile data up -d
```

### Erreur : "script not executable"

```bash
chmod +x scripts/validate_*.sh
```

### Redis ne démarre pas

```bash
# Vérifier les logs
docker compose logs redis

# Redémarrer Redis seul
docker compose restart redis
```

### Tests échouent

```bash
# Voir les logs détaillés
cat /tmp/kafka_validation.log
cat /tmp/minio_validation.log
cat /tmp/redis_validation.log
cat /tmp/postgres_validation.log
```

---

## 📚 Documentation complète

- **Audit Phase 1** : [PHASE1_INFRASTRUCTURE_AUDIT.md](docs/phase du projet réalisé/PHASE1_INFRASTRUCTURE_AUDIT.md)
- **Guide Grafana/Prometheus** : [GUIDE_GRAFANA_PROMETHEUS.md](docs/GUIDE_GRAFANA_PROMETHEUS.md)
- **Tâches Phase 1** : [tache_P1.md](tache_P1.md)
- **Architecture système** : [complete_system_doc (1).md](complete_system_doc (1).md)

---

**Bon déploiement ! 🚀**
