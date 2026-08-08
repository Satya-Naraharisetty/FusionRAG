import React from "react";
import { Link } from "react-router-dom";
import { Eye, EyeOff, ShieldAlert, ArrowRight, Github } from "lucide-react";
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
  strength?: {
    score: number;
    label: string;
    color: string;
    feedback: string;
  };
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
    <div className="w-full max-w-[430px] flex flex-col items-center bg-white dark:bg-[#171717] text-zinc-900 dark:text-zinc-100 p-8 rounded-2xl shadow-sm border border-zinc-200/40 dark:border-[rgba(255,255,255,0.07)] transition-all duration-300 animate-in fade-in zoom-in-95">
      {/* Brand Logo - Minimalist, ChatGPT-inspired */}
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-zinc-900 dark:bg-zinc-100 text-white dark:text-black font-extrabold text-lg shadow-xs mb-5 transition-transform duration-300 hover:scale-105 select-none">
        H
      </div>

      <h1 className="text-2xl font-bold tracking-tight text-center mb-1 text-zinc-900 dark:text-zinc-50">
        Create account
      </h1>
      <p className="text-xs text-zinc-500 dark:text-zinc-400 text-center mb-6">
        Sign up with your email to start chatting with Hybrid RAG
      </p>

      {error && (
        <div className="w-full flex items-center gap-2 p-3 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 rounded-xl text-red-650 dark:text-red-400 text-xs font-medium mb-4 animate-in slide-in-from-top duration-300">
          <ShieldAlert size={15} className="flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={onSubmit} className="w-full space-y-4">
        <Input
          id="email"
          type="email"
          placeholder="Email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          disabled={isSubmitting}
          className="h-12 rounded-xl text-sm"
        />

        {!isMagicLink && setPassword && setConfirmPassword && (
          <>
            <div className="space-y-1.5">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isSubmitting}
                rightIcon={
                  <button
                    type="button"
                    onClick={() => setShowPassword?.(!showPassword)}
                    className="text-zinc-450 hover:text-zinc-700 dark:hover:text-zinc-300 cursor-pointer focus:outline-none flex items-center justify-center p-1"
                    disabled={isSubmitting}
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                }
                className="h-12 rounded-xl text-sm"
              />

              {/* Password strength meter */}
              {password.length > 0 && strength && (
                <div className="space-y-1.5 pt-1 animate-in fade-in duration-300">
                  <div className="flex justify-between items-center text-[9px] font-bold">
                    <span className="text-zinc-450">STRENGTH:</span>
                    <span
                      className={
                        strength.score < 2
                          ? "text-red-405"
                          : strength.score === 2
                            ? "text-amber-405"
                            : "text-emerald-500"
                      }
                    >
                      {strength.label}
                    </span>
                  </div>
                  {/* Progress bars */}
                  <div className="grid grid-cols-4 gap-1">
                    {Array.from({ length: 4 }).map((_, idx) => (
                      <div
                        key={idx}
                        className={`h-1 rounded-full transition-all duration-350 ${
                          idx < strength.score ? strength.color : "bg-zinc-200 dark:bg-zinc-800"
                        }`}
                      />
                    ))}
                  </div>
                  <p className="text-[9px] text-zinc-500 leading-normal">
                    {strength.feedback}
                  </p>
                </div>
              )}
            </div>

            <div className="space-y-1.5">
              <Input
                id="confirmPassword"
                type={showPassword ? "text" : "password"}
                placeholder="Confirm password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                disabled={isSubmitting}
                className="h-12 rounded-xl text-sm"
              />
              {confirmPassword.length > 0 && (
                <p className={`text-[9px] font-bold ${doPasswordsMatch ? "text-emerald-500" : "text-red-400"}`}>
                  {doPasswordsMatch ? "Passwords match" : "Passwords do not match"}
                </p>
              )}
            </div>
          </>
        )}

        {/* Options Row */}
        <div className="flex items-center justify-end text-xs font-semibold text-zinc-500 select-none pb-1">
          <button
            type="button"
            onClick={() => setIsMagicLink(!isMagicLink)}
            className="text-zinc-650 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors cursor-pointer underline underline-offset-2"
          >
            {isMagicLink ? "Use password register" : "Use magic link"}
          </button>
        </div>

        <Button
          type="submit"
          className="w-full bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-250 dark:text-zinc-950 text-white font-semibold h-12 rounded-xl transition-all duration-200 active:scale-[0.98] cursor-pointer mt-2 text-sm flex items-center justify-center gap-1.5"
          disabled={
            isSubmitting ||
            (!isMagicLink && (password.length < 8 || (strength && strength.score < 2) || !doPasswordsMatch))
          }
        >
          {isSubmitting ? (
            <div className="flex items-center gap-2">
              <svg className="animate-spin h-4 w-4 text-current" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span>Creating account...</span>
            </div>
          ) : (
            <div className="flex items-center gap-1">
              <span>Continue</span>
              <ArrowRight size={15} />
            </div>
          )}
        </Button>
      </form>

      {/* Social Register */}
      <div className="relative w-full my-5 flex items-center justify-center text-[10px] font-bold text-zinc-400 dark:text-zinc-550 uppercase tracking-widest">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-zinc-200 dark:border-zinc-800/80" />
        </div>
        <span className="relative bg-white dark:bg-[#171717] px-3 z-10 select-none">OR</span>
      </div>

      <div className="w-full grid grid-cols-2 gap-2.5">
        <Button
          variant="outline"
          onClick={() => onSocialAuth("Google")}
          className="bg-transparent border-zinc-200 dark:border-[rgba(255,255,255,0.08)] hover:bg-zinc-50 dark:hover:bg-zinc-900/40 text-zinc-700 dark:text-zinc-300 text-xs h-12 rounded-xl cursor-pointer gap-2"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24">
            <path fill="#EA4335" d="M12 5.04c1.62 0 3.08.56 4.22 1.65l3.15-3.15C17.45 1.84 14.93 1 12 1 7.35 1 3.39 3.65 1.5 7.5l3.6 2.8C6.01 7.03 8.79 5.04 12 5.04z" />
            <path fill="#4285F4" d="M23.49 12.27c0-.81-.07-1.59-.2-2.36H12v4.47h6.44c-.28 1.47-1.11 2.71-2.36 3.55l3.6 2.8c2.1-1.94 3.31-4.8 3.31-8.46z" />
            <path fill="#FBBC05" d="M5.1 14.7c-.24-.73-.38-1.51-.38-2.32s.14-1.59.38-2.32L1.5 7.26C.54 9.17 0 11.31 0 13.62s.54 4.45 1.5 6.36l3.6-2.8z" />
            <path fill="#34A853" d="M12 23c3.24 0 5.97-1.07 7.96-2.91l-3.6-2.8c-1.1.74-2.5 1.18-4.36 1.18-3.21 0-5.99-1.99-6.9-4.76L1.5 16.5C3.39 20.35 7.35 23 12 23z" />
          </svg>
          <span>Google</span>
        </Button>
        <Button
          variant="outline"
          onClick={() => onSocialAuth("GitHub")}
          className="bg-transparent border-zinc-200 dark:border-[rgba(255,255,255,0.08)] hover:bg-zinc-50 dark:hover:bg-zinc-900/40 text-zinc-700 dark:text-zinc-300 text-xs h-12 rounded-xl cursor-pointer gap-2"
        >
          <Github size={14} />
          <span>GitHub</span>
        </Button>
      </div>

      <div className="text-center mt-6 text-xs text-zinc-550 select-none">
        <span>Already have an account? </span>
        <Link to="/login" className="text-zinc-850 dark:text-zinc-200 hover:underline font-bold transition-colors">
          Sign in
        </Link>
      </div>
    </div>
  );
};
