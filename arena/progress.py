"""
Arena progress emitter.

Provides a thread-local queue so arena LangGraph nodes can emit SSE events
to the frontend without the arena graph itself knowing about HTTP infrastructure.

Usage inside any arena node / agent function:
    from arena.progress import emit_arena_event
    emit_arena_event({"type": "arena_agent_done", "agent": "fundamental", ...})

The queue is set by ArenaAgent.analyze() before the graph runs and cleared after.
"""
from __future__ import annotations
import asyncio
import threading
from typing import Any, Optional

_local = threading.local()


def set_arena_queue(queue: Optional[asyncio.Queue], loop: Optional[asyncio.AbstractEventLoop]) -> None:
    _local.queue = queue
    _local.loop = loop


def clear_arena_queue() -> None:
    _local.queue = None
    _local.loop = None


def emit_arena_event(event: dict[str, Any]) -> None:
    """Thread-safe fire-and-forget emit to the SSE queue.  Silently no-ops if no queue is set."""
    queue: Optional[asyncio.Queue] = getattr(_local, "queue", None)
    loop: Optional[asyncio.AbstractEventLoop] = getattr(_local, "loop", None)
    if queue is None or loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)
    except Exception:
        pass
