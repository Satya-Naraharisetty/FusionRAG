import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  KeyRound,
  Mail,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import toast from "react-hot-toast";
import { useAuth } from "../hooks/useAuth";
import { Button } from "../components/ui/Button";
import { SEOHead } from "../components/seo/SEOHead";

const COOLDOWN_SECONDS = 60;

export const VerifyEmailPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { verifyEmail, resendVerification } = useAuth();

  const tokenParam = searchParams.get("token");
  const emailParam = searchParams.get("email") || "";

  const [email, setEmail] = useState<string>(emailParam);
  const [otp, setOtp] = useState<string[]>(["", "", "", "", "", ""]);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [isVerified, setIsVerified] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState<number>(0);
  const [isResending, setIsResending] = useState<boolean>(false);

  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const redirectTimerRef = useRef<number | null>(null);

  // Clear timers on unmount
  useEffect(() => {
    return () => {
      if (redirectTimerRef.current) {
        window.clearTimeout(redirectTimerRef.current);
      }
    };
  }, []);

  // 1. Automatic verification if tokenParam is present in URL
  useEffect(() => {
    if (!tokenParam) return;

    let isMounted = true;

    const verifyToken = async () => {
      setIsVerifying(true);
      setError(null);
      try {
        await verifyEmail({ token: tokenParam });
        if (isMounted) {
          setIsVerified(true);
          toast.success("Email verified successfully!");
          redirectTimerRef.current = window.setTimeout(() => {
            navigate("/chat", { replace: true });
          }, 1500);
        }
      } catch (err: unknown) {
        if (isMounted) {
          const e = err as {
            data?: {
              message?: string;
              detail?: string;
              error?: { message?: string };
            };
          };
          const msg =
            e.data?.error?.message ||
            (typeof e.data?.detail === "string" ? e.data.detail : undefined) ||
            e.data?.message ||
            "Verification link is invalid or has expired.";
          setError(msg);
          toast.error(msg);
        }
      } finally {
        if (isMounted) {
          setIsVerifying(false);
        }
      }
    };

    verifyToken();
    return () => {
      isMounted = false;
    };
  }, [tokenParam, verifyEmail, navigate]);

  // 2. Cooldown timer for resending verification code
  useEffect(() => {
    if (resendCooldown <= 0) return;

    const timer = window.setInterval(() => {
      setResendCooldown((prev) => (prev > 1 ? prev - 1 : 0));
    }, 1000);

    if (
      typeof timer === "object" &&
      timer !== null &&
      "unref" in timer &&
      typeof (timer as { unref?: () => void }).unref === "function"
    ) {
      (timer as { unref: () => void }).unref();
    }

    return () => clearInterval(timer);
  }, [resendCooldown]);

  // Focus first input on mount if not auto-verifying
  useEffect(() => {
    if (!tokenParam && inputRefs.current[0]) {
      inputRefs.current[0].focus();
    }
  }, [tokenParam]);

  const handleOtpChange = (index: number, value: string) => {
    // Only accept numeric digit
    const cleaned = value.replace(/\D/g, "");
    if (!cleaned && value !== "") return;

    const newOtp = [...otp];
    const digit = cleaned.slice(-1);
    newOtp[index] = digit;
    setOtp(newOtp);
    setError(null);

    // Auto-advance to next box if digit is entered
    if (digit && index < 5 && inputRefs.current[index + 1]) {
      inputRefs.current[index + 1]?.focus();
    }

    // Auto-submit when all 6 digits are complete
    const fullCode = newOtp.join("");
    if (fullCode.length === 6 && !newOtp.includes("")) {
      submitOtpVerification(fullCode);
    }
  };

  const handleKeyDown = (
    index: number,
    e: React.KeyboardEvent<HTMLInputElement>
  ) => {
    if (e.key === "Backspace") {
      if (!otp[index] && index > 0 && inputRefs.current[index - 1]) {
        inputRefs.current[index - 1]?.focus();
      }
    } else if (e.key === "ArrowLeft" && index > 0) {
      inputRefs.current[index - 1]?.focus();
    } else if (e.key === "ArrowRight" && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pastedData = (
      e.clipboardData?.getData("text/plain") ||
      e.clipboardData?.getData("text") ||
      (typeof e.clipboardData?.getData === "function"
        ? (e.clipboardData.getData as () => string)()
        : "") ||
      ""
    ).trim();
    const digits = pastedData.replace(/\D/g, "").slice(0, 6);
    if (!digits) return;

    const newOtp = [...otp];
    for (let i = 0; i < 6; i++) {
      newOtp[i] = digits[i] || "";
    }
    setOtp(newOtp);
    setError(null);

    const focusIndex = Math.min(digits.length, 5);
    inputRefs.current[focusIndex]?.focus();

    if (digits.length === 6) {
      submitOtpVerification(digits);
    }
  };

  const submitOtpVerification = async (codeOverride?: string) => {
    const code = codeOverride || otp.join("");
    if (code.length !== 6) {
      setError("Please enter the complete 6-digit verification code.");
      return;
    }
    if (!email) {
      setError("Please provide your email address.");
      return;
    }

    setIsVerifying(true);
    setError(null);
    try {
      await verifyEmail({ email: email.trim(), otp: code });
      setIsVerified(true);
      toast.success("Email verified successfully!");
      redirectTimerRef.current = window.setTimeout(() => {
        navigate("/chat", { replace: true });
      }, 1500);
    } catch (err: unknown) {
      const e = err as {
        data?: {
          message?: string;
          detail?: string;
          error?: { message?: string };
        };
      };
      const msg =
        e.data?.error?.message ||
        (typeof e.data?.detail === "string" ? e.data.detail : undefined) ||
        e.data?.message ||
        "Invalid or expired verification code.";
      setError(msg);
      toast.error(msg);
    } finally {
      setIsVerifying(false);
    }
  };

  const handleResend = async () => {
    if (!email) {
      setError("Please enter your email address to receive a new code.");
      return;
    }
    if (resendCooldown > 0 || isResending) return;

    setIsResending(true);
    setError(null);
    try {
      await resendVerification(email.trim());
      setResendCooldown(COOLDOWN_SECONDS);
      toast.success("A new verification code and link have been dispatched.");
      // Clear OTP boxes for fresh entry
      setOtp(["", "", "", "", "", ""]);
      inputRefs.current[0]?.focus();
    } catch (err: unknown) {
      const e = err as {
        data?: {
          message?: string;
          detail?: string;
          error?: { message?: string };
        };
      };
      const msg =
        e.data?.error?.message ||
        (typeof e.data?.detail === "string" ? e.data.detail : undefined) ||
        e.data?.message ||
        "Failed to resend verification email. Please try again.";
      setError(msg);
      toast.error(msg);
    } finally {
      setIsResending(false);
    }
  };

  return (
    <div className="auth-page flex min-h-dvh w-full items-center justify-center p-4 bg-[var(--bg-primary)]">
      <SEOHead
        title="Verify Email"
        description="Verify your email address to activate your Hybrid RAG account."
        canonicalUrl="https://hybrid-rag-gilt.vercel.app/verify-email"
        robots="noindex, follow"
      />
      <div
        className="relative z-10 flex w-full max-w-[460px] flex-col rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-8 sm:p-10 shadow-2xl animate-in fade-in zoom-in-95 duration-300"
        aria-label="Email Verification Form"
      >
        {/* Brand Header */}
        <div className="flex flex-col items-center mb-6">
          <div className="mb-4 flex h-14 w-14 select-none items-center justify-center rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-xl font-bold text-[var(--accent-primary)] shadow-sm">
            {isVerified ? (
              <CheckCircle2 className="h-7 w-7 text-[var(--accent-success)] animate-bounce" />
            ) : tokenParam && isVerifying ? (
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--accent-primary)] border-t-transparent" />
            ) : (
              <KeyRound className="h-6 w-6 text-[var(--accent-primary)]" />
            )}
          </div>
          <h1 className="mb-1.5 text-2xl font-bold tracking-tight text-[var(--text-primary)] text-center">
            {isVerified
              ? "Email Verified!"
              : tokenParam && isVerifying
              ? "Verifying link..."
              : "Verify your email"}
          </h1>
          <p className="text-sm text-[var(--text-secondary)] text-center leading-relaxed">
            {isVerified
              ? "Your account is activated. Redirecting you to chat..."
              : email
              ? `We sent a 6-digit verification code and a one-click link to ${email}`
              : "Enter your 6-digit code or click the verification link sent to your inbox."}
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div
            role="alert"
            className="mb-6 flex items-start gap-2.5 rounded-xl border border-[var(--accent-error)]/30 bg-[var(--accent-error)]/10 p-3.5 text-xs font-medium text-[var(--accent-error)] animate-in slide-in-from-top duration-200"
          >
            <ShieldAlert size={16} className="flex-shrink-0 mt-0.5" />
            <span className="leading-relaxed">{error}</span>
          </div>
        )}

        {/* Success State */}
        {isVerified ? (
          <div className="flex flex-col items-center gap-4 py-4 text-center">
            <div className="flex items-center gap-2 rounded-full border border-[var(--accent-success)]/30 bg-[var(--accent-success)]/10 px-4 py-2 text-xs font-medium text-[var(--accent-success)]">
              <Sparkles size={14} /> Account activated successfully
            </div>
            <p className="text-xs text-[var(--text-muted)]">
              Redirecting you to the platform...
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {/* Email Edit field if user arrived without email param */}
            {!emailParam && (
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="verify-email-input"
                  className="text-xs font-medium text-[var(--text-secondary)]"
                >
                  Email Address
                </label>
                <div className="relative">
                  <Mail
                    size={16}
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
                  />
                  <input
                    id="verify-email-input"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@example.com"
                    disabled={isVerifying}
                    className="h-11 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] pl-10 pr-3.5 text-sm text-[var(--text-primary)] transition-all placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/20"
                  />
                </div>
              </div>
            )}

            {/* 6-Digit OTP Box Grid */}
            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-[var(--text-secondary)] text-center">
                6-Digit Security Code
              </label>
              <div className="flex items-center justify-center gap-2 sm:gap-2.5">
                {otp.map((digit, idx) => (
                  <input
                    key={idx}
                    ref={(el) => (inputRefs.current[idx] = el)}
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleOtpChange(idx, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(idx, e)}
                    onPaste={handlePaste}
                    disabled={isVerifying}
                    aria-label={`Digit ${idx + 1}`}
                    className="h-13 w-11 sm:h-14 sm:w-13 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] text-center font-mono text-xl sm:text-2xl font-bold text-[var(--accent-primary)] shadow-sm transition-all focus:border-[var(--accent-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 disabled:opacity-50"
                  />
                ))}
              </div>
              <p className="text-[11px] text-[var(--text-muted)] text-center mt-1">
                You can paste the entire code directly into any box
              </p>
            </div>

            {/* Submit Verification Button */}
            <Button
              type="button"
              variant="default"
              size="lg"
              className="w-full h-11 text-sm font-semibold shadow-lg shadow-[var(--accent-primary)]/20"
              loading={isVerifying}
              disabled={isVerifying || otp.join("").length !== 6 || !email}
              onClick={() => submitOtpVerification()}
            >
              Verify Code <ArrowRight size={16} className="ml-1.5" />
            </Button>

            {/* Resend Code Section */}
            <div className="flex flex-col items-center gap-2 pt-2 border-t border-[var(--border-subtle)]">
              <p className="text-xs text-[var(--text-muted)]">
                Didn't receive the email?
              </p>
              <button
                type="button"
                onClick={handleResend}
                disabled={resendCooldown > 0 || isResending || !email}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--accent-primary)] hover:underline disabled:opacity-50 disabled:no-underline cursor-pointer"
              >
                <RefreshCw
                  size={13}
                  className={isResending ? "animate-spin" : ""}
                />
                {resendCooldown > 0
                  ? `Resend available in ${resendCooldown}s`
                  : isResending
                  ? "Sending new code..."
                  : "Resend Code & Link"}
              </button>
            </div>

            {/* Back to Login Link */}
            <div className="text-center pt-2">
              <Link
                to="/login"
                className="inline-flex items-center gap-1 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                <ArrowLeft size={13} /> Back to Sign In
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default VerifyEmailPage;
