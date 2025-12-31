# Résolution Problème : Dashboard Grafana "NO DATA"

## 📋 Contexte

Lors de la mise en place de l'observabilité pour le service **Triage Stage 1**, les dashboards Grafana affichaient systématiquement "NO DATA" malgré :
- Le service fonctionnant correctement
- Prometheus scrapant les métriques
- Les métriques visibles via `curl http://localhost:8006/metrics`

## 🔍 Problèmes Identifiés

### Problème #1 : Configuration de Provisioning Incorrecte

**Symptôme** :
```bash
curl -s "http://admin:admin@localhost:3001/api/search?type=dash-db"
# Retournait une liste vide ou dashboards manquants
```

**Cause** :
Le fichier `dashboards.yml` était placé à la racine du dossier `provisioning/` au lieu de `provisioning/dashboards/`.

**Structure incorrecte** :
```
infra/observability/grafana/
├── provisioning/
│   ├── dashboards.yml          ❌ INCORRECT
│   └── datasources/
│       └── datasource.yml
└── dashboards/
    └── triage_stage1.json
```

**Structure correcte** :
```
infra/observability/grafana/
├── provisioning/
│   ├── dashboards/
│   │   └── dashboards.yml      ✅ CORRECT
│   └── datasources/
│       └── datasource.yml
└── dashboards/
    └── triage_stage1.json
```

**Solution appliquée** :
```bash
mkdir -p /home/leox7/trading-platform/infra/observability/grafana/provisioning/dashboards
mv /home/leox7/trading-platform/infra/observability/grafana/provisioning/dashboards.yml \
   /home/leox7/trading-platform/infra/observability/grafana/provisioning/dashboards/
```

**Logs Grafana après correction** :
```
logger=provisioning.dashboard msg="starting to provision dashboards"
logger=provisioning.dashboard msg="finished to provision dashboards"
```

---

### Problème #2 : Codec Snappy Manquant

**Symptôme** :
```bash
docker compose logs triage-stage1
# ERROR: UnsupportedCodecError: Libraries for snappy compression codec not found
```

Le service crashait en boucle au démarrage, empêchant toute consommation d'événements Kafka.

**Cause** :
Redpanda utilise la compression Snappy par défaut, mais les bibliothèques nécessaires n'étaient pas installées dans le conteneur Docker.

**Solution appliquée** :

1. **Dockerfile** - Ajout de la dépendance système :
```dockerfile
# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libsnappy-dev \    # ✅ Ajouté
    curl \             # ✅ Ajouté pour healthcheck
    && rm -rf /var/lib/apt/lists/*
```

2. **requirements.txt** - Ajout du binding Python :
```txt
# Triage Stage 1 Service Requirements
aiokafka>=0.9.0
kafka-python-ng>=2.2.0
python-snappy>=0.7.0    # ✅ Ajouté
redis==5.0.1
pyyaml==6.0.1
loguru==0.7.2
aiohttp==3.9.1
prometheus-client==0.19.0
```

3. **Rebuild du conteneur** :
```bash
cd /home/leox7/trading-platform/infra
docker compose build triage-stage1 --no-cache
docker compose up -d triage-stage1
```

**Validation** :
```bash
docker compose logs triage-stage1 --tail 20
# ✅ INFO: Triage Stage 1 started
# ✅ INFO: Started consuming from events.normalized.v1
# ✅ DEBUG: Triaged event: score=75, bucket=FAST
```

---

### Problème #3 : UID de Datasource Incorrect

**Symptôme** :
Dashboard visible dans Grafana mais tous les panels affichent "NO DATA" même avec des événements traités.

**Cause** :
Le dashboard JSON utilisait un UID de datasource générique `"prometheus"` au lieu de l'UID réel généré par Grafana.

**Diagnostic** :
```bash
# Vérifier l'UID réel de la datasource
curl -s "http://admin:admin@localhost:3001/api/datasources" | \
  python3 -c "import sys,json; ds=[d for d in json.load(sys.stdin) if d['type']=='prometheus'][0]; print(f'Real UID: {ds[\"uid\"]}')"
# Real UID: PBFA97CFB590B2093

# Vérifier l'UID dans le dashboard
grep -o '"uid": "[^"]*"' triage_stage1.json | head -5
# "uid": "prometheus"    ❌ INCORRECT
```

**Solution appliquée** :
```bash
cd /home/leox7/trading-platform/infra/observability/grafana/dashboards

# Backup
cp triage_stage1.json triage_stage1.json.bak

# Remplacement global
sed -i 's/"uid": "prometheus"/"uid": "PBFA97CFB590B2093"/g' triage_stage1.json

# Vérification
grep -c 'PBFA97CFB590B2093' triage_stage1.json
# 35 occurrences remplacées ✅
```

**Redémarrage de Grafana** :
```bash
docker compose restart grafana
sleep 15
```

---

### Problème #4 : Variable d'Environnement Kafka Incorrecte

**Symptôme** :
```
ERROR: KafkaConnectionError: Unable to bootstrap from [('localhost', 9092)]
```

**Cause** :
Le code utilisait `os.getenv('KAFKA_BROKERS')` mais Docker Compose définissait `KAFKA_BOOTSTRAP_SERVERS`.

**Solution appliquée** :

**Fichier** : `services/preprocessing/triage_stage1/app.py`
```python
# Avant ❌
kafka_bootstrap_servers=os.getenv('KAFKA_BROKERS', 'localhost:9092'),

# Après ✅
kafka_bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
```

