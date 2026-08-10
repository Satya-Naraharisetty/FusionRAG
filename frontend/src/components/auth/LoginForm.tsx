import React, { useState, useEffect } from "react";
import { useAuth } from "../../hooks/useAuth";
import { LoginCard } from "./LoginCard";
import toast from "react-hot-toast";

export const LoginForm: React.FC = () => {
  const { login } = useAuth();
  const [email, setEmail]             = useState("");
  const [password, setPassword]       = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe]   = useState(false);
  const [isMagicLink, setIsMagicLink] = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("login-remember-email");
    if (saved) { setEmail(saved); setRememberMe(true); }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (isMagicLink) {
      if (!email) { setError("Please enter your email to receive a magic link."); return; }
      setIsSubmitting(true);
      setTimeout(() => {
        setIsSubmitting(false);
        toast.success("Magic sign-in link sent!");
      }, 1000);
      return;
    }

    if (!email || !password) { setError("Please fill in all fields."); return; }

    setIsSubmitting(true);
    try {
      await login(email, password);
      if (rememberMe) localStorage.setItem("login-remember-email", email);
      else            localStorage.removeItem("login-remember-email");
      toast.success("Welcome back!");
    } catch (err: unknown) {
      const e = err as { data?: { message?: string } };
      setError(e.data?.message || "Invalid email or password.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSocialAuth = (provider: string) => {
    toast.success(`Redirecting to ${provider} authentication…`);
  };

  return (
    <div className="auth-page">
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
