from unittest.mock import AsyncMock, patch

import pytest

from app.core.email.resend_service import ResendEmailService


@pytest.mark.asyncio
async def test_resend_email_service_mock_mode():
    service = ResendEmailService(api_key="mock_key", from_email="onboarding@resend.dev")
    success = await service.send_magic_link(
        to_email="test@example.com",
        magic_url="http://localhost:5173/oauth/callback#token=xyz123",
    )
    assert success is True


@pytest.mark.asyncio
async def test_resend_email_service_real_api_call():
    service = ResendEmailService(
        api_key="re_valid_api_key", from_email="onboarding@resend.dev"
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"id": "email_123"}

        success = await service.send_magic_link(
            to_email="test@example.com",
            magic_url="http://localhost:5173/oauth/callback#token=xyz123",
        )
        assert success is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["to"] == ["test@example.com"]
        assert "xyz123" in call_kwargs["json"]["html"]
