# 🆕 Reddit Devvit vs API Classique - Guide

## ❓ Qu'est-ce que Devvit ?

**Devvit** est la nouvelle plateforme de développement de Reddit lancée en 2024.

### Devvit c'est pour:
- ✅ Créer des **bots** interactifs Reddit
- ✅ Créer des **widgets** personnalisés dans les posts
- ✅ Créer des **apps** intégrées à Reddit
- ✅ Automatisation **dans** Reddit (modération, réponses, etc.)

### Devvit ce N'EST PAS pour:
- ❌ Collecter des données **en dehors** de Reddit
- ❌ Analyse batch de données
- ❌ Scripts Python externes (comme PRAW)
- ❌ Intégration avec systèmes externes (Kafka, MinIO, etc.)

---

## 🎯 Notre Cas d'Usage

**Ce que nous faisons:**
```
Reddit → Collecte externe → Kafka → MinIO → Analyse
```

**Ce dont nous avons besoin:**
- ❌ Pas d'app intégrée Reddit
- ❌ Pas de bot interactif
- ✅ **Lecture seule** des subreddits
- ✅ Collecte de données externe
- ✅ Traitement batch

**→ Devvit n'est PAS adapté à notre cas**

---

## ✅ Solution Recommandée: API Reddit Classique

### Pourquoi utiliser l'API classique ?

1. **Compatible avec notre code actuel**
   - Utilise PRAW (Python Reddit API Wrapper)
   - Pas besoin de tout réécrire
   - Fonctionne en dehors de Reddit

2. **Plus simple pour la collecte de données**
   - Accès en lecture aux subreddits
   - Pas besoin de déploiement sur Reddit
   - Contrôle total du code

3. **Toujours supporté par Reddit**
   - L'API REST classique fonctionne toujours
   - PRAW est maintenu et à jour
   - Pas de migration forcée vers Devvit

---

## 🔧 Comment Obtenir les Credentials (API Classique)

### Méthode qui fonctionne en 2024-2025:

**1. Utiliser l'ancienne interface Reddit**
```
URL: https://old.reddit.com/prefs/apps
```

**2. Créer une "script app"**
```
Name:         trading-platform-ingestor
App type:     script
Description:  Data collection for analysis
About URL:    (vide)
Redirect URI: http://localhost:8080
```

**3. Récupérer les credentials**
```
Client ID:     [sous le nom de l'app]
Client Secret: [ligne "secret:"]
```

**4. Configurer dans .env**
```bash
REDDIT_CLIENT_ID=votre_client_id
REDDIT_CLIENT_SECRET=votre_secret
```

---

## 🆚 Comparaison Devvit vs API Classique

| Critère | Devvit | API Classique (PRAW) |
|---------|--------|---------------------|
| **Hébergement** | Reddit servers | Vos serveurs |
| **Langage** | TypeScript | Python/Tout |
| **Use case** | Apps intégrées | Collecte externe |
| **Notre code compatible** | ❌ Non | ✅ Oui |
| **Setup** | npm, devvit CLI | pip, credentials |
| **Temps setup** | 30 min + dev | 5 min |
| **Migration nécessaire** | ✅ Oui (réécriture) | ❌ Non |
| **Coût** | Gratuit | Gratuit |
| **Rate limits** | Similaires | 60 req/min |

---

## 📖 Documentation

### API Classique (Ce que nous utilisons):
- **PRAW**: https://praw.readthedocs.io/
- **Reddit API**: https://www.reddit.com/dev/api/
- **OAuth**: https://github.com/reddit-archive/reddit/wiki/OAuth2

### Devvit (Pour info):
- **Site officiel**: https://developers.reddit.com/
- **Docs**: https://developers.reddit.com/docs
- **GitHub**: https://github.com/reddit/devvit

---

## 🚀 Actions à Faire

### ✅ Pour utiliser notre système (recommandé):

1. **Créer une script app sur old.reddit.com**
   ```bash
   # Aller sur:
   https://old.reddit.com/prefs/apps
   ```

2. **Récupérer les credentials**

3. **Configurer .env**
   ```bash
   cd /home/leox7/trading-platform/infra
   nano .env
   # Éditer REDDIT_CLIENT_ID et REDDIT_CLIENT_SECRET
   ```

4. **Démarrer le service**
   ```bash
   docker compose up -d reddit-ingestor
   ```

### ❌ Si vous voulez absolument utiliser Devvit:

**Il faudrait:**
1. Réécrire tout le code en TypeScript
2. Adapter l'architecture pour Devvit
3. Déployer sur les serveurs Reddit
4. Trouver un moyen d'exporter vers Kafka/MinIO

**Estimation:** 2-3 semaines de développement

**Pas recommandé** pour notre cas d'usage.

---

## 🤔 FAQ

**Q: Est-ce que l'API classique va disparaître ?**
R: Non, Reddit la maintient toujours. Devvit est une option supplémentaire, pas un remplacement.

**Q: Devvit est-il obligatoire ?**
R: Non, seulement pour les apps intégrées à Reddit (bots, widgets).

**Q: Notre code PRAW va-t-il cesser de fonctionner ?**
R: Non, PRAW utilise l'API REST qui est toujours maintenue.

**Q: Quand utiliser Devvit ?**
R: Pour créer des bots interactifs, des jeux, des widgets personnalisés dans Reddit.

**Q: Peut-on utiliser Devvit pour collecter des données ?**
R: Techniquement oui, mais c'est plus complexe et pas conçu pour ça.

**Q: Les rate limits sont différents ?**
R: Non, similaires (~60 requêtes/minute).

---

## 📝 Résumé Simple

```
┌─────────────────────────────────────────────────┐
│  Devvit                                         │
│  - Apps DANS Reddit                             │
│  - TypeScript                                   │
│  - Nécessite réécriture                         │
│  ❌ Pas adapté pour nous                        │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  API Classique (PRAW)                           │
│  - Collecte EXTERNE                             │
│  - Python                                       │
│  - Code actuel compatible                       │
│  ✅ Parfait pour notre cas                      │
└─────────────────────────────────────────────────┘
```

**→ Utilisez l'API classique via old.reddit.com/prefs/apps**

---

## 🔗 Liens Utiles

- **Créer une app**: https://old.reddit.com/prefs/apps
- **Documentation API**: https://www.reddit.com/dev/api/
- **PRAW Docs**: https://praw.readthedocs.io/
- **Notre guide**: [REDDIT_SETUP_REQUIRED.md](REDDIT_SETUP_REQUIRED.md)
- **Quickstart sans Reddit**: [QUICKSTART_SANS_REDDIT.md](QUICKSTART_SANS_REDDIT.md)

---

**💡 Conseil: N'utilisez Devvit que si vous créez un bot Reddit interactif. Pour la collecte de données, l'API classique est parfaite.**
