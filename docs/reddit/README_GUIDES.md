# 📖 Guides Disponibles - Aide Rapide

## 🚨 Vous Avez un Problème avec Reddit / Devvit ?

**Solution rapide:** Lisez [DEVVIT_VS_API_CLASSIQUE.md](DEVVIT_VS_API_CLASSIQUE.md)

**TL;DR:**
- ❌ Devvit n'est PAS nécessaire pour notre cas
- ✅ Utilisez l'API classique: https://old.reddit.com/prefs/apps
- ✅ Le système fonctionne DÉJÀ sans Reddit (avec RSS)

---

## 📚 Liste des Guides

| Fichier | Quand l'utiliser | Temps |
|---------|------------------|-------|
| **[INDEX_GUIDES.md](INDEX_GUIDES.md)** | Index complet de tous les guides | 2 min |
| **[QUICKSTART_SANS_REDDIT.md](QUICKSTART_SANS_REDDIT.md)** | Démarrer MAINTENANT sans Reddit | 10 min |
| **[DEVVIT_VS_API_CLASSIQUE.md](DEVVIT_VS_API_CLASSIQUE.md)** | Reddit demande Devvit ? | 10 min |
| **[REDDIT_SETUP_REQUIRED.md](REDDIT_SETUP_REQUIRED.md)** | Configurer Reddit (avec solutions) | 15 min |
| **[MEMO_AJOUT_SOURCES.md](MEMO_AJOUT_SOURCES.md)** | Ajouter RSS ou Reddit | 15 min |

---

## ⚡ Démarrage Ultra-Rapide (30 secondes)

```bash
cd /home/leox7/trading-platform

# Vérifier que tout fonctionne
bash scripts/check_sources.sh

# Tester end-to-end
python3 scripts/test_phase1_e2e.py

# Voir les données collectées
docker exec redpanda rpk topic consume events.normalized.v1 -n 5
```

---

## 💡 Ce qu'il Faut Savoir

1. ✅ **Le système collecte DÉJÀ des données** (via RSS)
2. ✅ **Reddit est OPTIONNEL** (ajoute juste plus de volume)
3. ✅ **Devvit n'est PAS nécessaire** (API classique suffit)
4. ✅ **old.reddit.com/prefs/apps** fonctionne pour créer l'app

---

**➡️ Commencez par [INDEX_GUIDES.md](INDEX_GUIDES.md) pour trouver le bon guide**
