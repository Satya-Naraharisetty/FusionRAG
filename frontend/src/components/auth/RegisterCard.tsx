import React from "react";
import { Link } from "react-router-dom";
import { Eye, EyeOff, ShieldAlert, ArrowRight } from "lucide-react";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";

interface RegisterCardProps {
  email: string;
  setEmail: (val: string) => void;
  password?: string;
  setPassword?: (val: string) => void;
  confirmPassword?: string;
  setConfirmPassword?: (val: string) => void;
  showPassword?: boolean;
  setShowPassword?: (val: boolean) => void;
  isMagicLink: boolean;
  setIsMagicLink: (val: boolean) => void;
  error: string | null;
  isSubmitting: boolean;
  onSubmit: (e: React.FormEvent) => void;
  onSocialAuth: (provider: string) => void;
  strength?: { score: number; label: string; color: string; feedback: string };
  doPasswordsMatch?: boolean;
}

export const RegisterCard: React.FC<RegisterCardProps> = ({
  email,
  setEmail,
  password = "",
  setPassword,
  confirmPassword = "",
  setConfirmPassword,
  showPassword = false,
  setShowPassword,
  isMagicLink,
  setIsMagicLink,
  error,
  isSubmitting,
  onSubmit,
  onSocialAuth,
  strength,
  doPasswordsMatch,
}) => {
  return (
    <div
      className="relative z-10 flex w-full max-w-[408px] flex-col rounded-[var(--radius-2xl)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-8 shadow-none animate-in fade-in zoom-in-95 duration-300"
      aria-label="Register form"
    >
      {/* Brand mark */}
      <div className="flex flex-col items-center mb-6">
        <div className="mb-4 flex h-10 w-10 select-none items-center justify-center rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-base font-semibold text-[var(--text-primary)]">
          H
        </div>
        <h1 className="mb-1 text-2xl font-semibold tracking-tight text-[var(--text-primary)]">
          Create account
        </h1>
        <p className="text-sm text-[var(--text-secondary)] text-center">
          Start chatting with your documents
        </p>
      </div>

      {/* Error alert */}
      {error && (
        <div
          role="alert"
          className="mb-5 flex items-center gap-2 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3 text-xs font-medium text-[var(--text-secondary)] animate-in slide-in-from-top duration-200"
        >
          <ShieldAlert size={14} className="flex-shrink-0 text-[var(--accent-error)]" />
          <span>{error}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={onSubmit} className="flex flex-col gap-3.5" noValidate>
        <Input
          id="register-email"
          type="email"
          placeholder="Email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          disabled={isSubmitting}
          autoComplete="email"
          className="h-11"
        />

        {!isMagicLink && setPassword && setConfirmPassword && (
          <>
            {/* Password field + strength meter */}
            <div className="space-y-1.5">
              <Input
                id="register-password"
                type={showPassword ? "text" : "password"}
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isSubmitting}
                autoComplete="new-password"
                rightIcon={
                  <button
                    type="button"
                    onClick={() => setShowPassword?.(!showPassword)}
                    className="flex cursor-pointer items-center p-1 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)] focus:outline-none"
                    disabled={isSubmitting}
                    tabIndex={-1}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                }
                className="h-11"
              />

              {password.length > 0 && strength && (
                <div className="space-y-1 pt-0.5 animate-in fade-in duration-200">
                  <div className="flex justify-between text-[10px] font-medium">
                    <span className="text-[var(--text-muted)] uppercase tracking-wider">Strength</span>
                    <span
                      className={
                        strength.score < 2
                          ? "text-red-400"
                          : strength.score === 2
                            ? "text-amber-400"
                            : "text-emerald-400"
                      }
                    >
                      {strength.label}
                    </span>
                  </div>
                  <div className="grid grid-cols-4 gap-1">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <div
                        key={i}
                        className={`h-1 rounded-full transition-all duration-300 ${
                          i < strength.score ? strength.color : "bg-[var(--bg-tertiary)]"
                        }`}
                      />
                    ))}
                  </div>
                  {strength.feedback && (
                    <p className="text-[10px] text-[var(--text-muted)] leading-normal">
                      {strength.feedback}
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Confirm password */}
            <div className="space-y-1">
              <Input
                id="register-confirm-password"
                type={showPassword ? "text" : "password"}
                placeholder="Confirm password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                disabled={isSubmitting}
                autoComplete="new-password"
                className="h-11"
              />
              {confirmPassword.length > 0 && (
                <p
                  className={`text-[10px] font-medium px-0.5 ${
                    doPasswordsMatch ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  {doPasswordsMatch ? "Passwords match" : "Passwords do not match"}
                </p>
              )}
            </div>
          </>
        )}

        {/* Magic link toggle */}
        <div className="flex justify-end text-xs text-[var(--text-secondary)] select-none">
          <button
            type="button"
            onClick={() => setIsMagicLink(!isMagicLink)}
            className="hover:text-[var(--text-primary)] transition-colors cursor-pointer underline underline-offset-2"
          >
            {isMagicLink ? "Use password instead" : "Use magic link"}
          </button>
        </div>

        <Button
          type="submit"
          variant="default"
          size="lg"
          fullWidth
          className="mt-1 font-medium"
          disabled={
            isSubmitting ||
            (!isMagicLink &&
              (password.length < 8 ||
                (strength != null && strength.score < 2) ||
                !doPasswordsMatch))
          }
          loading={isSubmitting}
        >
          {!isSubmitting && (
            <span className="flex items-center gap-1.5">
              Create account
              <ArrowRight size={15} />
            </span>
          )}
        </Button>
      </form>

      {/* Divider */}
      <div className="relative my-5 flex items-center">
        <div className="flex-1 border-t border-[var(--border-subtle)]" />
        <span className="px-3 text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-widest select-none">
          or
        </span>
        <div className="flex-1 border-t border-[var(--border-subtle)]" />
      </div>

      {/* OAuth buttons */}
      <div className="flex flex-col gap-2">
        <Button
          variant="secondary"
          size="default"
          onClick={() => onSocialAuth("Google")}
          className="gap-2 text-xs font-medium w-full"
          aria-label="Sign up with Google"
        >
          <svg className="h-4 w-4 flex-shrink-0" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="#EA4335" d="M12 5.04c1.62 0 3.08.56 4.22 1.65l3.15-3.15C17.45 1.84 14.93 1 12 1 7.35 1 3.39 3.65 1.5 7.5l3.6 2.8C6.01 7.03 8.79 5.04 12 5.04z" />
            <path fill="#4285F4" d="M23.49 12.27c0-.81-.07-1.59-.2-2.36H12v4.47h6.44c-.28 1.47-1.11 2.71-2.36 3.55l3.6 2.8c2.1-1.94 3.31-4.8 3.31-8.46z" />
            <path fill="#FBBC05" d="M5.1 14.7c-.24-.73-.38-1.51-.38-2.32s.14-1.59.38-2.32L1.5 7.26C.54 9.17 0 11.31 0 13.62s.54 4.45 1.5 6.36l3.6-2.8z" />
            <path fill="#34A853" d="M12 23c3.24 0 5.97-1.07 7.96-2.91l-3.6-2.8c-1.1.74-2.5 1.18-4.36 1.18-3.21 0-5.99-1.99-6.9-4.76L1.5 16.5C3.39 20.35 7.35 23 12 23z" />
          </svg>
          <span>Continue with Google</span>
        </Button>
      </div>

      {/* Footer link */}
      <p className="text-center mt-6 text-xs text-[var(--text-secondary)] select-none">
        Already have an account?{" "}
        <Link
          to="/login"
          className="text-[var(--text-primary)] font-semibold hover:underline underline-offset-2 transition-colors"
        >
          Sign in
        </Link>
      </p>
    </div>
  );
};
