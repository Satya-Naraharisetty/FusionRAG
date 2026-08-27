from uuid import uuid4

from app.core.telemetry.sanitizer import (
    hash_user_id,
    mask_ip_address,
    sanitize_error_string,
    sanitize_span_attribute,
    sanitize_telemetry_data,
)


def test_hash_user_id():
    uid = uuid4()
    h1 = hash_user_id(uid)
    h2 = hash_user_id(str(uid))
    assert h1 is not None
    assert len(h1) == 16
    assert h1 == h2
    assert hash_user_id(None) is None
    assert hash_user_id("") is None


def test_mask_ip_address():
    assert mask_ip_address("192.168.1.50") == "192.168.1.0/24"
    assert mask_ip_address("10.0.0.1") == "10.0.0.0/24"
    assert mask_ip_address(None) is None


def test_sanitize_error_string_redactions():
    raw_err = "Failed with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and password='SuperSecret123'"
    sanitized = sanitize_error_string(raw_err)
    assert "SuperSecret123" not in sanitized
    assert "[REDACTED]" in sanitized


def test_sanitize_telemetry_data_dict_and_nesting():
    data = {
        "user_id": "123",
        "authorization": "Bearer token-xyz",
        "api_key": "sk-1234567890",
        "nested": {
            "password": "secret_pass_123",
            "prompt": "Sensitive prompt instructions",
            "document_content": "Full confidential document body",
            "safe_field": 42,
        },
        "items": [
            {"token": "refresh-token-xyz"},
            {"safe_val": "hello"},
        ],
    }
    sanitized = sanitize_telemetry_data(data)
    assert sanitized["authorization"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert sanitized["nested"]["prompt"] == "[REDACTED]"
    assert sanitized["nested"]["document_content"] == "[REDACTED]"
    assert sanitized["nested"]["safe_field"] == 42
    assert sanitized["items"][0]["token"] == "[REDACTED]"
    assert sanitized["items"][1]["safe_val"] == "hello"


def test_sanitize_span_attribute():
    assert sanitize_span_attribute(None) == ""
    assert sanitize_span_attribute(123) == 123
    assert sanitize_span_attribute(True) is True
    assert sanitize_span_attribute(3.14) == 3.14
    attr = sanitize_span_attribute({"api_key": "secret", "count": 5})
    assert "secret" not in str(attr)
    assert "REDACTED" in str(attr)
