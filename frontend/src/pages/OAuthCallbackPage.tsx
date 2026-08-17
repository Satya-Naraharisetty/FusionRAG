import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { setAccessToken } from "../api/client";
import { authApi } from "../api/auth";

/**
 * OAuthCallbackPage
 *
 * Mounted at /oauth/callback — the destination the backend redirects to after
 * a successful Google OAuth exchange.
 *
 * URL format:  /oauth/callback?access_token=<jwt>&expires_in=<seconds>
 *
 * Responsibilities:
 *   1. Read access_token + expires_in from the URL query string.
 *   2. Store the token in-memory via setAccessToken.
 *   3. Immediately replace the URL history entry so the token is gone from
 *      the address bar (no back-button leakage).
 *   4. Fetch the user profile to hydrate AuthContext.
 *   5. Redirect to /chat on success or /login on failure.
 *
 * Note: The refresh cookie was already set by the backend redirect response,
 * so silent refresh will work normally from this point on.
 */
export default function OAuthCallbackPage() {
  const navigate = useNavigate();
  const processed = useRef(false);

  useEffect(() => {
    // Guard against React StrictMode double-invoke
    if (processed.current) return;
    processed.current = true;

    const params = new URLSearchParams(window.location.search);
    const accessToken = params.get("access_token");
    const expiresIn = params.get("expires_in");
    const oauthError = params.get("oauth_error");

    // ── Clear the sensitive query params immediately from the URL ──────────────
    window.history.replaceState({}, "", "/oauth/callback");

    if (oauthError || !accessToken) {
      console.error("OAuth callback error:", oauthError || "missing token");
      navigate("/login?oauth_error=" + (oauthError || "missing_token"), {
        replace: true,
      });
      return;
    }

    // ── Store token + hydrate user profile ────────────────────────────────────
    setAccessToken(accessToken);

    authApi
      .getMe()
      .then(() => {
        // Navigate into the app; AuthContext will pick up the token via
        // the in-memory store and getMe will already have been called.
        navigate("/chat", { replace: true });
      })
      .catch(() => {
        setAccessToken(null);
        navigate("/login?oauth_error=profile_fetch_failed", { replace: true });
      });

    // Store expires_in for potential future use (e.g. scheduling refresh)
    if (expiresIn) {
      sessionStorage.setItem("token_expires_in", expiresIn);
    }
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
