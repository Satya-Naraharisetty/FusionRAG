import React from "react";
import { Link } from "react-router-dom";
import { Eye, EyeOff, ShieldAlert, ArrowRight, Github } from "lucide-react";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";

interface LoginCardProps {
  email: string;
  setEmail: (val: string) => void;
  password?: string;
  setPassword?: (val: string) => void;
  showPassword?: boolean;
  setShowPassword?: (val: boolean) => void;
  rememberMe: boolean;
  setRememberMe: (val: boolean) => void;
  isMagicLink: boolean;
  setIsMagicLink: (val: boolean) => void;
  error: string | null;
  isSubmitting: boolean;
  onSubmit: (e: React.FormEvent) => void;
  onSocialAuth: (provider: string) => void;
}

export const LoginCard: React.FC<LoginCardProps> = ({
  email,
  setEmail,
  password = "",
  setPassword,
  showPassword = false,
  setShowPassword,
  rememberMe,
  setRememberMe,
  isMagicLink,
  setIsMagicLink,
  error,
  isSubmitting,
  onSubmit,
  onSocialAuth,
}) => {
  return (
    <div className="w-full max-w-[400px] flex flex-col items-center bg-white dark:bg-[#171717] text-zinc-900 dark:text-zinc-100 p-8 rounded-2xl shadow-xl dark:shadow-2xl border border-zinc-200/50 dark:border-zinc-800/80 transition-all duration-300 animate-in fade-in zoom-in-95">
      {/* Brand Logo - Minimalist, ChatGPT-inspired but proprietary */}
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-zinc-900 dark:bg-zinc-100 text-white dark:text-black font-extrabold text-xl shadow-sm mb-6 transition-transform duration-300 hover:scale-105 select-none">
        H
      </div>

      <h1 className="text-2xl font-bold tracking-tight text-center mb-1 text-zinc-900 dark:text-zinc-50">
        Welcome back
      </h1>
      <p className="text-xs text-zinc-500 dark:text-zinc-400 text-center mb-6">
        Sign in with your Hybrid RAG account to continue
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
          className="bg-transparent border-zinc-300 dark:border-zinc-855 focus-visible:ring-1 focus-visible:ring-zinc-900 dark:focus-visible:ring-zinc-300 text-sm rounded-xl h-11 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-500"
        />

        {!isMagicLink && setPassword && (
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
            className="bg-transparent border-zinc-300 dark:border-zinc-850 focus-visible:ring-1 focus-visible:ring-zinc-900 dark:focus-visible:ring-zinc-300 text-sm rounded-xl h-11 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-500"
          />
        )}

        {/* Options Row */}
        <div className="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400 select-none px-0.5">
          <label className="flex items-center gap-2 cursor-pointer hover:text-zinc-750 dark:hover:text-zinc-200">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="rounded border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100 accent-zinc-900 dark:accent-zinc-100 cursor-pointer focus:ring-0"
            />
            <span>Remember me</span>
          </label>
          <button
            type="button"
            onClick={() => setIsMagicLink(!isMagicLink)}
            className="text-zinc-650 dark:text-zinc-350 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors cursor-pointer font-semibold underline underline-offset-2"
          >
            {isMagicLink ? "Use password" : "Use magic link"}
          </button>
        </div>

        <Button
          type="submit"
          className="w-full bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 dark:text-zinc-950 text-white font-semibold h-11 rounded-xl transition-all duration-200 shadow-sm cursor-pointer mt-2 text-sm flex items-center justify-center gap-1.5"
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <div className="flex items-center gap-2">
              <svg className="animate-spin h-4 w-4 text-current" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span>{isMagicLink ? "Sending link..." : "Signing in..."}</span>
            </div>
          ) : (
            <div className="flex items-center gap-1">
              <span>Continue</span>
              <ArrowRight size={15} />
            </div>
          )}
        </Button>
      </form>

      {/* Social Logins */}
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
          className="bg-transparent border-zinc-300 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-900 text-zinc-700 dark:text-zinc-300 text-xs h-10 rounded-xl cursor-pointer gap-2"
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
          className="bg-transparent border-zinc-300 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-900 text-zinc-700 dark:text-zinc-300 text-xs h-10 rounded-xl cursor-pointer gap-2"
        >
          <Github size={14} />
          <span>GitHub</span>
        </Button>
      </div>

      <div className="text-center mt-6 text-xs text-zinc-500 dark:text-zinc-450 select-none">
        <span>Don't have an account? </span>
        <Link to="/register" className="text-zinc-800 dark:text-zinc-200 hover:underline font-bold transition-colors">
          Sign up
        </Link>
      </div>
    </div>
  );
};
