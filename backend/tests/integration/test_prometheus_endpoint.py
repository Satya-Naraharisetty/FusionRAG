import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "METRICS_BEARER_TOKEN", None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Trigger an endpoint to record request metrics
        health_resp = await client.get("/api/v1/health/liveness")
        assert health_resp.status_code == 200

        # Scrape metrics
        metrics_resp = await client.get("/metrics")
        assert metrics_resp.status_code == 200
        assert "text/plain" in metrics_resp.headers.get("content-type", "")

        body = metrics_resp.text
        assert "http_server_requests_total" in body
        assert "http_server_duration_seconds" in body


@pytest.mark.asyncio
async def test_metrics_endpoint_micro_caching(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "METRICS_BEARER_TOKEN", None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp1 = await client.get("/metrics")
        assert resp1.status_code == 200
        resp2 = await client.get("/metrics")
        assert resp2.status_code == 200
        assert resp1.text == resp2.text


@pytest.mark.asyncio
async def test_metrics_bearer_token_authorization(monkeypatch):
    from app.core.config import settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. When METRICS_BEARER_TOKEN is configured
        monkeypatch.setattr(
            settings, "METRICS_BEARER_TOKEN", "super-secret-metrics-token-123"
        )

        # Missing token -> 401
        res_missing = await client.get("/metrics")
        assert res_missing.status_code == 401
        assert "WWW-Authenticate" in res_missing.headers

        # Invalid token -> 401
        res_invalid = await client.get(
            "/metrics", headers={"Authorization": "Bearer wrong-token"}
        )
        assert res_invalid.status_code == 401

        # Valid token -> 200
        res_valid = await client.get(
            "/metrics",
            headers={"Authorization": "Bearer super-secret-metrics-token-123"},
        )
        assert res_valid.status_code == 200
        assert "http_server_requests_total" in res_valid.text

        # 2. When METRICS_BEARER_TOKEN is None (open access)
        monkeypatch.setattr(settings, "METRICS_BEARER_TOKEN", None)
        res_open = await client.get("/metrics")
        assert res_open.status_code == 200