---

### Problème #5 : Conflit de Ports

**Symptôme** :
```
Error: Bind for 0.0.0.0:8006 failed: port is already allocated
```

**Cause** :
Le service `feature-store` utilisait déjà le port 8006 (`8006:8000`) et `triage-stage1` tentait aussi d'utiliser le même port (`8006:8006`).

**Solution appliquée** :

**Fichier** : `infra/docker-compose.yml`
```yaml
# feature-store - Changé le port externe
ports:
  - "8007:8000"    # ✅ Avant: 8006:8000

# triage-stage1 - Garde le port 8006
ports:
  - "8006:8006"    # ✅ OK
```

---

## ✅ Validation Finale

### 1. Service Healthy
```bash
curl -s http://localhost:8006/health
# {"status": "ok", "running": true, "timestamp": "2025-12-31T09:27:00Z"}
```

### 2. Métriques Exposées
```bash
curl -s http://localhost:8006/metrics | grep "triage_stage1_events" | head -5
# triage_stage1_events_consumed_total 38.0
# triage_stage1_events_routed_total{bucket="FAST"} 2.0
# triage_stage1_events_routed_total{bucket="STANDARD"} 33.0
# triage_stage1_events_routed_total{bucket="COLD"} 3.0
```

### 3. Prometheus Target UP
```bash
curl -s "http://localhost:9090/api/v1/targets" | \
  python3 -c "import sys,json; t=[x for x in json.load(sys.stdin)['data']['activeTargets'] if x['labels'].get('job')=='triage-stage1'][0]; print(f'Health: {t[\"health\"].upper()}')"
# Health: UP
```

### 4. Dashboards Visibles
```bash
curl -s "http://admin:admin@localhost:3001/api/search?type=dash-db" | \
  python3 -c "import sys,json; print(len(json.load(sys.stdin)), 'dashboards trouvés')"
# 5 dashboards trouvés
```

### 5. Données dans Grafana
```bash
# Test d'une requête PromQL via Grafana
curl -s "http://admin:admin@localhost:3001/api/datasources/proxy/uid/PBFA97CFB590B2093/api/v1/query?query=triage_stage1_events_consumed_total" | \
  python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(f'Value: {r[0][\"value\"][1]} events')"
# Value: 38 events
```

### 6. Dashboard Accessible
URL : http://localhost:3001/d/triage-stage1/triage-stage-1?orgId=1&refresh=10s&from=now-15m&to=now

Login : `admin` / `admin`

---

## 📊 Résumé des Changements

| Fichier | Modification | Raison |
|---------|--------------|--------|
| `infra/observability/grafana/provisioning/dashboards.yml` | Déplacé dans `provisioning/dashboards/` | Structure de provisioning Grafana |
| `services/preprocessing/triage_stage1/Dockerfile` | Ajout `libsnappy-dev` + `curl` | Support compression Kafka |
| `services/preprocessing/triage_stage1/requirements.txt` | Ajout `python-snappy>=0.7.0` | Binding Python pour Snappy |
| `services/preprocessing/triage_stage1/app.py` | `KAFKA_BROKERS` → `KAFKA_BOOTSTRAP_SERVERS` | Alignement avec docker-compose |
| `infra/docker-compose.yml` | Port feature-store : `8006` → `8007` | Résolution conflit de ports |
| `infra/observability/grafana/dashboards/triage_stage1.json` | UID datasource : `prometheus` → `PBFA97CFB590B2093` | UID réel de Prometheus |

---

## 🚀 Commandes de Test

### Générer un flux continu d'événements
```bash
./scripts/inject_test_events.sh
```

### Vérifier les métriques en temps réel
```bash
watch -n 2 'curl -s http://localhost:8006/metrics | grep consumed_total'
```

### Tester les requêtes PromQL
```bash
# Ingest rate
curl -s "http://localhost:9090/api/v1/query?query=rate(triage_stage1_events_consumed_total[5m])"

# Distribution par bucket
curl -s "http://localhost:9090/api/v1/query?query=sum%20by(bucket)%20(triage_stage1_events_routed_total)"
```

---

## 📚 Leçons Apprises

1. **Structure de provisioning Grafana** : Les fichiers de configuration doivent être dans des sous-dossiers spécifiques (`dashboards/`, `datasources/`, `notifiers/`)

2. **Dépendances Kafka** : Toujours vérifier les codecs de compression supportés par les clients Kafka

3. **UID Datasource** : Les UIDs de datasource sont générés dynamiquement par Grafana et doivent être référencés correctement dans les dashboards

4. **Variables d'environnement** : Maintenir la cohérence entre les noms de variables dans le code et docker-compose

5. **Allocation de ports** : Documenter clairement les ports utilisés par chaque service pour éviter les conflits

---

## 🔗 Références

- Documentation Grafana Provisioning : https://grafana.com/docs/grafana/latest/administration/provisioning/
- AIOKafka Compression : https://aiokafka.readthedocs.io/en/stable/
- Prometheus Query API : https://prometheus.io/docs/prometheus/latest/querying/api/
- Guide d'opérations : [docs/90_operations.md](90_operations.md)
- Validation complète : [docs/TRIAGE_STAGE1_OBSERVABILITY_VALIDATION.md](TRIAGE_STAGE1_OBSERVABILITY_VALIDATION.md)
