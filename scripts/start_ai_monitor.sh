#!/bin/bash
# Script pour démarrer le dashboard de monitoring IA

echo "=================================================="
echo "🤖 Claude AI Activity Monitor"
echo "=================================================="

cd /home/leox7/trading-platform

# Activer l'environnement virtuel
source venv/bin/activate

# Démarrer le monitoring
python -m src.agents.monitor
