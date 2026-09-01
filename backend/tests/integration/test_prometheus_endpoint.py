import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format():
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
async def test_metrics_endpoint_micro_caching():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp1 = await client.get("/metrics")
        assert resp1.status_code == 200
        resp2 = await client.get("/metrics")
        assert resp2.status_code == 200
        assert resp1.text == resp2.text
