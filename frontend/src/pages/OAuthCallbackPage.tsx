import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { setAccessToken } from "../api/client";
import { authApi } from "../api/auth";

/**
 * OAuthCallbackPage
 *
 * Mounted at /oauth/callback — the destination the backend redirects to after
 * a successful OAuth exchange.
 *
 * Security:
 *   Zero tokens are passed in the URL. The backend sets a secure, HttpOnly
 *   refresh cookie during the redirect. This page triggers a silent refresh
 *   to exchange the cookie for an in-memory access token via JSON response.
 */
export default function OAuthCallbackPage() {
  const navigate = useNavigate();
  const processed = useRef(false);

  useEffect(() => {
    // Guard against React StrictMode double-invoke
    if (processed.current) return;
    processed.current = true;

    const params = new URLSearchParams(window.location.search);
    const oauthError = params.get("oauth_error");

    // Clear any query params immediately from the URL
    window.history.replaceState({}, "", "/oauth/callback");

    if (oauthError) {
      console.error("OAuth callback error:", oauthError);
      if (window.opener) {
        window.opener.postMessage({ type: "OAUTH_ERROR", error: oauthError }, window.location.origin);
        window.close();
        return;
      }
      navigate("/login?oauth_error=" + oauthError, { replace: true });
      return;
    }

    // ── If opened inside popup, notify opener window and close ────────────────
    if (window.opener) {
      window.opener.postMessage({ type: "OAUTH_SUCCESS" }, window.location.origin);
      window.close();
      return;
    }

    // ── Silent Refresh via HttpOnly Cookie (Full-Page Fallback) ───────────────
    authApi
      .refresh()
      .then((tokenData) => {
        setAccessToken(tokenData.access_token);
        return authApi.getMe();
      })
      .then(() => {
        navigate("/chat", { replace: true });
      })
      .catch((err) => {
        console.error("Failed to complete OAuth authentication:", err);
        setAccessToken(null);
        navigate("/login?oauth_error=session_failed", { replace: true });
      });
  }, [navigate]);


  return (
    <div className="flex h-dvh w-dvw items-center justify-center bg-[var(--bg-primary)]">
      <div className="flex flex-col items-center gap-4">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--accent-primary)] border-t-transparent" />
        <p className="text-sm font-medium text-[var(--text-secondary)]">
          Completing sign-in…
        </p>
      </div>
    </div>
  );
}
