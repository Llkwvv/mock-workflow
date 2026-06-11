"""WebSocket endpoint for conversational mock data generation."""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from backend.agent.chat import chat_message
from backend.config import get_settings


async def chat_websocket(websocket: WebSocket):
    await websocket.accept()
    history: list[dict[str, str]] = []
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            user_message = payload.get("message", "")
            if not user_message:
                await websocket.send_json({"type": "error", "message": "Empty message"})
                continue

            settings = get_settings()
            result = chat_message(history, user_message, settings)

            # Update history
            history.append({"role": "user", "content": user_message})
            if result.get("action") == "chat":
                history.append({"role": "assistant", "content": result.get("message", "")})
            else:
                history.append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})

            await websocket.send_json({"type": "response", "data": result})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close()
