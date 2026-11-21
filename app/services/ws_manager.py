"""WebSocket connection manager for live logs."""
import asyncio
import json
from datetime import datetime, timezone
from typing import Set, Dict, Any
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            return
        data = json.dumps(message)
        # Copy set to avoid modification during iteration
        connections = list(self.active_connections)
        for connection in connections:
            try:
                await connection.send_text(data)
            except Exception:
                # Remove dead connections
                self.active_connections.discard(connection)

# Global manager instance
manager = ConnectionManager()

async def emit_log(agent: str, method: str, status: str, message: str, level: str = "info", metadata: Dict[str, Any] = None):
    """Emit a high-level log event to all connected WebSocket clients."""
    payload = {
        "type": "log",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "method": method,
        "status": status,
        "level": level,
        "message": message,
        "metadata": metadata or {}
    }
    await manager.broadcast(payload)
