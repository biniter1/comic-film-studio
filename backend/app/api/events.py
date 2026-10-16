import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any, Optional

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.jobs.event_bus import event_bus

router = APIRouter(tags=["events"])


@router.get("/events")
async def sse_events(request: Request, chapter_id: Optional[str] = None) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[dict[str, Any], None]:
        q = event_bus.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Timeout after 15 seconds to send heartbeat comment
                    item = await asyncio.wait_for(q.get(), timeout=15.0)
                    data_str = json.dumps(item["data"], ensure_ascii=False)
                    yield {
                        "event": item["event"],
                        "data": data_str,
                    }
                except asyncio.TimeoutError:
                    yield {
                        "comment": "heartbeat",
                    }
        finally:
            event_bus.unsubscribe(q)

    return EventSourceResponse(event_generator())
