"""Small async-safe wrappers around blocking HTTP clients."""
from __future__ import annotations

from typing import Any, Dict

import requests
from fastapi.concurrency import run_in_threadpool


def requests_get_json(url: str, *, params: Dict[str, Any], timeout: int = 10) -> Any:
    """Synchronous helper for requests-based JSON APIs."""
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


async def fetch_json(url: str, *, params: Dict[str, Any], timeout: int = 10) -> Any:
    """Run blocking HTTP requests in a threadpool so async endpoints stay responsive."""
    return await run_in_threadpool(requests_get_json, url, params=params, timeout=timeout)
