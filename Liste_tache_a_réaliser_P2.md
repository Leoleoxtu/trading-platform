#### Tâche 4.6 : Execution Adapter
- [ ] Créer `src/execution/ibkr_adapter.py`
- [ ] Consumer Kafka : `signals.final.v1`
- [ ] Pour chaque signal :
  - [ ] Re-check Risk Gate Hard
  - [ ] Pre-flight check
  - [ ] Mapping Signal → IBKR Order :
    ```python
    if signal.action == "BUY":
        order = LimitOrder(
            action="BUY",
            totalQuantity=signal.plan.quantity,
            lmtPrice=signal.plan.limit_price,
            tif="DAY"
        )
    ```
  - [ ] Submit order
  - [ ] Attacher bracket orders (stop + target)
- [ ] Publier `orders.intent.v1` (intent)
- [ ] Publier `orders.executed.v1` (confirmation)

#### Tâche 4.7 : Order Status Tracking
- [ ] Subscribe IBKR order updates
- [ ] Statuses : Submitted, Filled, Cancelled, Rejected
- [ ] Update PostgreSQL `orders` table
- [ ] Si rejected : log reason + alert

#### Tâche 4.8 : Position Manager
- [ ] Créer `src/execution/position_manager.py`
- [ ] Sync positions IBKR ↔ PostgreSQL
- [ ] Calculate PnL real-time
- [ ] Update Redis cache (positions_live)
- [ ] Métriques (positions_open, capital_deployed)

#### Tâche 4.9 : Tests Execution (Paper Trading)
- [ ] Test ordre LIMIT buy
- [ ] Test ordre MARKET sell
- [ ] Test bracket orders (stop + target)
- [ ] Test rejection handling
- [ ] Valider sync positions

---

## 👁️ PHASE 5 : GUARDIAN & MEMORY (Semaine 6 - Jours 36-42)

### JOUR 36-38 : Position Watcher

#### Tâche 5.1 : Guardian Levels Logic
- [ ] Créer `src/execution/position_watcher.py`
- [ ] Définir niveaux :
  ```python
  def calculate_guardian_level(position):
      if position.pnl_pct > 0.02 and position.volatility < 1.5:
          return "PASSIVE"  # Check 30 min
      elif position.age_minutes < 120 or -0.01 < position.pnl_pct < 0.02:
          return "ACTIVE"   # Check 5 min
      elif -0.03 < position.pnl_pct < -0.01 or position.vol_spike > 2:
          return "ALERT"    # Check 1 min
      elif position.pnl_pct < -0.03:
          return "EMERGENCY"  # Check real-time
  ```

#### Tâche 5.2 : Monitoring Loop
- [ ] Pour chaque position ouverte :
  - [ ] Get current price
  - [ ] Calculate PnL, drawdown
  - [ ] Determine guardian_level
  - [ ] Schedule next check selon level
- [ ] Si ALERT/EMERGENCY :
  - [ ] Trigger web research (autorisé)
  - [ ] Re-run Decision Engine avec context "position_in_danger"
  - [ ] Ajuster stop dynamiquement si vol spike

#### Tâche 5.3 : Auto-Exit Conditions
- [ ] Function `check_exit_conditions(position)` :
  ```python
  # Stop loss hit
  if current_price <= position.stop_loss:
      return EXIT("Stop loss")
  
  # Time stop
  if position.age_minutes > position.max_hold_time:
      return EXIT("Time stop")
  
  # Take profit
  if current_price >= position.take_profit_1:
      return EXIT_PARTIAL("Take profit 1")
  
  # Emergency regime
  if get_regime() == "FLASH_CRASH":
      return EXIT_ALL("Emergency")
  ```
- [ ] Execute exit via IBKR
- [ ] Log reason

#### Tâche 5.4 : Market Sentinel
- [ ] Créer `src/monitoring/market_sentinel.py`
- [ ] Monitor global :
  - [ ] VIX > 40 → Alert
  - [ ] SPY circuit breaker → Alert
  - [ ] Volume spike sector (> 5σ) → Alert
- [ ] Publier `alerts.priority.v1`

#### Tâche 5.5 : Alerting System
- [ ] Config `config/alerts.yaml` :
  ```yaml
  channels:
    - type: email
      to: trader@example.com
      enabled: true
    - type: slack
      webhook: https://hooks.slack.com/...
      enabled: true
    - type: sms
      provider: twilio
      to: +33612345678
      enabled: false
  ```
- [ ] Créer `src/monitoring/alerts.py`
- [ ] Send alert selon severity (WARNING, CRITICAL)

#### Tâche 5.6 : Tests Position Watcher
- [ ] Mock position avec PnL -2.5%
- [ ] Vérifier guardian_level = ALERT
- [ ] Vérifier réévaluation déclenchée
- [ ] Test auto-exit stop loss
- [ ] Test alert envoyé

---

### JOUR 39-42 : Memory & Learning

#### Tâche 5.7 : Decision Log
- [ ] Créer table `decision_logs` :
  ```sql
  CREATE TABLE decision_logs (
    log_id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    ticker VARCHAR(10),
    input_pack JSONB,
    signal JSONB,
    execution JSONB,
    outcome JSONB,
    post_mortem JSONB
  );
  ```
- [ ] Créer `src/learning/decision_logger.py`
- [ ] Logger chaque trade avec contexte complet

#### Tâche 5.8 : Post-Mortem Generator
- [ ] Créer `src/learning/post_mortem.py`
- [ ] Trigger : Position fermée
- [ ] Analyse :
  ```python
  def generate_post_mortem(trade):
      return {
          "what_worked": [
              "Scenario entry conditions accurate",
              "NewsCard impact confirmed"
          ],
          "what_failed": [
              "Stop too tight, hit by noise"
          ],
          "luck_factor": 0.2,  # 20% luck estimate
          "lessons": [
              "Widen stops in high vol regime"
          ]
      }
  ```
- [ ] Stocker dans decision_logs

#### Tâche 5.9 : Meta-Learner
- [ ] Créer `src/learning/meta_learner.py`
- [ ] Trigger : Dimanche 20:00 ET (cron)
- [ ] Analyse derniers 50 trades :
  - [ ] Détecte patterns gagnants
  - [ ] Détecte anti-patterns
  - [ ] Évalue performance scénarios
- [ ] Prompt LLM (Opus) :
  ```
  Analyse ces 50 trades. Détecte patterns.
  
  Trades: [...]
  
  Output JSON:
  {
    "patterns_winning": [...],
    "anti_patterns": [...],
    "scenario_performance": {...}
  }
  ```

#### Tâche 5.10 : Confidence Modifiers
- [ ] Créer table `confidence_modifiers` :
  ```sql
  CREATE TABLE confidence_modifiers (
    pattern_id VARCHAR(50),
    description TEXT,
    modifier FLOAT,
    sample_size INT,
    win_rate FLOAT,
    created_at TIMESTAMPTZ
  );
  ```
