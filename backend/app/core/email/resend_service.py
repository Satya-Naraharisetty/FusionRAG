import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailService:
    """
    Transactional email service using the Resend REST API (https://resend.com).
    Dispatches styled, responsive HTML emails with plaintext fallbacks.
    """

    def __init__(
        self, api_key: str | None = None, from_email: str | None = None
    ) -> None:
        self._api_key = (api_key or settings.RESEND_API_KEY).strip()
        self._from_email = (from_email or settings.RESEND_FROM_EMAIL).strip()

    def _build_magic_link_html(self, magic_url: str, expire_minutes: int) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sign in to Hybrid RAG</title>
</head>
<body style="margin: 0; padding: 0; background-color: #09090b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f4f4f5;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #09090b; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="100%" max-width="480" border="0" cellspacing="0" cellpadding="0" style="max-width: 480px; background-color: #121215; border: 1px solid #27272a; border-radius: 16px; padding: 36px 32px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
          <!-- Logo -->
          <tr>
            <td align="center" style="padding-bottom: 24px;">
              <div style="display: inline-block; width: 44px; height: 44px; line-height: 44px; text-align: center; background-color: #18181b; border: 1px solid #3f3f46; border-radius: 12px; font-weight: bold; font-size: 18px; color: #ffffff;">
                H
              </div>
            </td>
          </tr>
          <!-- Heading -->
          <tr>
            <td align="center" style="padding-bottom: 12px;">
              <h1 style="margin: 0; font-size: 22px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">Sign in to Hybrid RAG</h1>
            </td>
          </tr>
          <!-- Subtext -->
          <tr>
            <td align="center" style="padding-bottom: 28px; color: #a1a1aa; font-size: 14px; line-height: 1.5;">
              Click the button below to sign in to your Hybrid RAG account passwordlessly.
            </td>
          </tr>
          <!-- Button -->
          <tr>
            <td align="center" style="padding-bottom: 28px;">
              <a href="{magic_url}" target="_blank" style="display: inline-block; background-color: #00d2ff; background-image: linear-gradient(135deg, #00d2ff 0%, #0099ff 100%); color: #000000; text-decoration: none; font-weight: 600; font-size: 14px; padding: 14px 32px; border-radius: 10px; box-shadow: 0 4px 14px rgba(0, 210, 255, 0.35);">
                Sign in to Hybrid RAG &rarr;
              </a>
            </td>
          </tr>
          <!-- Security note -->
          <tr>
            <td align="center" style="padding-top: 16px; border-top: 1px solid #27272a; color: #71717a; font-size: 12px; line-height: 1.5;">
              This link will expire in <strong>{expire_minutes} minutes</strong> and can only be used once.<br>
              If you didn't request this email, you can safely ignore it.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    def _build_verification_email_html(
        self, verify_url: str, otp_code: str, expire_minutes: int
    ) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verify your email - Hybrid RAG</title>
