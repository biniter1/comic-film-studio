import asyncio
from typing import Any


class EventBus:
    """Thread-safe SSE event bus using the main event loop.

    On startup, call `bind_loop(asyncio.get_running_loop())` from within the
    async lifespan so that `publish_threadsafe` can be called from any thread
    (e.g. FastAPI `def` endpoints running in threadpool workers).
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the main event loop for cross-thread publishing."""
        self._loop = loop

    # ------------------------------------------------------------------
    # Internal helper — must be called from the loop thread
    # ------------------------------------------------------------------
    def _publish_sync(self, event_type: str, data: dict[str, Any]) -> None:
        message = {"event": event_type, "data": data}
        for q in list(self._subscribers):
            try:
                q.put_nowait(message)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Async publish (call from async context inside the loop)
    # ------------------------------------------------------------------
    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        self._publish_sync(event_type, data)

    # ------------------------------------------------------------------
    # Thread-safe publish (call from ANY thread, including threadpool workers)
    # ------------------------------------------------------------------
    def publish_threadsafe(self, event_type: str, data: dict[str, Any]) -> None:
        """Schedule a publish on the main loop from any thread."""
        if self._loop is None or self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._publish_sync, event_type, data)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)


event_bus = EventBus()