- [ ] Update modifiers depuis Meta-Learner
- [ ] Apply dans Decision Engine :
  ```python
  base_confidence = 0.70
  if matches_pattern("PATTERN_47"):
      adjusted = base_confidence + get_modifier("PATTERN_47")
  ```

#### Tâche 5.11 : Confidence Calibrator (mensuel)
- [ ] Créer `src/learning/calibrator.py`
- [ ] Trigger : 1er du mois
- [ ] Après 1000+ NewsCards :
  - [ ] Mesure accuracy par bucket confidence
  - [ ] Calcule fonction calibration empirique
  - [ ] Update fonction dans Standardizer

#### Tâche 5.12 : Weekly Report Generator
- [ ] Créer `src/learning/report_generator.py`
- [ ] Trigger : Dimanche 21:00 ET
- [ ] Génère rapport PDF :
  - [ ] Performance metrics (Sharpe, DD, Win rate)
  - [ ] Top 5 / Worst 5 trades
  - [ ] Patterns détectés
  - [ ] Recommendations
- [ ] Archive dans MinIO (`reports/`)
- [ ] Email au trader

#### Tâche 5.13 : Tests Memory System
- [ ] Mock 50 trades variés
- [ ] Test Meta-Learner détecte pattern
- [ ] Vérifier confidence modifiers appliqués
- [ ] Test report generation

---

## 🖥️ PHASE 6 : FRONTEND & API (Semaine 7 - Jours 43-49)

### JOUR 43-45 : Backend API

#### Tâche 6.1 : FastAPI Setup
- [ ] Créer `src/api/main.py`
- [ ] Routes :
  ```python
  @app.get("/health")
  @app.get("/positions/live")
  @app.get("/signals/today")
  @app.get("/newscards")
  @app.get("/scenarios/{ticker}")
  @app.get("/performance/metrics")
  @app.websocket("/stream/updates")
  ```

#### Tâche 6.2 : Database Queries
- [ ] Créer `src/api/queries.py`
- [ ] Functions :
  - [ ] `get_live_positions()` → List[Position]
  - [ ] `get_signals_today()` → List[Signal]
  - [ ] `get_newscards(ticker, hours)` → List[NewsCard]
  - [ ] `get_scenarios(ticker)` → List[Scenario]
  - [ ] `get_performance_metrics(days)` → Metrics

#### Tâche 6.3 : WebSocket Stream
- [ ] Créer `src/api/websocket.py`
- [ ] Consumer Kafka topics :
  - [ ] `signals.final.v1`
  - [ ] `orders.executed.v1`
  - [ ] `alerts.priority.v1`
- [ ] Broadcast vers clients WebSocket
- [ ] Heartbeat toutes les 30s

#### Tâche 6.4 : Authentication
- [ ] JWT tokens
- [ ] Route `/login` (username/password)
- [ ] Middleware protect routes
- [ ] Config users dans `.env`

#### Tâche 6.5 : CORS Configuration
- [ ] Allow origins : `http://localhost:3000` (dev)
- [ ] Allow methods : GET, POST, WebSocket
- [ ] Allow credentials

#### Tâche 6.6 : API Tests
- [ ] Test chaque endpoint
- [ ] Test WebSocket connection
- [ ] Test JWT auth
- [ ] Load test (100 req/s)

---

### JOUR 46-49 : Frontend React

#### Tâche 6.7 : React App Setup
- [ ] Init : `npx create-react-app trading-frontend`
- [ ] Install deps :
  ```bash
  npm install @tanstack/react-query recharts socket.io-client
  npm install axios react-router-dom
  ```
- [ ] Structure :
  ```
  src/
  ├── components/
  ├── pages/
  ├── hooks/
  ├── api/
  └── utils/
  ```

#### Tâche 6.8 : API Client
- [ ] Créer `src/api/tradingApi.ts`
- [ ] Axios instance avec base URL
- [ ] Functions pour chaque endpoint
- [ ] Error handling

#### Tâche 6.9 : WebSocket Hook
- [ ] Créer `src/hooks/useWebSocket.ts`
- [ ] Connect to backend WS
- [ ] Handle events : `position_update`, `new_signal`, `alert`
- [ ] Auto-reconnect si disconnect

#### Tâche 6.10 : Dashboard Page
- [ ] Créer `src/pages/Dashboard.tsx`
- [ ] Components :
  - [ ] `<PortfolioOverview />` : PnL, Sharpe, Positions
  - [ ] `<PerformanceChart />` : Courbe PnL 30D
  - [ ] `<LivePositions />` : Table positions
  - [ ] `<RecentSignals />` : 5 derniers signaux
  - [ ] `<LatestNewsCards />` : 5 dernières news
- [ ] Real-time updates via WebSocket

#### Tâche 6.11 : Live Positions Page
- [ ] Créer `src/pages/LivePositions.tsx`
- [ ] Table columns :
  - [ ] Ticker, Entry, Current, PnL%, Guardian Level
  - [ ] Actions : [View Detail] [Force Exit]
- [ ] Color coding (green = profit, red = loss)
- [ ] Auto-refresh 5s

#### Tâche 6.12 : Signals Feed Page
- [ ] Créer `src/pages/SignalsFeed.tsx`
- [ ] Real-time feed (WebSocket)
- [ ] Filters : Action (BUY/SELL/HOLD), Ticker
- [ ] Card per signal :
  - [ ] Ticker, Action, Confidence
  - [ ] Entry/Stop/Target
  - [ ] Reasoning (collapsible)
  - [ ] [View Detail] button

#### Tâche 6.13 : NewsCards Browser Page
- [ ] Créer `src/pages/NewsCardsBrowser.tsx`
- [ ] Search par ticker
- [ ] Filters : Type, Impact, Time horizon
- [ ] List view avec pagination
- [ ] Detail modal

#### Tâche 6.14 : Scenarios Page
- [ ] Créer `src/pages/Scenarios.tsx`
- [ ] Dropdown select ticker
- [ ] Display 3 scénarios :
  - [ ] Bullish / Neutral / Bearish
  - [ ] Probability, Entry conditions, Targets
  - [ ] Status : Active / Monitoring / Inactive
- [ ] Show pending catalysts
- [ ] Next update countdown

#### Tâche 6.15 : Agent Activity Page
- [ ] Créer `src/pages/AgentActivity.tsx`
- [ ] Table agents :
  - [ ] Name, Status, Calls/Hour, Latency, Cost/Hour
- [ ] Total cost today vs. budget
- [ ] Provider distribution pie chart

#### Tâche 6.16 : Risk Dashboard Page
- [ ] Créer `src/pages/RiskDashboard.tsx`
- [ ] Metrics cards :
  - [ ] Max Drawdown
  - [ ] Daily Loss vs Limit
  - [ ] Positions Open
- [ ] Correlation heatmap (recharts)
- [ ] Sector exposure pie chart
- [ ] Risk Gate rejections log

#### Tâche 6.17 : Styling & Polish
- [ ] CSS global (dark theme recommandé)
- [ ] Responsive design (mobile-friendly)
- [ ] Loading states
- [ ] Error boundaries
- [ ] Toast notifications (alerts)

