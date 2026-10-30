"""WebSocket endpoint and log broadcast manager for real-time frontend telemetry."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("arrclean.api.websocket")

router = APIRouter()

_SCRUB_PATTERNS = [
    re.compile(r"(apikey|api_key|token|password|secret|X-Gotify-Key)=([a-zA-Z0-9_\-\.]+)", re.IGNORECASE),
    re.compile(r"(X-Plex-Token|X-Api-Key|X-Gotify-Key):\s*([a-zA-Z0-9_\-\.]+)", re.IGNORECASE),
]


def scrub_sensitive_tokens(message: str) -> str:
    """Mask sensitive API keys and tokens from log messages."""
    result = message
    for pat in _SCRUB_PATTERNS:
        result = pat.sub(r"\1=••••••••", result)
    return result


class WebSocketLogManager:
    """Manages active WebSocket connections and broadcasts log events to connected clients."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self.log_history: list[dict[str, Any]] = []
        self._max_history = 200

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send buffered recent history
        for msg in self.log_history:
            try:
                await websocket.send_text(json.dumps(msg))
            except Exception:
                break

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.log_history.append(message)
        if len(self.log_history) > self._max_history:
            self.log_history.pop(0)

        dead_connections: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


ws_log_manager = WebSocketLogManager()


class BroadcastLogHandler(logging.Handler):
    """Logging handler that pipes log records into the WebSocketLogManager."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == "arrclean.api.websocket":
            return
        try:
            raw_msg = record.getMessage()
            clean_msg = scrub_sensitive_tokens(raw_msg)
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": clean_msg,
            }
            # Attempt to schedule broadcast in current running loop if available
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            if loop and loop.is_running():
                try:
                    loop.create_task(ws_log_manager.broadcast(log_entry))
                except RuntimeError:
                    asyncio.run_coroutine_threadsafe(ws_log_manager.broadcast(log_entry), loop)
        except Exception:
            self.handleError(record)


@router.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket) -> None:
    """Stream real-time log messages to connected clients."""
    await ws_log_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; accept any client pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_log_manager.disconnect(websocket)
    except Exception:
        ws_log_manager.disconnect(websocket)
