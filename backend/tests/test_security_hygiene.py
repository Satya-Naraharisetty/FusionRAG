import os
import re

import pytest

from app.core.config import ConfigurationError, Settings


def test_env_example_not_ignored():
    """
    Ensure .env.example files exist and are not accidentally ignored or missing.
    """
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    backend_example = os.path.join(root_dir, "backend", ".env.example")
    frontend_example = os.path.join(root_dir, "frontend", ".env.example")

    assert os.path.exists(backend_example), "backend/.env.example is missing"
    assert os.path.exists(frontend_example), "frontend/.env.example is missing"

    # Verify backend/.env.example contains only placeholders, no real secrets
    with open(backend_example, encoding="utf-8") as f:
        content = f.read()
        # Verify no actual Gemini key
        assert not re.search(r"GEMINI_API_KEY=AIzaSy", content), (
            "backend/.env.example contains a real-looking Gemini key"
        )
        # Verify no actual OpenAI key
        assert not re.search(r"OPENAI_API_KEY=sk-", content), (
            "backend/.env.example contains a real-looking OpenAI key"
        )
        # Verify standard secret placeholders are safe
        assert "super_secure_random" not in content, (
            "backend/.env.example contains development signing key string"
        )
        assert "postgres_secure_password" not in content, (
            "backend/.env.example contains default database password"
        )


def test_frontend_source_contains_no_private_credentials():
    """
    Scan frontend source files to ensure no private credentials/secrets are hardcoded.
    """
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    frontend_src = os.path.join(root_dir, "frontend", "src")

    # Common secret patterns
    secret_patterns = [
        re.compile(r"AIzaSy[A-Za-z0-9_-]{35}"),  # Google/Gemini API Key
        re.compile(r"sk-proj-[A-Za-z0-9_-]{40,}"),  # OpenAI API Key
        re.compile(r"ghp_[A-Za-z0-9]{36,40}"),  # GitHub Personal Access Token
    ]

    if os.path.exists(frontend_src):
        for root, _, files in os.walk(frontend_src):
            for file in files:
                if file.endswith((".ts", ".tsx", ".js", ".jsx", ".css", ".html")):
                    file_path = os.path.join(root, file)
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        for line_no, line in enumerate(lines, 1):
                            for pattern in secret_patterns:
                                assert not pattern.search(line), (
                                    f"Potential secret found in {file_path}:{line_no}"
                                )


def test_secret_values_not_emitted_by_config_logging_or_errors():
    """
    Ensure secret values are not emitted by config repr/str or validation errors.
    """
    secret_value = "SUPER_SECRET_KEY_THAT_MUST_NEVER_BE_LOGGED_OR_PRINTED_12345"

    # Verify that representation doesn't leak secrets in Settings
    # Create settings in testing env where we can pass custom keys
    settings = Settings(
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_database",
        REDIS_HOST="localhost",
        QDRANT_HOST="localhost",
        JWT_SECRET=secret_value,
        GEMINI_API_KEY=secret_value,
        OPENAI_API_KEY=secret_value,
    )

    repr_str = repr(settings)
    str_str = str(settings)

    assert secret_value not in repr_str, (
        "Settings representation leaks JWT_SECRET or other secrets"
    )
    assert secret_value not in str_str, "Settings string conversion leaks secrets"

    # Verify that validation error message does not leak the invalid secret itself
    # when raising ConfigurationError
    invalid_secret = "my_mock_key_development_secret_leak_test"
    os.environ["ENV"] = "production"
    try:
        with pytest.raises(ConfigurationError) as exc_info:
            Settings(
                POSTGRES_SERVER="localhost",
                POSTGRES_USER="test_user",
                POSTGRES_PASSWORD="test_password",
                POSTGRES_DB="test_database",
                REDIS_HOST="localhost",
                QDRANT_HOST="localhost",
                JWT_SECRET=invalid_secret,
                GEMINI_API_KEY="valid_key",
            )
        assert invalid_secret not in str(exc_info.value), (
            "ConfigurationError message leaks the secret value"
        )
    finally:
        os.environ["ENV"] = "testing"


def test_oauth_configuration_disabled_behaves_correctly():
    """
    Verify that when OAuth is disabled (client ID is empty), client secret is not required.
    """
    # Should build settings successfully without client secrets when client IDs are not configured
    settings = Settings(
        ENV="production",
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_database",
        REDIS_HOST="localhost",
        QDRANT_HOST="localhost",
        JWT_SECRET="a_very_long_secure_secret_signing_key_32_bytes_long",
        GEMINI_API_KEY="valid_key",
        GOOGLE_CLIENT_ID="",
        GOOGLE_CLIENT_SECRET="",
        GITHUB_CLIENT_ID="",
        GITHUB_CLIENT_SECRET="",
    )
    assert settings.GOOGLE_CLIENT_ID == ""
    assert settings.GOOGLE_CLIENT_SECRET == ""
    assert settings.GITHUB_CLIENT_ID == ""
    assert settings.GITHUB_CLIENT_SECRET == ""
