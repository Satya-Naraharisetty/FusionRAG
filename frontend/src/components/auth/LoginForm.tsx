import React, { useState, useEffect } from "react";
import { useAuth } from "../../hooks/useAuth";
import { LoginCard } from "./LoginCard";
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
    <div className="min-h-screen w-screen flex items-center justify-center bg-zinc-50 dark:bg-[#0D0D0D] px-4 relative overflow-hidden select-none">
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
