"""
AI Activity Monitor - Real-time Dashboard
FastAPI backend for monitoring LLM activity in real-time
"""

import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any
from collections import deque
from dataclasses import dataclass, asdict
from enum import Enum

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


# ============================================================================
# Activity Tracking
# ============================================================================

class ActivityType(str, Enum):
    """Type of AI activity"""
    COMPLETION_START = "completion_start"
    COMPLETION_SUCCESS = "completion_success"
    COMPLETION_ERROR = "completion_error"
    RETRY = "retry"
    RATE_LIMIT = "rate_limit"


@dataclass
class AIActivity:
    """Single AI activity event"""
    timestamp: datetime
    activity_type: ActivityType
    provider: str
    model: str
    tier: str
    event_id: str
    prompt_preview: str  # First 100 chars
    response_preview: str = ""  # First 200 chars
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    error_msg: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['activity_type'] = self.activity_type.value
        return data


class ActivityMonitor:
    """
    Global activity monitor
    Tracks all AI interactions in real-time
    """
    
    def __init__(self, max_history: int = 1000):
        self.activities: deque = deque(maxlen=max_history)
        self.stats = {
            "total_completions": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "completions_by_model": {},
            "errors_count": 0,
        }
        self.websocket_clients: List[WebSocket] = []
    
    def log_activity(self, activity: AIActivity):
        """Log a new activity"""
        self.activities.append(activity)
        
        # Update stats
        if activity.activity_type == ActivityType.COMPLETION_SUCCESS:
            self.stats["total_completions"] += 1
            self.stats["total_tokens"] += activity.tokens_in + activity.tokens_out
            self.stats["total_cost_usd"] += activity.cost_usd
            
            model_key = f"{activity.provider}:{activity.model}"
            self.stats["completions_by_model"][model_key] = \
                self.stats["completions_by_model"].get(model_key, 0) + 1
        
        elif activity.activity_type == ActivityType.COMPLETION_ERROR:
            self.stats["errors_count"] += 1
        
        # Broadcast to WebSocket clients
        asyncio.create_task(self.broadcast(activity))
    
    async def broadcast(self, activity: AIActivity):
        """Broadcast activity to all connected WebSocket clients"""
        if not self.websocket_clients:
            return
        
        message = json.dumps(activity.to_dict())
        disconnected = []
        
        for client in self.websocket_clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.append(client)
        
        # Clean up disconnected clients
        for client in disconnected:
            self.websocket_clients.remove(client)
    
    def get_recent_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent activities"""
        return [activity.to_dict() for activity in list(self.activities)[-limit:]]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return self.stats.copy()


# Global monitor instance
monitor = ActivityMonitor()


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="AI Activity Monitor - Claude",
    description="Surveillance en temps réel des interactions avec Claude",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def dashboard():
    """Serve the dashboard HTML"""
    return HTMLResponse(content=HTML_DASHBOARD)


@app.get("/api/activities")
async def get_activities(limit: int = 50):
    """Get recent activities"""
    return {
        "activities": monitor.get_recent_activities(limit),
        "stats": monitor.get_stats()
    }


@app.get("/api/stats")
async def get_stats():
    """Get statistics only"""
    return monitor.get_stats()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    monitor.websocket_clients.append(websocket)
    
    try:
        # Send initial data
        await websocket.send_text(json.dumps({
            "type": "init",
            "activities": monitor.get_recent_activities(20),
            "stats": monitor.get_stats()
        }))
        
        # Keep connection alive
        while True:
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    
    except WebSocketDisconnect:
        monitor.websocket_clients.remove(websocket)


# ============================================================================
# HTML Dashboard
# ============================================================================

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 Claude AI Monitor - Trading Platform</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            padding: 20px;
        }
        
        .container { max-width: 1600px; margin: 0 auto; }
        
        header { text-align: center; margin-bottom: 30px; }
        
        h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .status {
            display: inline-block;
            padding: 8px 16px;
            background: rgba(0, 255, 0, 0.2);
            border-radius: 20px;
            font-size: 0.9rem;
        }
        
        .status.connected::before { content: '🟢 '; }
        .status.disconnected::before { content: '🔴 '; }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .stat-card h3 {
            font-size: 0.9rem;
            opacity: 0.8;
            margin-bottom: 10px;
        }
        
        .stat-card .value {
            font-size: 2rem;
            font-weight: bold;
        }
        
        .activity-feed {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            max-height: 600px;
            overflow-y: auto;
        }
        
        .activity-feed h2 {
            margin-bottom: 20px;
            font-size: 1.5rem;
        }
        
        .activity-item {
            background: rgba(0, 0, 0, 0.2);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 10px;
            border-left: 4px solid;
            animation: slideIn 0.3s ease-out;
        }
        
        @keyframes slideIn {
            from { opacity: 0; transform: translateX(-20px); }
            to { opacity: 1; transform: translateX(0); }
        }
        
        .activity-item.success { border-left-color: #10b981; }
        .activity-item.error { border-left-color: #ef4444; }
        .activity-item.start { border-left-color: #3b82f6; }
        
        .activity-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .activity-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: bold;
        }
        
        .badge-haiku { background: #8b5cf6; }
        .badge-sonnet { background: #06b6d4; }
        
        .activity-time {
            font-size: 0.85rem;
            opacity: 0.7;
        }
        
        .activity-details {
            font-size: 0.9rem;
            line-height: 1.6;
        }
        
        .prompt-preview {
            background: rgba(0, 0, 0, 0.3);
            padding: 10px;
            border-radius: 8px;
            margin-top: 10px;
            font-family: 'Courier New', monospace;
            font-size: 0.85rem;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .metrics-row {
            display: flex;
            gap: 15px;
            margin-top: 8px;
            flex-wrap: wrap;
        }
        
        .metric {
            background: rgba(255, 255, 255, 0.1);
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 0.8rem;
        }
        
        .error-message {
            color: #fca5a5;
            margin-top: 8px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 Claude AI Monitor</h1>
            <p style="opacity: 0.8; margin-bottom: 15px;">Surveillance en temps réel des interactions Claude</p>
            <div class="status" id="status">Connecting...</div>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Completions</h3>
                <div class="value" id="total-completions">0</div>
            </div>
            <div class="stat-card">
                <h3>Total Tokens</h3>
                <div class="value" id="total-tokens">0</div>
            </div>
            <div class="stat-card">
                <h3>Total Cost</h3>
                <div class="value" id="total-cost">$0.00</div>
            </div>
            <div class="stat-card">
                <h3>Errors</h3>
                <div class="value" id="errors">0</div>
            </div>
        </div>
        
        <div class="activity-feed">
            <h2>📊 Activité en Temps Réel</h2>
            <div id="activities"></div>
        </div>
    </div>
    
    <script>
        let ws;
        
        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
            ws.onopen = () => {
                console.log('WebSocket connected');
                document.getElementById('status').className = 'status connected';
                document.getElementById('status').textContent = 'Connected';
            };
            
            ws.onclose = () => {
                console.log('WebSocket disconnected');
                document.getElementById('status').className = 'status disconnected';
                document.getElementById('status').textContent = 'Disconnected';
                setTimeout(connect, 5000);
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'init') {
                    updateStats(data.stats);
                    data.activities.reverse().forEach(activity => addActivity(activity));
                } else if (data.type !== 'ping') {
                    addActivity(data);
                    updateStatsFromActivity(data);
                }
            };
        }
        
        function updateStats(stats) {
            document.getElementById('total-completions').textContent = stats.total_completions.toLocaleString();
            document.getElementById('total-tokens').textContent = stats.total_tokens.toLocaleString();
            document.getElementById('total-cost').textContent = '$' + stats.total_cost_usd.toFixed(4);
            document.getElementById('errors').textContent = stats.errors_count.toLocaleString();
        }
        
        function updateStatsFromActivity(activity) {
            if (activity.activity_type === 'completion_success') {
                const completions = parseInt(document.getElementById('total-completions').textContent.replace(/,/g, '')) || 0;
                const tokens = parseInt(document.getElementById('total-tokens').textContent.replace(/,/g, '')) || 0;
                const cost = parseFloat(document.getElementById('total-cost').textContent.replace('$', '')) || 0;
                
                document.getElementById('total-completions').textContent = (completions + 1).toLocaleString();
                document.getElementById('total-tokens').textContent = (tokens + activity.tokens_in + activity.tokens_out).toLocaleString();
                document.getElementById('total-cost').textContent = '$' + (cost + activity.cost_usd).toFixed(4);
            } else if (activity.activity_type === 'completion_error') {
                const errors = parseInt(document.getElementById('errors').textContent.replace(/,/g, '')) || 0;
                document.getElementById('errors').textContent = (errors + 1).toLocaleString();
            }
        }
        
        function addActivity(activity) {
            const container = document.getElementById('activities');
            const item = document.createElement('div');
            
            let className = 'activity-item';
            if (activity.activity_type === 'completion_success') className += ' success';
            else if (activity.activity_type === 'completion_error') className += ' error';
            else if (activity.activity_type === 'completion_start') className += ' start';
            
            item.className = className;
            
            const modelBadge = activity.model.includes('haiku') ? 'haiku' : 'sonnet';
            const time = new Date(activity.timestamp).toLocaleTimeString('fr-FR');
            
            let html = `
                <div class="activity-header">
                    <div>
                        <span class="activity-badge badge-${modelBadge}">${activity.model}</span>
                        <span style="opacity: 0.7; margin-left: 10px;">${activity.tier}</span>
                    </div>
                    <div class="activity-time">${time}</div>
                </div>
                <div class="activity-details">
                    <div><strong>Event:</strong> ${activity.event_id}</div>
            `;
            
            if (activity.activity_type === 'completion_success') {
                html += `
                    <div class="metrics-row">
                        <div class="metric">📥 ${activity.tokens_in} tokens</div>
                        <div class="metric">📤 ${activity.tokens_out} tokens</div>
                        <div class="metric">💰 $${activity.cost_usd.toFixed(4)}</div>
                        <div class="metric">⏱️ ${activity.latency_ms}ms</div>
                    </div>
                    <div class="prompt-preview">Prompt: ${escapeHtml(activity.prompt_preview)}</div>
                `;
                if (activity.response_preview) {
                    html += `<div class="prompt-preview">Response: ${escapeHtml(activity.response_preview)}</div>`;
                }
            } else if (activity.activity_type === 'completion_error') {
                html += `<div class="error-message">❌ ${escapeHtml(activity.error_msg)}</div>`;
            }
            
            html += '</div>';
            item.innerHTML = html;
            
            container.insertBefore(item, container.firstChild);
            
            // Keep only last 50
            while (container.children.length > 50) {
                container.removeChild(container.lastChild);
            }
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        connect();
    </script>
</body>
</html>
"""


def run_monitor(host: str = "0.0.0.0", port: int = 8010):
    """Run the monitoring dashboard"""
    print("=" * 60)
    print("🤖 Claude AI Activity Monitor")
    print("=" * 60)
    print(f"\n📊 Dashboard: http://localhost:{port}")
    print(f"📡 API:       http://localhost:{port}/api/activities")
    print(f"📈 Stats:     http://localhost:{port}/api/stats")
    print("\n" + "=" * 60 + "\n")
    
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_monitor()
