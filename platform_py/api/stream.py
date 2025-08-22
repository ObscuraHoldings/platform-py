"""
WebSocket gateway: ephemeral subscription bridge from NATS subjects to clients.
"""

import asyncio
import json
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services import services

router = APIRouter(prefix="/stream", tags=["Stream"])


@router.websocket("")
async def stream(ws: WebSocket):
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=1024)

    async def make_handler():
        async def handler(evt: dict):
            try:
                data = json.dumps(evt)
                try:
                    queue.put_nowait(data)
                except asyncio.QueueFull:
                    # Drop when overloaded (best effort for UI)
                    pass
            except Exception:
                pass
        return handler

    subs = []
    try:
        # Expect initial subscribe message
        sub_msg = await ws.receive_text()
        req = json.loads(sub_msg)
        topics: List[str] = req.get("topics", ["intent.*", "plan.*", "exec.*"])  # defaults
        handler = await make_handler()
        for subject in topics:
            await services.event_stream.subscribe(subject, handler)
            subs.append(subject)

        # Flush loop
        while True:
            data = await queue.get()
            await ws.send_text(data)
    except WebSocketDisconnect:
        return
    except Exception:
        return
