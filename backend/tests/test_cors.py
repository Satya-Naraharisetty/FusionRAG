"""
CORS regression tests.

These pin the CORS behavior for the origins declared in the canonical
BACKEND_CORS_ORIGINS list (see app/core/config.py). If a preflight from the
Vite dev server or the dockerized frontend stops returning the expected
headers, the browser silently blocks all API traffic - so this is a
high-value regression surface.
"""

from fastapi import status
from httpx import Response


def _preflight(client, origin: str, method: str = "POST") -> Response:
    """Send a CORS preflight OPTIONS request from the given origin."""
    return client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )


def test_cors_preflight_allows_vite_dev_server(client):
    """
    Asserts a preflight from the Vite dev server (http://localhost:5173) is
    allowed with the exact origin echoed back and credentials enabled.
    """
    response = _preflight(client, "http://localhost:5173")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-headers"] == (
        "content-type,authorization"
    )


def test_cors_preflight_allows_localhost_ip_dev_server(client):
    """
    Asserts a preflight from the Vite dev server via 127.0.0.1 is also allowed.
    """
    response = _preflight(client, "http://127.0.0.1:5173")
    assert response.status_code == status.HTTP_200_OK
    assert (
        response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    )
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_preflight_allows_docker_frontend(client):
    """
    Asserts a preflight from the dockerized frontend origin (http://localhost,
    served on port 80 via nginx) is allowed.
    """
    response = _preflight(client, "http://localhost")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["access-control-allow-origin"] == "http://localhost"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_simple_request_echoes_allow_origin(client):
    """
    Asserts a simple (non-preflight) request from the dev server also receives
    the allow-origin header, so real API traffic is visible to the browser.
    """
    response = client.get(
        "/api/v1/health/liveness",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_preflight_rejects_unknown_origin(client):
    """
    Asserts a preflight from an origin outside the canonical list is rejected.
    Starlette's CORSMiddleware answers disallowed preflights with 400 and no
    access-control-* headers, so the browser blocks the request.
    """
    response = _preflight(client, "http://evil.example.com")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    # The decisive signal: no allow-origin header, so the browser blocks it.
    # (Starlette still attaches generic access-control-allow-credentials and
    # allow-methods to rejected preflights, so those are not asserted here.)
    assert "access-control-allow-origin" not in response.headers