#### Tâche 6.18 : Frontend Tests
- [ ] Test chaque page renders
- [ ] Test WebSocket connection
- [ ] Test user interactions
- [ ] E2E test avec Playwright

---

## 🧪 PHASE 7 : BACKTESTING & VALIDATION (Semaine 8 - Jours 50-56)

### JOUR 50-52 : Backtest Infrastructure

#### Tâche 7.1 : Historical Data Loader
- [ ] Créer `src/backtesting/data_loader.py`
- [ ] Download OHLCV 6 mois (50 tickers)
- [ ] Download historical news (scrape archives)
- [ ] Format : Same schema que production
- [ ] Store dans MinIO (`backtest/data/`)

#### Tâche 7.2 : Event Replayer
- [ ] Créer `src/backtesting/replayer.py`
- [ ] Replay events chronologique
- [ ] Simulate Kafka (in-memory queue)
- [ ] Respect timing (market hours, delays)
- [ ] Fast-forward option (100x speed)

#### Tâche 7.3 : Backtest Engine
- [ ] Créer `src/backtesting/engine.py`
- [ ] Config :
  ```yaml
  backtest:
    start_date: 2024-07-01
    end_date: 2024-12-31
    initial_capital: 10000
    mode: realistic  # realistic vs optimistic
  ```
- [ ] Run entire system (tous modules)
- [ ] Paper orders (no real broker)
- [ ] Fill simulation (realistic slippage)

#### Tâche 7.4 : Performance Metrics
- [ ] Créer `src/backtesting/metrics.py`
- [ ] Calculate :
  - [ ] Total Return
  - [ ] Sharpe Ratio
  - [ ] Max Drawdown
  - [ ] Win Rate
  - [ ] Profit Factor
  - [ ] Average Hold Time
  - [ ] Max Adverse Excursion
  - [ ] Calmar Ratio
- [ ] Generate equity curve

#### Tâche 7.5 : Report Generator
- [ ] Créer `src/backtesting/report.py`
- [ ] PDF report :
  - [ ] Summary metrics
  - [ ] Equity curve chart
  - [ ] Monthly returns table
  - [ ] Top 10 / Worst 10 trades
  - [ ] Drawdown periods
- [ ] Save to MinIO

---

### JOUR 53-56 : Validation & Tuning

#### Tâche 7.6 : Run Full Backtest
- [ ] Execute : `python -m src.backtesting.engine`
- [ ] Duration : ~6h (6 mois data)
- [ ] Monitor logs, errors
- [ ] Collect metrics

#### Tâche 7.7 : Analyze Results
- [ ] Review report PDF
- [ ] Check objectives :
  - [ ] Sharpe > 1.5 ✓ ou ✗
  - [ ] Max DD < 15% ✓ ou ✗
  - [ ] Win rate > 52% ✓ ou ✗
  - [ ] Profit factor > 1.3 ✓ ou ✗

#### Tâche 7.8 : Parameter Tuning
Si objectifs non atteints :
- [ ] Ajuster confidence thresholds
  - [ ] Tester seuils 0.6, 0.65, 0.7, 0.75
- [ ] Ajuster stop/target ratios
  - [ ] Tester 1:1.5, 1:2, 1:2.5
- [ ] Ajuster scenario probabilities
- [ ] Re-run backtest
- [ ] Iterate jusqu'à objectifs

#### Tâche 7.9 : Walk-Forward Analysis
- [ ] Split data : Train (4 mois) / Test (2 mois)
- [ ] Optimize sur Train
- [ ] Validate sur Test
- [ ] Vérifier pas d'overfitting

#### Tâche 7.10 : Sensitivity Analysis
- [ ] Test robustesse :
  - [ ] +/- 20% sur chaque paramètre
  - [ ] Vérifier performance reste stable
- [ ] Identifier paramètres critiques

#### Tâche 7.11 : Scenario Testing
- [ ] Test sur périodes spécifiques :
  - [ ] Bull market (Nov 2024)
  - [ ] Bear market (Aug 2024)
  - [ ] High volatility (Oct 2024)
- [ ] Vérifier adaptabilité

#### Tâche 7.12 : Documentation Results
- [ ] Créer `docs/backtest_results.md`
- [ ] Screenshots equity curve
- [ ] Lessons learned
- [ ] Recommendations pour paper trading

---

## 🎯 PHASE 8 : PAPER TRADING (Semaine 9-12 - Jours 57-84)

### JOUR 57 : Pré-Déploiement

#### Tâche 8.1 : Production Config
- [ ] Créer `config/production.yaml`
- [ ] Mode : `paper_trading`
- [ ] IBKR : Port 4002 (paper)
- [ ] Limits conservateurs :
  ```yaml
  risk:
    max_position_pct: 0.05  # 5% (vs 10% full prod)
    max_trades_per_day: 5
    max_open_positions: 3
  ```

#### Tâche 8.2 : Monitoring Enhanced
- [ ] Setup PagerDuty (ou équivalent)
- [ ] Alertes critiques → SMS
- [ ] Dashboard Grafana public URL
- [ ] Logs centralisés (Loki optionnel)

#### Tâche 8.3 : Backup Automatique
- [ ] Script backup DB : `scripts/backup_db.sh`
- [ ] Cron daily : `0 2 * * * /path/backup_db.sh`
- [ ] Backup MinIO vers S3 externe (optionnel)
- [ ] Retention : 30 jours

#### Tâche 8.4 : Disaster Recovery Plan
- [ ] Document `docs/disaster_recovery.md` :
  - [ ] Que faire si Redpanda crash ?
  - [ ] Que faire si DB corrompue ?
  - [ ] Que faire si IA API down ?
  - [ ] Procédures rollback
- [ ] Test DR scenario

#### Tâche 8.5 : Kill Switch
- [ ] Route API : `POST /emergency/shutdown`
- [ ] Actions :
  - [ ] Stop tous collectors
  - [ ] Exit toutes positions (market orders)
  - [ ] Disable agents
  - [ ] Alert admin
- [ ] Bouton rouge dans frontend

---

### JOUR 58-84 : Paper Trading Actif (4 Semaines)

