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
 *   Extracts the short-lived token from the URL fragment / query param,
 *   immediately wipes the browser address bar / history, sets the in-memory
 *   token, and smoothly directs the user to /chat.
 */
export default function OAuthCallbackPage() {
  const navigate = useNavigate();
  const processed = useRef(false);

  useEffect(() => {
    // Guard against React StrictMode double-invoke
    if (processed.current) return;
    processed.current = true;

    // 1. Extract params from search and hash fragment
    const searchParams = new URLSearchParams(window.location.search);
    const hashParams = new URLSearchParams(
      window.location.hash.startsWith("#") ? window.location.hash.slice(1) : window.location.hash
    );

    const oauthError = searchParams.get("oauth_error") || hashParams.get("oauth_error");
    const token = searchParams.get("token") || hashParams.get("token");

    // Clear any token / query params immediately from browser address bar & history
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
      window.opener.postMessage({ type: "OAUTH_SUCCESS", token: token || undefined }, window.location.origin);
      window.close();
      return;
    }

    // ── Direct Token Sign-In (Cross-Origin SPA) ──────────────────────────────
    if (token) {
      setAccessToken(token);
      authApi
        .getMe()
        .then(() => {
          navigate("/chat", { replace: true });
        })
        .catch((err) => {
          console.error("Failed to fetch user profile with OAuth token:", err);
          setAccessToken(null);
          navigate("/login?oauth_error=session_failed", { replace: true });
        });
      return;
    }

    // ── Silent Refresh via HttpOnly Cookie (Fallback) ─────────────────────────
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
