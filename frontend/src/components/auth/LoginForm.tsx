import React, { useState, useEffect } from "react";
import { useAuth } from "../../hooks/useAuth";
import { authApi } from "../../api/auth";
import { LoginCard } from "./LoginCard";
import { SEOHead } from "../seo/SEOHead";
import toast from "react-hot-toast";
import { useNavigate, useSearchParams } from "react-router-dom";

const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  access_denied: "Google sign-in was cancelled.",
  invalid_state: "Security check failed. Please try again.",
  exchange_failed: "Could not complete Google sign-in. Please try again.",
  session_failed: "Session creation failed. Please try again.",
  missing_params: "OAuth response was invalid. Please try again.",
  missing_token: "Sign-in token was not received. Please try again.",
  profile_fetch_failed: "Could not load your profile. Please try again.",
};

export const LoginForm: React.FC = () => {
  const navigate = useNavigate();
  const { login, loginWithGoogle, loginWithGithub } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [isMagicLink, setIsMagicLink] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Show a toast if we were redirected back from a failed OAuth attempt
  useEffect(() => {
    const oauthError = searchParams.get("oauth_error");
    if (oauthError) {
      const msg = OAUTH_ERROR_MESSAGES[oauthError] || "Google sign-in failed. Please try again.";
      toast.error(msg);
      // Remove the param so refreshing doesn't re-show it
      setSearchParams((prev) => {
        prev.delete("oauth_error");
        return prev;
      });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    const saved = localStorage.getItem("login-remember-email");
    if (saved) {
      setEmail(saved);
      setRememberMe(true);
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (isMagicLink) {
      if (!email) {
        setError("Please enter your email to receive a magic link.");
        return;
      }
      setIsSubmitting(true);
      try {
        const res = await authApi.requestMagicLink(email);
        toast.success(res.message || "Magic sign-in link sent! Check your inbox.");
      } catch (err: unknown) {
        const e = err as {
          status?: number;
          message?: string;
          data?: { message?: string; detail?: string; error?: { message?: string } };
        };
        const msg =
          e.data?.error?.message ||
          (typeof e.data?.detail === "string" ? e.data.detail : undefined) ||
          e.data?.message ||
          e.message ||
          "Failed to send magic link. Please try again.";
        setError(msg);
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    if (!email || !password) {
      setError("Please fill in all fields.");
      return;
    }

    setIsSubmitting(true);
    try {
      await login(email, password);
      if (rememberMe) localStorage.setItem("login-remember-email", email);
      else localStorage.removeItem("login-remember-email");
      toast.success("Welcome back!");
    } catch (err: unknown) {
      const e = err as {
        status?: number;
        message?: string;
        data?: {
          code?: string;
          message?: string;
          detail?: string;
          error?: { code?: string; message?: string };
        };
      };

      const isUnverified =
        e.status === 403 ||
        e.data?.error?.code === "EMAIL_NOT_VERIFIED" ||
        e.data?.code === "EMAIL_NOT_VERIFIED" ||
        (e.message && e.message.toLowerCase().includes("verify your email"));

      if (isUnverified) {
        toast.error("Please verify your email address to log in.");
        navigate(`/verify-email?email=${encodeURIComponent(email)}`);
        return;
      }

      const errorMessage =
        e.status === 429
          ? typeof e.data?.detail === "string"
            ? e.data.detail
            : "Too many login attempts. Please wait 5 minutes and try again."
          : e.data?.error?.message ||
            (typeof e.data?.detail === "string" ? e.data.detail : undefined) ||
            e.data?.message ||
            e.message ||
            "Invalid email or password.";
      setError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSocialAuth = (provider: string) => {
    if (provider === "Google") {
      loginWithGoogle();
    } else if (provider === "GitHub") {
      loginWithGithub();
    }
  };

  return (
    <div className="auth-page">
      <SEOHead
        title="Sign In"
        description="Sign in to your Fusion RAG account to access your AI document chat studio, indexed knowledge bases, and custom RAG evaluations."
        canonicalUrl="https://fusionrag.vercel.app/login"
      />
      <LoginCard
        email={email}
        setEmail={setEmail}
        password={password}
        setPassword={setPassword}
        showPassword={showPassword}
        setShowPassword={setShowPassword}
        rememberMe={rememberMe}
        setRememberMe={setRememberMe}
        isMagicLink={isMagicLink}
        setIsMagicLink={setIsMagicLink}
        error={error}
        isSubmitting={isSubmitting}
        onSubmit={handleSubmit}
        onSocialAuth={handleSocialAuth}
      />
    </div>
  );
};