#### Tâche 8.6 : Semaine 1 - Observation
- [ ] Démarrer système : `docker-compose up -d`
- [ ] Observer 5 jours (pas d'intervention)
- [ ] Daily checklist :
  - [ ] Check dashboard matin (8h)
  - [ ] Review signals générés
  - [ ] Check positions ouvertes/fermées
  - [ ] Review logs erreurs
  - [ ] Check coûts IA
  - [ ] Note incidents dans journal

#### Tâche 8.7 : Semaine 1 - Analyse
- [ ] Vendredi soir : Generate weekly report
- [ ] Review :
  - [ ] Nombre trades : Attendu vs Réel
  - [ ] Win rate paper
  - [ ] Latences (< 1s ?)
  - [ ] Coûts IA (dans budget ?)
  - [ ] Erreurs / bugs détectés
- [ ] Créer tickets pour bugs

#### Tâche 8.8 : Semaine 2 - Fixes
- [ ] Corriger bugs critiques S1
- [ ] Ajuster paramètres si nécessaire
- [ ] Continuer observation
- [ ] Daily + weekly review

#### Tâche 8.9 : Semaine 3 - Stabilisation
- [ ] Système devrait être stable
- [ ] Focus sur métriques performance
- [ ] Comparer vs backtest :
  - [ ] Sharpe similaire ?
  - [ ] Drawdown similaire ?
  - [ ] Si divergence → investigate

#### Tâche 8.10 : Semaine 4 - Validation Finale
- [ ] Calculate métriques 4 semaines :
  ```
  Trades total : X
  Win rate : Y%
  Sharpe : Z
  Max DD : W%
  Uptime : U%
  Avg latency : L ms
  Total cost IA : $C
  ```
- [ ] Decision GO / NO-GO pour live

#### Tâche 8.11 : Critères Passage Live
Valider tous :
- [ ] Sharpe paper > 1.3
- [ ] Max DD paper < 20%
- [ ] 0 violation risk limits
- [ ] Latence p95 < 1s
- [ ] Uptime > 99.5%
- [ ] 0 bug critique non résolu
- [ ] Coûts IA dans budget

---

## 🚀 PHASE 9 : LIVE TRADING (Semaine 13+ - Jour 85+)

### JOUR 85 : Pré-Live Checklist

#### Tâche 9.1 : Transition Paper → Live
- [ ] Config : `mode: live_trading`
- [ ] IBKR : Switch port 4002 → 4001 (live)
- [ ] Re-test connexion IBKR live
- [ ] Vérifier capital disponible

#### Tâche 9.2 : Capital Initial Limité
- [ ] Semaine 1-2 : Capital 1000€
- [ ] Max 1 position
- [ ] Max 2% capital/trade (20€)
- [ ] Stop loss agressif (1.5%)

#### Tâche 9.3 : Monitoring 24/7
- [ ] Alertes activées (SMS pour CRITICAL)
- [ ] Dashboard accessible mobile
- [ ] Journal trading prêt (noter toute anomalie)

#### Tâche 9.4 : First Live Trade
- [ ] Attendre signal haute confiance (> 0.8)
- [ ] Valider manuellement avant execution
- [ ] Observer comportement
- [ ] Logger émotions (humain) + metrics (système)

---

### JOUR 86-98 : Semaines 1-2 Live (Capital Limité)

#### Tâche 9.5 : Daily Routine
Chaque jour trading :
- [ ] 08:00 - Check système health
- [ ] 08:30 - Review scénarios pré-market
- [ ] 09:30 - Market open, monitoring actif
- [ ] 12:00 - Mid-day check
- [ ] 16:00 - Market close, review
- [ ] 17:00 - Post-mortem trades du jour

#### Tâche 9.6 : Incident Tracking
- [ ] Créer spreadsheet incidents :
  ```
  Date | Type | Description | Impact | Resolution
  ```
- [ ] Logger tout problème
- [ ] Categorize : Bug / Mauvaise décision IA / Mauvaise chance

#### Tâche 9.7 : Weekly Review Live
Chaque vendredi :
- [ ] PnL semaine
- [ ] Compare vs paper trading (divergence ?)
- [ ] Trades exécutés vs signaux générés (execution rate)
- [ ] Slippage moyen (prix intent vs fill)
- [ ] Emotional log (stress, confiance)

---

### JOUR 99+ : Scale Progressif

#### Tâche 9.8 : Decision Scale Up
Si après 2 semaines :
- [ ] PnL positif (même si petit)
- [ ] Aucun incident majeur
- [ ] Comportement prévisible

→ Augmenter capital : 1000€ → 5000€

#### Tâche 9.9 : Ajustements Limites
- [ ] Max 3 positions
- [ ] Max 5% capital/trade
- [ ] Stops moins agressifs (2%)

#### Tâche 9.10 : Scale Graduel
Plan sur 6 mois :
```
Mois 1 : 1k€ capital, 1 position max
Mois 2 : 5k€ capital, 3 positions max
Mois 3 : 10k€ capital, 5 positions max
Mois 4 : 20k€ capital, 5 positions max
Mois 5 : 50k€ capital, 5 positions max
Mois 6 : 100k€ capital, full production mode
```

#### Tâche 9.11 : Continuous Improvement
- [ ] Monthly meta-learner review
- [ ] Quarterly confidence recalibration
- [ ] Bi-annual full backtest (nouveaux 6 mois)
- [ ] Annual strategy review

---

## 🔧 TÂCHES TRANSVERSALES (Tout au Long)

### Documentation

#### Tâche T.1 : README.md
- [ ] Créer `README.md` :
  - [ ] Description projet
  - [ ] Quick start
  - [ ] Architecture overview
  - [ ] Links vers docs

#### Tâche T.2 : API Documentation
- [ ] FastAPI auto-doc : http://localhost:8000/docs
- [ ] Compléter docstrings
- [ ] Export OpenAPI spec

#### Tâche T.3 : Runbook Opérations
- [ ] Créer `docs/runbook.md` :
  - [ ] Comment démarrer système
  - [ ] Comment arrêter proprement
  - [ ] Troubleshooting commun
  - [ ] Procédures maintenance

#### Tâche T.4 : CHANGELOG
- [ ] Créer `CHANGELOG.md`
- [ ] Noter chaque changement significatif
- [ ] Format : Keep a Changelog

---

### Testing (Continu)

#### Tâche T.5 : Tests Unitaires
- [ ] Objectif : Coverage > 80%
- [ ] Utiliser pytest
- [ ] CI/CD : Run tests sur chaque commit

#### Tâche T.6 : Tests Intégration
- [ ] Test pipeline end-to-end
- [ ] Test avec fixtures réelles
- [ ] Slow tests (mark `@pytest.mark.slow`)

#### Tâche T.7 : Tests Property-Based
- [ ] Hypothesis pour risk gate
- [ ] Vérifier invariants (ex: position size jamais > 10%)

#### Tâche T.8 : Chaos Engineering
- [ ] Simulate Redpanda failure
- [ ] Simulate API timeout
- [ ] Simulate DB slow queries
- [ ] Vérifier recovery

---

### Sécurité

#### Tâche T.9 : Secrets Management
- [ ] Ne JAMAIS commit `.env`
- [ ] Utiliser variables environnement
- [ ] Rotate API keys tous les 90 jours

#### Tâche T.10 : Network Security
- [ ] Firewall : Only expose necessary ports
- [ ] HTTPS pour API (Let's Encrypt)
- [ ] VPN pour accès production (optionnel)

#### Tâche T.11 : Audit Logs
- [ ] Logger tous accès API (qui, quand, quoi)
- [ ] Logger toutes décisions trading
- [ ] Retention logs : 1 an minimum

---

### Performance

#### Tâche T.12 : Profiling
- [ ] Python profiler (cProfile)
- [ ] Identifier bottlenecks
- [ ] Optimize hot paths

#### Tâche T.13 : Database Optimization
- [ ] Index sur colonnes queries fréquentes
- [ ] VACUUM PostgreSQL régulier
- [ ] TimescaleDB compression active

#### Tâche T.14 : Caching Strategy
- [ ] Redis pour données hot (positions, last prices)
- [ ] TTL approprié (30s - 5min)
- [ ] Cache invalidation sur updates

---

## 📋 CHECKLIST FINALE DE PRODUCTION

### Infrastructure
- [ ] Tous services Docker up
- [ ]# 📋 LISTE DE TÂCHES DÉVELOPPEUR
## Système de Trading Algorithmique IA

**Durée estimée totale** : 56 jours (8 semaines) + 4 semaines paper trading
**Pré-requis** : Python 3.11+, Docker, Git, Compte Anthropic/OpenAI, Compte IBKR

---

## 🔧 PHASE 1 : INFRASTRUCTURE DE BASE (Semaine 1 - Jours 1-7)

### JOUR 1-2 : Setup Services Fondamentaux

#### Tâche 1.1 : Initialiser le Projet
- [ ] Créer repo Git : `git init trading-system`
- [ ] Structure de dossiers :
  ```
  trading-system/
  ├── docker-compose.yml
  ├── docker-compose.scale.yml
  ├── .env.example
  ├── requirements.txt
  ├── src/
  ├── config/
  ├── tests/
  ├── scripts/
  └── docs/
  ```
- [ ] Créer `.gitignore` (env files, __pycache__, logs, data)
- [ ] Premier commit

#### Tâche 1.2 : Docker Compose Base
- [ ] Créer `docker-compose.yml` avec services :
  - [ ] Redpanda (Kafka)
  - [ ] MinIO (S3)
  - [ ] PostgreSQL
  - [ ] Redis
  - [ ] Kafka UI
- [ ] Tester démarrage : `docker-compose up -d`
- [ ] Vérifier santé : `docker-compose ps`

#### Tâche 1.3 : Configuration Redpanda
- [ ] Créer topics Kafka :
  ```bash
  rpk topic create events.raw.v1 --partitions 10
  rpk topic create events.normalized.v1 --partitions 10
  rpk topic create events.triaged.v1 --partitions 5
  rpk topic create newscards.v1 --partitions 5
  rpk topic create market.ohlcv.v1 --partitions 20
  rpk topic create signals.final.v1 --partitions 3
  rpk topic create orders.intent.v1 --partitions 2
  rpk topic create orders.executed.v1 --partitions 2
  rpk topic create alerts.priority.v1 --partitions 5
  rpk topic create learning.outcomes.v1 --partitions 1
  ```
- [ ] Tester producer/consumer basique
- [ ] Accéder Kafka UI : http://localhost:8080

#### Tâche 1.4 : Configuration MinIO
- [ ] Créer buckets S3 :
  ```
  raw-events
  newscards-archive
  scenarios-archive
  reports
  backups
  ```
- [ ] Configurer lifecycle policy (rétention 30-90 jours)
- [ ] Tester upload/download fichier
- [ ] Accéder console : http://localhost:9001

#### Tâche 1.5 : Configuration PostgreSQL
- [ ] Créer base `trading`
- [ ] Créer user `trader` avec permissions
- [ ] Tester connexion : `psql -h localhost -U trader -d trading`

#### Tâche 1.6 : Configuration Redis
- [ ] Tester connexion : `redis-cli ping`
- [ ] Configurer maxmemory policy : `allkeys-lru`
- [ ] Tester set/get

---

### JOUR 3-4 : TimescaleDB & Monitoring

#### Tâche 1.7 : Installation TimescaleDB
- [ ] Installer extension TimescaleDB dans PostgreSQL
- [ ] Créer hypertables :
  ```sql
  CREATE TABLE ohlcv (
    time TIMESTAMPTZ NOT NULL,
    ticker VARCHAR(10),
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume BIGINT
  );
  SELECT create_hypertable('ohlcv', 'time');
  ```
- [ ] Créer continuous aggregates (VWAP 1h, 1d)
- [ ] Tester insertion données

#### Tâche 1.8 : Schéma Base de Données
- [ ] Créer tables :
  - [ ] `newscards` (event_id, ticker, type, impact, etc.)
  - [ ] `scenarios` (scenario_id, ticker, version, conditions, etc.)
  - [ ] `positions` (position_id, ticker, entry, current, pnl, etc.)
  - [ ] `orders` (order_id, ticker, action, status, etc.)
  - [ ] `decision_logs` (log_id, input_pack, signal, outcome, etc.)
  - [ ] `agent_performance` (agent_name, calls, latency, cost, etc.)
- [ ] Créer index optimisés (ticker, timestamp)
- [ ] Créer script migration : `scripts/db_migration.sql`

#### Tâche 1.9 : Setup Prometheus + Grafana
- [ ] Ajouter services au docker-compose :
  - [ ] Prometheus
  - [ ] Grafana
- [ ] Créer `config/prometheus.yml` avec scrape configs
- [ ] Accéder Grafana : http://localhost:3000 (admin/admin)
- [ ] Ajouter datasource Prometheus

#### Tâche 1.10 : Dashboards Grafana Initiaux
- [ ] Dashboard "System Health" :
  - [ ] Panels : CPU, RAM, Disk, Network
  - [ ] Panel : Redpanda throughput
  - [ ] Panel : PostgreSQL connections
- [ ] Exporter JSON : `dashboards/grafana/system_health.json`
- [ ] Test alerting : Alert si CPU > 80%

---

### JOUR 5-7 : Environment & Testing Infrastructure

#### Tâche 1.11 : Configuration Environnement
- [ ] Créer `.env.example` :
  ```
  # Databases
  DATABASE_URL=postgresql://trader:password@localhost:5432/trading
  REDIS_URL=redis://localhost:6379
  
  # Kafka
  KAFKA_BROKERS=localhost:9092
  
  # MinIO
  MINIO_ENDPOINT=localhost:9000
  MINIO_ACCESS_KEY=minioadmin
  MINIO_SECRET_KEY=minioadmin
  
  # AI APIs
  ANTHROPIC_API_KEY=sk-ant-...
  OPENAI_API_KEY=sk-...
  
  # Data APIs
  TWITTER_API_KEY=
  REDDIT_CLIENT_ID=
  NEWSAPI_KEY=
  FINNHUB_KEY=
  
  # Broker
  IB_GATEWAY_HOST=localhost
  IB_GATEWAY_PORT=4002
  ```
- [ ] Copier vers `.env` : `cp .env.example .env`
- [ ] Remplir clés API réelles

#### Tâche 1.12 : Requirements Python
- [ ] Créer `requirements.txt` :
  ```
  # Core
  python-dotenv==1.0.0
  pydantic==2.5.0
  loguru==0.7.2
  
  # Kafka
  aiokafka==0.8.1
  
  # Databases
  psycopg2-binary==2.9.9
  sqlalchemy==2.0.23
  redis==5.0.1
  
  # S3
  boto3==1.34.10
  
  # Data Collection
  feedparser==6.0.10
  tweepy==4.14.0
  praw==7.7.1
  requests==2.31.0
  beautifulsoup4==4.12.2
  playwright==1.40.0
  
  # NLP
  spacy==3.7.2
  transformers==4.36.2
  torch==2.1.2
  sentence-transformers==2.2.2
  langdetect==1.0.9
  
  # AI
  langchain==0.1.0
  langgraph==0.0.20
  anthropic==0.8.1
  openai==1.6.1
  
  # Market Data
  yfinance==0.2.33
  ccxt==4.1.92
  ib-insync==0.9.86
  
  # Analysis
  pandas==2.1.4
  numpy==1.26.2
  ta-lib==0.4.28
  
  # API
  fastapi==0.108.0
  uvicorn==0.25.0
  websockets==12.0
  
  # Testing
  pytest==7.4.3
  pytest-asyncio==0.21.1
  hypothesis==6.92.1
  ```
- [ ] Créer venv : `python -m venv venv`
- [ ] Installer : `pip install -r requirements.txt`

#### Tâche 1.13 : Structure Code Base
- [ ] Créer arborescence `src/` :
  ```
  src/
  ├── __init__.py
  ├── ingestion/
  ├── preprocessing/
  ├── nlp/
  ├── agents/
  ├── knowledge/
  ├── strategy/
  ├── execution/
  ├── backtesting/
  ├── learning/
  ├── monitoring/
  └── utils/
  ```
- [ ] Créer `__init__.py` dans chaque dossier

#### Tâche 1.14 : Framework de Test
- [ ] Créer structure `tests/` :
  ```
  tests/
  ├── unit/
  ├── integration/
  ├── e2e/
  └── fixtures/
  ```
- [ ] Créer `pytest.ini`
- [ ] Test basique : `pytest --version`

---

## 📊 PHASE 2 : DATA COLLECTION (Semaine 2 - Jours 8-14)

### JOUR 8-10 : Collectors Core

#### Tâche 2.1 : Interface Abstraite Collector
- [ ] Créer `src/ingestion/base.py` :
  ```python
  from abc import ABC, abstractmethod
  from dataclasses import dataclass
  
  @dataclass
  class RawEvent:
      source: str
      url: str
      text: str
      timestamp: str
      metadata: dict
  
  class Collector(ABC):
      @abstractmethod
      async def collect(self) -> List[RawEvent]:
          pass
  ```

#### Tâche 2.2 : RSS Collector
- [ ] Créer `src/ingestion/rss_collector.py`
- [ ] Charger sources depuis `config/rss_sources.yaml`
- [ ] Parser avec feedparser
- [ ] Publier vers `events.raw.v1` (Redpanda)
- [ ] Archiver dans MinIO (`raw-events/rss/`)
- [ ] Test unitaire : 10 feeds mock
- [ ] Métriques Prometheus (feeds_processed, errors)

#### Tâche 2.3 : Configuration RSS Sources
- [ ] Créer `config/rss_sources.yaml` :
  ```yaml
  sources:
    - name: Bloomberg
      url: https://www.bloomberg.com/feed/...
      priority: high
      quality: 9
    - name: Reuters
      url: https://www.reutersagency.com/feed/...
      priority: high
      quality: 9
    # ... 50+ sources
  ```
- [ ] Ajouter catégories (tech, finance, macro, etc.)

#### Tâche 2.4 : Twitter Collector
- [ ] Créer `src/ingestion/twitter_collector.py`
- [ ] Setup Tweepy avec API key
- [ ] Filtres : #stocks, #trading, comptes vérifés
- [ ] Rate limiting (300 calls/15min)
- [ ] Publier vers Redpanda
- [ ] Test avec API sandbox

#### Tâche 2.5 : Reddit Collector
- [ ] Créer `src/ingestion/reddit_collector.py`
- [ ] Setup PRAW avec credentials
- [ ] Subreddits : wallstreetbets, stocks, investing
- [ ] Filtrer posts score > 50
- [ ] Polling interval : 2 minutes
- [ ] Test unitaire

#### Tâche 2.6 : News API Collector
- [ ] Créer `src/ingestion/news_api_collector.py`
- [ ] Intégration NewsAPI, Finnhub
- [ ] Rate limiting par provider
- [ ] Retry logic avec backoff
- [ ] Fallback si API down

#### Tâche 2.7 : Web Scraper
- [ ] Créer `src/ingestion/web_scraper.py`
- [ ] Playwright setup
- [ ] Sites cibles : Seeking Alpha, MarketWatch
- [ ] Respecter robots.txt
- [ ] Rate limiting 1 req/5s
- [ ] Rotating user-agents

---

### JOUR 11-14 : Market Data & Preprocessing

#### Tâche 2.8 : Market Data Collector
- [ ] Créer `src/ingestion/market_collector.py`
- [ ] yfinance pour données delayed
- [ ] Polygon.io pour real-time (si API key)
- [ ] Tickers watchlist depuis config
- [ ] Insertion directe TimescaleDB
- [ ] Scheduling : 1 min bars pendant market hours

#### Tâche 2.9 : Feature Calculator
- [ ] Créer `src/ingestion/features.py`
- [ ] Calculer indicateurs :
  - [ ] VWAP (1h, 1d)
  - [ ] RSI (14 périodes)
  - [ ] MACD (12, 26, 9)
  - [ ] Bollinger Bands
  - [ ] ATR (Average True Range)
- [ ] Stocker dans TimescaleDB
- [ ] Test avec données mock

#### Tâche 2.10 : Normalizer
- [ ] Créer `src/preprocessing/normalizer.py`
- [ ] Consumer Kafka : `events.raw.v1`
- [ ] Nettoyage texte :
  - [ ] Strip HTML tags
  - [ ] Normaliser Unicode
  - [ ] Supprimer URLs
- [ ] Timestamp vers UTC
- [ ] Déduplication (BloomFilter Redis)
- [ ] Publier vers `events.normalized.v1`
- [ ] Tests unitaires

#### Tâche 2.11 : Triage Stage 1 (Déterministe)
- [ ] Créer `src/preprocessing/triage.py`
- [ ] Règles dures :
  ```python
  KEYWORDS = ['earnings', 'SEC', 'Fed', 'merger', 'bankruptcy']
  def stage1_filter(event):
      if any(kw in event.text.lower() for kw in KEYWORDS):
          return True
      if event.source_quality > 7:
          return True
      return False
  ```
- [ ] Rejeter 70% du bruit
- [ ] Métriques (drop_rate, latency)

#### Tâche 2.12 : Triage Stage 2 (NLP)
- [ ] Télécharger modèles :
  ```bash
  python -m spacy download en_core_web_sm
  python -m spacy download fr_core_news_sm
  ```
- [ ] NER avec spaCy (ORG, MONEY, PERCENT)
- [ ] Sentiment avec FinBERT local
- [ ] Scoring 0-100
- [ ] Seuil adaptatif selon régime
- [ ] Publier vers `events.triaged.v1` avec priority

#### Tâche 2.13 : Orchestration Collectors
- [ ] Créer `src/ingestion/orchestrator.py`
- [ ] Schedule tous collectors (APScheduler)
- [ ] RSS : 5 min
- [ ] Twitter : 1 min (si stream)
- [ ] Reddit : 2 min
- [ ] Market : 1 min (pendant heures ouverture)
- [ ] Health checks
- [ ] Graceful shutdown

#### Tâche 2.14 : Tests Integration Data Pipeline
- [ ] Test end-to-end :
  - [ ] Inject event → RSS collector
  - [ ] Vérifier Redpanda (`events.raw.v1`)
  - [ ] Vérifier MinIO (archive)
  - [ ] Vérifier Normalizer traite
  - [ ] Vérifier Triage filtre
- [ ] Mesurer latency totale (< 5s acceptable)

---

## 🤖 PHASE 3 : AI CORE (Semaine 3-4 - Jours 15-28)

### JOUR 15-18 : Standardizer (NewsCards)

#### Tâche 3.1 : Multi-Provider Setup
- [ ] Créer `src/agents/providers/` :
  - [ ] `anthropic_provider.py`
  - [ ] `openai_provider.py`
  - [ ] `base_provider.py` (interface)
- [ ] Config `config/ai_providers.yaml` :
  ```yaml
  providers:
    - name: anthropic
      models:
        fast: claude-haiku-4-5-20251001
        medium: claude-sonnet-4-5-20250929
        deep: claude-opus-4-20250514
      weight: 0.6
    - name: openai
      models:
        fast: gpt-4o-mini
        medium: gpt-4o
        deep: o1-preview
      weight: 0.4
  ```

#### Tâche 3.2 : NewsCard Schema
- [ ] Créer `src/agents/schemas.py` :
  ```python
  from pydantic import BaseModel
  
  class NewsCard(BaseModel):
      event_id: str
      timestamp: str
      entities: List[str]
      tickers: List[str]
      type: str
      impact_direction: str
      impact_strength: float
      time_horizon: str
      novelty: str
      confidence: float
      uncertainties: List[str]
      why_it_matters: List[str]
      invalidated_if: List[str]
      evidence_refs: List[str]
  ```

#### Tâche 3.3 : Prompt Template NewsCard
- [ ] Créer `src/agents/prompts/newscard_prompt.txt`
- [ ] Variables : {normalized_event}, {context}
- [ ] Output strict JSON
- [ ] Examples few-shot (3-5)

#### Tâche 3.4 : Standardizer Core
- [ ] Créer `src/agents/standardizer.py`
- [ ] Consumer Kafka : `events.triaged.v1`
- [ ] Sélection provider/model selon priority
- [ ] Appel LLM avec prompt
- [ ] Parse JSON response
- [ ] Retry si malformed (max 3)
- [ ] Validation schema Pydantic
- [ ] Stockage :
  - [ ] PostgreSQL (metadata)
  - [ ] MinIO (NewsCard complète)
  - [ ] Redis (cache last 100 par ticker)
- [ ] Publier vers `newscards.v1`

#### Tâche 3.5 : Confidence Calibration
- [ ] Créer `src/agents/calibration.py`
- [ ] Function empirical_calibrate(raw_confidence)
- [ ] Placeholder (linéaire) :
  ```python
  def calibrate(conf):
      if conf > 0.9: return conf * 0.75
      elif conf < 0.6: return conf * 1.1
      return conf
  ```
- [ ] Appliquer avant stockage NewsCard

#### Tâche 3.6 : Tests Standardizer
- [ ] Mock API responses
- [ ] Test 10 events variés
- [ ] Validation JSON structure
- [ ] Test fallback provider si primary fail
- [ ] Test calibration

---

### JOUR 19-21 : Plan Builder

#### Tâche 3.7 : Catalyst Calendar Integration
- [ ] Créer `src/knowledge/calendar.py`
- [ ] API Trading Economics (gratuit)
- [ ] Earnings dates via yfinance
- [ ] Fed meetings (hardcodé + API)
- [ ] Stocker dans PostgreSQL (`catalysts` table)
- [ ] Fonction `get_upcoming_catalysts(ticker, days=7)`

#### Tâche 3.8 : Market Regime Detector
- [ ] Créer `src/strategy/regime_detector.py`
- [ ] Calculer :
  - [ ] VIX actuel
  - [ ] SPY return 5D
  - [ ] SPY volatility 30D
- [ ] Classifier :
  ```python
  if vix > 35: return "FLASH_CRASH"
  elif vix < 12 and vol < 0.005: return "LOW_VOL_GRIND"
  elif vix > 25 and ret_5d < -0.01: return "TRENDING_BEAR"
  elif vix < 15 and ret_5d > 0.01: return "TRENDING_BULL"
  else: return "VOLATILE_RANGE"
  ```
- [ ] Cacher dans Redis (update toutes les 5 min)

#### Tâche 3.9 : Scenario Schema
- [ ] Créer `src/agents/schemas.py` (ajouter) :
  ```python
  class Scenario(BaseModel):
      scenario_id: str
      ticker: str
      name: str
      version: str
      bias: str  # bullish/bearish/neutral
      probability: float
      entry_conditions: List[str]
      invalidation_triggers: List[str]
      targets: dict
      size_max_pct: float
      time_horizon: str
      reassess_if: List[str]
      reasoning: List[str]
      catalysts_pending: List[dict]
  ```

#### Tâche 3.10 : Prompt Template Scenario
- [ ] Créer `src/agents/prompts/scenario_prompt.txt`
- [ ] Input : NewsCards 24h, OHLCV 90D, Catalysts, Regime
- [ ] Output : 3 scénarios (bullish/neutral/bearish)
- [ ] JSON strict

#### Tâche 3.11 : Plan Builder Core
- [ ] Créer `src/agents/plan_builder.py`
- [ ] Trigger : Cron 04:00 ET
- [ ] Pour chaque ticker watchlist :
  - [ ] Charger NewsCards depuis 20:00 veille
  - [ ] Charger OHLCV 90D
  - [ ] Charger catalysts proches
  - [ ] Get market regime
  - [ ] Appel LLM (Opus/o1)
  - [ ] Parse scenarios
  - [ ] Stockage PostgreSQL + MinIO
- [ ] Génération watchlist dynamique (top 20)

#### Tâche 3.12 : Scenario Updater
- [ ] Créer `src/agents/scenario_updater.py`
- [ ] Trigger : 11:30, 13:30, 15:30 ET
- [ ] Pour chaque ticker avec position OU scénario actif :
  - [ ] Charger dernières 2h données
  - [ ] Re-run prompt (Sonnet)
  - [ ] Update scénarios (version++)
  - [ ] Mark old version superseded
- [ ] Métriques (scenarios_updated, cost)

#### Tâche 3.13 : Tests Plan Builder
- [ ] Mock NewsCards (10 pour AAPL)
- [ ] Mock OHLCV historique
- [ ] Test génération 3 scénarios
- [ ] Validation structure JSON
- [ ] Test catalyst injection

---

### JOUR 22-28 : Decision Engine (LangGraph)

#### Tâche 3.14 : LangGraph Workflow Setup
- [ ] Créer `src/agents/decision_engine.py`
- [ ] Définir StateGraph :
  ```python
  from langgraph.graph import StateGraph
  
  workflow = StateGraph(DecisionState)
  workflow.add_node("load_context", load_context_node)
  workflow.add_node("match_scenarios", match_scenarios_node)
  workflow.add_node("evaluate_confidence", evaluate_confidence_node)
  workflow.add_node("web_research", web_research_node)
  workflow.add_node("decide", decide_node)
  workflow.add_node("risk_soft", risk_soft_node)
  
  workflow.set_entry_point("load_context")
  workflow.add_edge("load_context", "match_scenarios")
  workflow.add_conditional_edges(
      "evaluate_confidence",
      route_by_confidence,
      {"low": "web_research", "medium": "decide", "high": "decide"}
  )
  ```

#### Tâche 3.15 : Node: Load Context
- [ ] Fonction `load_context_node(state)`
- [ ] Charger :
  - [ ] NewsCards (fenêtre 2h)
  - [ ] Scenarios actifs
  - [ ] OHLCV (1D + 5D)
  - [ ] Positions actuelles
  - [ ] Risk limits
- [ ] Return updated state

#### Tâche 3.16 : Node: Match Scenarios
- [ ] Fonction `match_scenarios_node(state)`
- [ ] Pour chaque scénario :
  - [ ] Vérifier entry_conditions
  - [ ] Calculer match_score (0-100)
- [ ] Garder top 2 scénarios
- [ ] Update state

#### Tâche 3.17 : Node: Evaluate Confidence
- [ ] Fonction `evaluate_confidence_node(state)`
- [ ] Agrège :
  - [ ] match_score scenarios
  - [ ] NewsCard.confidence (calibrée)
  - [ ] Technical confirmation (RSI, MACD)
- [ ] Output : confidence finale (0-1)

#### Tâche 3.18 : Node: Web Research (optionnel)
- [ ] Créer `src/agents/web_researcher.py`
- [ ] Tavily API ou Perplexity
- [ ] Budget : 20 calls/jour max
- [ ] Timeout : 15s
- [ ] Return : sources + extraits

#### Tâche 3.19 : Node: Decide
- [ ] Fonction `decide_node(state)`
- [ ] Prompt LLM (Sonnet/GPT-4o) :
  - [ ] Input : full context
  - [ ] Output : Signal JSON
    ```json
    {
      "action": "BUY|SELL|HOLD",
      "confidence": 0.78,
      "reasoning": [...],
      "plan": {
        "order_type": "LIMIT",
        "quantity": 10,
        "limit_price": 185.5,
        "stop_loss": 182.0,
        "take_profit": [189.0, 192.0]
      }
    }
    ```

#### Tâche 3.20 : Node: Risk Soft Gate
- [ ] Fonction `risk_soft_node(state)`
- [ ] Vérifier overrides IA :
  - [ ] Stop ajustement dans ±20%
  - [ ] Hold malgré drawdown < 2.5%
- [ ] Logger tous overrides
- [ ] Return approved/rejected

#### Tâche 3.21 : Decision Engine Orchestration
- [ ] Consumer Kafka : `newscards.v1` (pour positions held)
- [ ] Consumer Kafka : `alerts.priority.v1` (pour réévaluations)
- [ ] Pour chaque trigger :
  - [ ] Run LangGraph workflow
  - [ ] Publier Signal vers `signals.final.v1`
- [ ] Métriques (decisions/hour, latency, cost)

#### Tâche 3.22 : Tests Decision Engine
- [ ] Mock context complet
- [ ] Test workflow end-to-end
- [ ] Test routing confidence (low/medium/high)
- [ ] Test web research trigger
- [ ] Validation Signal output

---

## 🛡️ PHASE 4 : RISK & EXECUTION (Semaine 5 - Jours 29-35)

### JOUR 29-31 : Risk Management

#### Tâche 4.1 : Risk Gate Hard
- [ ] Créer `src/execution/risk_gate.py`
- [ ] Config `config/risk_limits.yaml` :
  ```yaml
  hard_limits:
    max_position_pct: 0.10
    max_daily_loss_pct: 0.03
    max_drawdown_pct: 0.15
    max_open_positions: 5
    max_trades_per_day: 10
    stop_loss_required: true
    halt_if_vix_above: 40
  ```
- [ ] Function `check_hard_limits(signal, portfolio)` :
  - [ ] Return GO | REJECT + reason
  - [ ] Aucune exception possible
  - [ ] Log violations

#### Tâche 4.2 : Correlation Guardian
- [ ] Créer `src/strategy/correlation_guardian.py`
- [ ] Calculer matrice corrélation rolling 30D
- [ ] Stocker dans Redis (update 1x/heure)
- [ ] Function `check_correlation(new_ticker, held_positions)` :
  - [ ] Si corr > 0.7 : REDUCE size 50%
  - [ ] Si 2+ positions corrélées : REJECT
- [ ] Alert si "correlation creep" détecté

#### Tâche 4.3 : Pre-Flight Check
- [ ] Créer `src/execution/preflight.py`
- [ ] Checks :
  ```python
  def preflight_check(signal):
      checks = []
      
      # Catalyst imminent ?
      if catalyst_within_minutes(signal.ticker, 30):
          return ABORT
      
      # Correlation OK ?
      corr = max_correlation(signal.ticker)
      if corr > 0.7:
          signal.quantity *= 0.5
          checks.append(WARN("Correlation high"))
      
      # Régime OK ?
      if get_regime() == "FLASH_CRASH":
          return ABORT
      
      # Liquidité OK ?
      if get_volume(signal.ticker) < 500_000:
          return ABORT
      
      # Spread OK ?
      if get_spread(signal.ticker) > 0.005:
          return WAIT
      
      return GO(checks)
  ```

#### Tâche 4.4 : Tests Risk Management
- [ ] Test hard limits (position size, daily loss, etc.)
- [ ] Test correlation checks
- [ ] Test preflight avec scenarios variés
- [ ] Valider aucun bypass possible

---

### JOUR 32-35 : Execution Layer

#### Tâche 4.5 : Interactive Brokers Setup
- [ ] Installer IB Gateway ou TWS
- [ ] Configuration paper trading :
  - [ ] Port 4002
  - [ ] Enable API connections
  - [ ] Client ID : 1
- [ ] Test connexion : `ib-insync`

#### Tâche 4.6 : Execution Adapter
- [ ] Créer `src/execution/ibkr_adapter.py`
- [ ] Consumer Kafka : `signals.final.v1`
- [ ] Pour chaque signal :
  - [ ] Re-check