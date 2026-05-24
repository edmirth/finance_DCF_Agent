import asyncio

from backend.system_router import create_system_router


def test_health_check_reports_injected_agent_cache_size():
    router = create_system_router(lambda: 3)
    endpoint = router.routes[0].endpoint

    body = asyncio.run(endpoint())

    assert body["status"] == "healthy"
    assert body["agents_cached"] == 3
    assert "api_keys_configured" in body
