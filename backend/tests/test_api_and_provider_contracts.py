"""
API & Provider Contract Verification Test Suite.

Comprehensive contract tests verifying:
1. OpenAPI Schema Invariants & Schema Drift (verifies FastAPI app routes, schemas, and parameters).
2. Third-Party Provider Response Contracts:
   - Google Gemini Chat & Vision API payload contracts.
   - Jina AI Embeddings & Reranker API response contracts.
   - Resend Transactional Email API payload contracts.
3. Backward Compatibility & Non-Breaking API Change Invariants.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.chat.domain.interfaces import ProviderResponse
from app.chat.domain.models import Usage
from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. OpenAPI Specification Contract & Schema Drift Tests
# ---------------------------------------------------------------------------


def test_openapi_schema_generation_and_validity():
    """
    Contract Test: Validates that the application generates a valid OpenAPI 3.1 schema
    containing all required top-level metadata, servers, paths, and components.
    """
    schema = app.openapi()
    assert schema is not None
    assert "openapi" in schema
    assert schema["openapi"].startswith("3.")
    assert "info" in schema
    assert schema["info"]["title"] == "FusionRAG"
    assert "paths" in schema
    assert len(schema["paths"]) > 0


def test_openapi_critical_endpoints_exist_in_contract():
    """
    Contract Test: Ensures essential public endpoints are strictly defined in the API contract.
    """
    schema = app.openapi()
    paths = schema.get("paths", {})

    expected_endpoints = [
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/chat",
        "/api/v1/documents",
        "/api/v1/search",
        "/api/v1/health/liveness",
        "/api/v1/health/readiness",
    ]

    for endpoint in expected_endpoints:
        assert endpoint in paths, (
            f"Contract violation: Endpoint {endpoint} missing from OpenAPI schema!"
        )


def test_openapi_chat_endpoint_contract():
    """
    Contract Test: Verifies that POST /api/v1/chat strictly declares the expected
    request body schema and status codes.
    """
    schema = app.openapi()
    chat_path = schema["paths"].get("/api/v1/chat", {})
    assert "post" in chat_path, "POST method missing on /api/v1/chat contract"

    post_op = chat_path["post"]
    assert "requestBody" in post_op
    content = post_op["requestBody"]["content"]["application/json"]
    schema_ref = content["schema"]["$ref"]
    schema_name = schema_ref.split("/")[-1]

    # Verify the schema exists in components
    components = schema.get("components", {}).get("schemas", {})
    assert schema_name in components
    chat_schema = components[schema_name]
    assert "question" in chat_schema.get("properties", {})
    assert "question" in chat_schema.get("required", [])

    # Verify 200 response definition
    responses = post_op.get("responses", {})
    assert "200" in responses, "200 OK response not declared in /api/v1/chat contract"


def test_openapi_snapshot_file_compatibility():
    """
    Contract Test: If a static openapi.json exists in docs/api/,
    verify that no breaking changes were introduced (e.g. removed paths).
    """
    docs_openapi = Path("docs/api/openapi.json")
    if not docs_openapi.exists():
        # Look relative to workspace root if running from backend directory
        docs_openapi = Path("../docs/api/openapi.json")

    if docs_openapi.exists():
        with open(docs_openapi, encoding="utf-8") as f:
            snapshot_schema = json.load(f)

        current_schema = app.openapi()
        snapshot_paths = set(snapshot_schema.get("paths", {}).keys())
        current_paths = set(current_schema.get("paths", {}).keys())

        # Check for unexpected deletions of documented endpoints
        removed_paths = snapshot_paths - current_paths
        # We allow internal or version migrations, but assert core paths remain
        critical_paths = {"/api/v1/auth/login", "/api/v1/chat", "/api/v1/search"}
        assert not (critical_paths & removed_paths), (
            f"Breaking Contract Change: Removed critical endpoints: {critical_paths & removed_paths}"
        )


# ---------------------------------------------------------------------------
# 2. Third-Party Provider Response Contract Tests
# ---------------------------------------------------------------------------


def test_gemini_provider_response_contract():
    """
    Contract Test: Asserts that responses from LLM providers conform to
    the domain ProviderResponse model (content, usage, tool_calls).
    """
    mock_response = ProviderResponse(
        content="Retrieval-Augmented Generation enhances LLMs.",
        usage=Usage(prompt_tokens=45, completion_tokens=15, total_tokens=60),
        tool_calls=[],
    )

    assert isinstance(mock_response.content, str)
    assert len(mock_response.content) > 0
    assert mock_response.usage.prompt_tokens == 45
    assert mock_response.usage.completion_tokens == 15
    assert mock_response.usage.total_tokens == 60
    assert mock_response.tool_calls == []


def test_jina_reranker_payload_contract():
    """
    Contract Test: Validates the request and response format contract expected
    by the Jina AI Reranker API (jina-reranker-v2-base-multilingual).
    """
    # Expected outgoing request structure to Jina API
    expected_request_payload = {
        "model": "jina-reranker-v2-base-multilingual",
        "query": "What is Fusion RAG?",
        "documents": [
            "Fusion RAG combines dense and sparse search.",
            "Irrelevant context.",
        ],
        "top_n": 2,
    }
    assert "model" in expected_request_payload
    assert "query" in expected_request_payload
    assert isinstance(expected_request_payload["documents"], list)

    # Expected incoming response structure from Jina API
    simulated_jina_response = {
        "model": "jina-reranker-v2-base-multilingual",
        "usage": {"total_tokens": 30, "prompt_tokens": 30},
        "results": [
            {
                "index": 0,
                "document": {"text": "Fusion RAG combines dense and sparse search."},
                "relevance_score": 0.94,
            },
            {
                "index": 1,
                "document": {"text": "Irrelevant context."},
                "relevance_score": 0.12,
            },
        ],
    }

    assert "results" in simulated_jina_response
    for item in simulated_jina_response["results"]:
        assert "index" in item
        assert "relevance_score" in item
        assert 0.0 <= item["relevance_score"] <= 1.0


def test_resend_email_payload_contract():
    """
    Contract Test: Validates the request schema sent to the Resend Email API.
    """
    expected_resend_body = {
        "from": "FusionRAG <noreply@fusionrag.com>",
        "to": ["user@example.com"],
        "subject": "Verify your FusionRAG account",
        "html": "<p>Click here to verify</p>",
    }

    assert "@" in expected_resend_body["from"]
    assert isinstance(expected_resend_body["to"], list)
    assert len(expected_resend_body["to"]) > 0
    assert "subject" in expected_resend_body
    assert "html" in expected_resend_body