</head>
<body style="margin: 0; padding: 0; background-color: #09090b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f4f4f5;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #09090b; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="100%" max-width="480" border="0" cellspacing="0" cellpadding="0" style="max-width: 480px; background-color: #121215; border: 1px solid #27272a; border-radius: 16px; padding: 36px 32px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
          <!-- Logo -->
          <tr>
            <td align="center" style="padding-bottom: 24px;">
              <div style="display: inline-block; width: 44px; height: 44px; line-height: 44px; text-align: center; background-color: #18181b; border: 1px solid #3f3f46; border-radius: 12px; font-weight: bold; font-size: 18px; color: #ffffff;">
                H
              </div>
            </td>
          </tr>
          <!-- Heading -->
          <tr>
            <td align="center" style="padding-bottom: 12px;">
              <h1 style="margin: 0; font-size: 22px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">Verify Your Email Address</h1>
            </td>
          </tr>
          <!-- Subtext -->
          <tr>
            <td align="center" style="padding-bottom: 24px; color: #a1a1aa; font-size: 14px; line-height: 1.5;">
              Thank you for signing up for Hybrid RAG. Use the 6-digit verification code below or click the button to activate your account.
            </td>
          </tr>
          <!-- OTP Code Box -->
          <tr>
            <td align="center" style="padding-bottom: 24px;">
              <div style="background-color: #18181b; border: 1px solid #3f3f46; border-radius: 12px; padding: 18px 24px; display: inline-block;">
                <span style="font-family: 'Courier New', Courier, monospace; font-size: 32px; font-weight: 700; letter-spacing: 8px; color: #00d2ff;">
                  {otp_code}
                </span>
              </div>
            </td>
          </tr>
          <!-- Button -->
          <tr>
            <td align="center" style="padding-bottom: 28px;">
              <a href="{verify_url}" target="_blank" style="display: inline-block; background-color: #00d2ff; background-image: linear-gradient(135deg, #00d2ff 0%, #0099ff 100%); color: #000000; text-decoration: none; font-weight: 600; font-size: 14px; padding: 14px 32px; border-radius: 10px; box-shadow: 0 4px 14px rgba(0, 210, 255, 0.35);">
                Verify Email Address &rarr;
              </a>
            </td>
          </tr>
          <!-- Cross-device tip -->
          <tr>
            <td align="center" style="padding-bottom: 20px; color: #71717a; font-size: 12px; line-height: 1.5;">
              If you signed up on another device, enter the 6-digit code directly into the verification screen.
            </td>
          </tr>
          <!-- Security note -->
          <tr>
            <td align="center" style="padding-top: 16px; border-top: 1px solid #27272a; color: #71717a; font-size: 12px; line-height: 1.5;">
              This code and link will expire in <strong>{expire_minutes} minutes</strong>.<br>
              If you didn't create a Hybrid RAG account, you can safely ignore this email.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    async def send_magic_link(self, to_email: str, magic_url: str) -> bool:
        """
        Send a passwordless magic link to the recipient email.
        """
        expire_minutes = settings.MAGIC_LINK_EXPIRE_MINUTES
        html_content = self._build_magic_link_html(magic_url, expire_minutes)
        text_content = (
            f"Sign in to Hybrid RAG:\n\n{magic_url}\n\n"
            f"This link expires in {expire_minutes} minutes and can only be used once.\n"
            "If you did not request this, please ignore this email."
        )

        if not self._api_key or self._api_key.startswith("mock_"):
            logger.info(
                "[MOCK RESEND EMAIL] To: %s | Link: %s",
                to_email,
                magic_url,
            )
            return True

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": self._from_email,
            "to": [to_email],
            "subject": "Your Hybrid RAG Sign-In Link",
            "html": html_content,
            "text": text_content,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(RESEND_API_URL, headers=headers, json=payload)
            if response.status_code not in (200, 201):
                logger.error(
                    "Resend API error (%s): %s", response.status_code, response.text
                )
                raise RuntimeError(
                    f"Failed to dispatch email via Resend: {response.text}"
                )

        logger.info("Magic link email dispatched via Resend to %s", to_email)
        return True

    async def send_verification_email(
        self, to_email: str, verify_url: str, otp_code: str
    ) -> bool:
        """
        Send an email verification message containing both a 6-digit OTP code and a one-click verification URL.
        """
        expire_minutes = settings.EMAIL_VERIFICATION_EXPIRE_MINUTES
        html_content = self._build_verification_email_html(
            verify_url, otp_code, expire_minutes
        )
        text_content = (
            f"Verify your email for Hybrid RAG\n\n"
            f"Your 6-digit verification code is: {otp_code}\n\n"
            f"Or verify instantly with this link:\n{verify_url}\n\n"
            f"This code and link expire in {expire_minutes} minutes.\n"
            "If you did not create an account, you can safely ignore this email."
        )

        if not self._api_key or self._api_key.startswith("mock_"):
            logger.info(
                "[MOCK RESEND EMAIL] Verification To: %s | OTP: %s | Link: %s",
                to_email,
                otp_code,
                verify_url,
            )
            return True

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": self._from_email,
            "to": [to_email],
            "subject": f"Your Hybrid RAG Verification Code: {otp_code}",
            "html": html_content,
            "text": text_content,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(RESEND_API_URL, headers=headers, json=payload)
            if response.status_code not in (200, 201):
                logger.error(
                    "Resend API error (%s): %s", response.status_code, response.text
                )
                raise RuntimeError(
                    f"Failed to dispatch verification email via Resend: {response.text}"
                )

        logger.info("Verification email dispatched via Resend to %s", to_email)
        return True


def get_resend_service() -> ResendEmailService:
    return ResendEmailService()
