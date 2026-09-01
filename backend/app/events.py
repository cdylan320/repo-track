from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import Request
from starlette.responses import StreamingResponse


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def publish(self, event: str, data: dict[str, Any] | None = None) -> None:
        payload = {"event": event, "data": data or {}}
        dead: list[asyncio.Queue] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            self.unsubscribe(queue)


bus = EventBus()


def _hello_data() -> dict[str, Any]:
    from .. import github
    from ..database import SessionLocal
    from ..models import Account
    from ..services import git_sync
    from ..services.rate_alerts import bucket_payload

    nxt = git_sync.next_tick_at()
    db = SessionLocal()
    try:
        accounts = db.query(Account).order_by(Account.id.asc()).all()
        buckets, limited = bucket_payload(accounts)
    finally:
        db.close()
    return {
        "next_tick_at": nxt.isoformat() if nxt else None,
        "github_paused_until": github.reset_iso(),
        "github_remaining": github.remaining(),
        "rate_limited_count": limited,
        "github_buckets": buckets,
    }


async def sse_stream(request: Request) -> StreamingResponse:
    queue = bus.subscribe()

    async def generate():
        try:
            yield f"data: {json.dumps({'event': 'hello', 'data': _hello_data()})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"data: {json.dumps(payload, default=str)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def account_payload(account) -> dict[str, Any]:
    return {
        "id": account.id,
        "name": account.name,
        "status": account.status,
        "paused": account.paused,
        "last_error": account.last_error,
        "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
    }
