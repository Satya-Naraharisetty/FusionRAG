import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { Mail, Lock, Eye, EyeOff, ShieldAlert, ArrowRight, Github } from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import toast from "react-hot-toast";

export const LoginForm: React.FC = () => {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [isMagicLink, setIsMagicLink] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Load email if remember me is set
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
      setTimeout(() => {
        setIsSubmitting(false);
        toast.success("Magic sign-in link sent to your email!");
      }, 1000);
      return;
    }

    if (!email || !password) {
      setError("Please fill in all fields.");
      return;
    }

    setIsSubmitting(true);
    try {
      await login(email, password);
      if (rememberMe) {
        localStorage.setItem("login-remember-email", email);
      } else {
        localStorage.removeItem("login-remember-email");
      }
      toast.success("Welcome back!");
    } catch (err: unknown) {
      const e = err as { response?: { data?: { message?: string } } };
      const msg = e.response?.data?.message || "Invalid email or password.";
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSocialAuth = (provider: string) => {
    toast.success(`Redirecting to secure ${provider} authentication...`);
  };

  return (
    <div className="min-h-screen w-screen flex items-center justify-center bg-zinc-950 px-4 relative overflow-hidden select-none">
      {/* Dynamic Glow background effects */}
      <div className="absolute top-1/4 left-1/4 h-80 w-80 rounded-full bg-violet-650/10 blur-[120px] pointer-events-none animate-pulse duration-[6000ms]" />
      <div className="absolute bottom-1/4 right-1/4 h-80 w-80 rounded-full bg-fuchsia-650/10 blur-[120px] pointer-events-none animate-pulse duration-[8000ms]" />

      <div className="w-full max-w-[420px] bg-zinc-900/20 border border-zinc-900 backdrop-blur-xl rounded-2xl p-6.5 shadow-2xl relative z-10 animate-in fade-in zoom-in-95 duration-500">
        <div className="flex flex-col items-center text-center gap-1.5 mb-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-fuchsia-600 text-white font-extrabold text-lg shadow-md mb-2">
            H
          </div>
          <h1 className="text-xl font-bold font-title text-zinc-100 tracking-tight">Welcome Back</h1>
          <p className="text-xs text-zinc-500">Sign in to your Hybrid RAG assistant</p>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-950/20 border border-red-900/30 rounded-xl text-red-400 text-xs font-semibold mb-4 animate-in slide-in-from-top duration-300">
            <ShieldAlert size={16} className="flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            id="email"
            type="email"
            label="Email Address"
            labelClassName="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block mb-1.5"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            disabled={isSubmitting}
            leftIcon={<Mail size={15} />}
            className="bg-zinc-900/40 border-zinc-900 hover:border-zinc-850 focus-visible:ring-1 focus-visible:ring-violet-600 text-xs rounded-xl h-10 text-zinc-200"
          />

          {!isMagicLink && (
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              label="Password"
              labelClassName="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block mb-1.5"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isSubmitting}
              leftIcon={<Lock size={15} />}
              rightIcon={
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="text-zinc-500 hover:text-zinc-350 cursor-pointer focus:outline-none flex items-center justify-center"
                  disabled={isSubmitting}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              }
              className="bg-zinc-900/40 border-zinc-900 hover:border-zinc-850 focus-visible:ring-1 focus-visible:ring-violet-600 text-xs rounded-xl h-10 text-zinc-200"
            />
          )}

          {/* Remember me & Options row */}
          <div className="flex items-center justify-between text-xs font-semibold text-zinc-400 select-none">
            <label className="flex items-center gap-2 cursor-pointer hover:text-zinc-300">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="rounded accent-violet-600 cursor-pointer focus-visible:outline-none"
              />
              <span>Remember me</span>
            </label>
            <button
              type="button"
              onClick={() => setIsMagicLink(!isMagicLink)}
              className="text-violet-400 hover:text-violet-300 transition-colors cursor-pointer"
            >
              {isMagicLink ? "Use password login" : "Use magic link"}
            </button>
          </div>

          <Button
            type="submit"
            className="w-full bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:shadow-[0_0_15px_rgba(139,92,246,0.3)] border-0 text-white font-bold h-10 rounded-xl transition-all duration-300 shadow-md cursor-pointer mt-2 text-xs"
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <div className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4 text-white" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Authenticating...</span>
              </div>
            ) : (
              <div className="flex items-center gap-1">
                <span>{isMagicLink ? "Send Magic Link" : "Sign In"}</span>
                <ArrowRight size={15} />
              </div>
            )}
          </Button>
        </form>

        {/* Social Auth Separator */}
        <div className="relative my-5 flex items-center justify-center text-[10px] font-bold text-zinc-650 uppercase tracking-widest">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-zinc-900" />
          </div>
          <span className="relative bg-zinc-950 px-3 z-10 select-none">Or continue with</span>
        </div>

        {/* Social Login buttons */}
        <div className="grid grid-cols-2 gap-2.5">
          <Button
            variant="outline"
            onClick={() => handleSocialAuth("Google")}
            className="bg-zinc-900/10 border-zinc-900 hover:border-zinc-800 text-zinc-300 hover:bg-zinc-900/40 text-xs h-9 rounded-xl cursor-pointer gap-2"
          >
            {/* Custom Google Color Icon */}
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
            onClick={() => handleSocialAuth("GitHub")}
            className="bg-zinc-900/10 border-zinc-900 hover:border-zinc-800 text-zinc-300 hover:bg-zinc-900/40 text-xs h-9 rounded-xl cursor-pointer gap-2"
          >
            <Github size={14} />
            <span>GitHub</span>
          </Button>
        </div>

        <div className="text-center mt-6 text-xs text-zinc-550 select-none">
          <span>Don't have an account? </span>
          <Link to="/register" className="text-violet-400 hover:text-violet-300 font-bold transition-colors">
            Sign up
          </Link>
        </div>
      </div>
    </div>
  );
};
