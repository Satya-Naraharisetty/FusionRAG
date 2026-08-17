import React, { useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { RegisterCard } from "./RegisterCard";
import { checkPasswordStrength } from "../../lib/passwordStrength";
import toast from "react-hot-toast";

export const RegisterForm: React.FC = () => {
  const { register, loginWithGoogle, loginWithGithub } = useAuth();
  const [email, setEmail]                       = useState("");
  const [password, setPassword]                 = useState("");
  const [confirmPassword, setConfirmPassword]   = useState("");
  const [showPassword, setShowPassword]         = useState(false);
  const [isMagicLink, setIsMagicLink]           = useState(false);
  const [error, setError]                       = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting]         = useState(false);

  const strength          = checkPasswordStrength(password);
  const doPasswordsMatch  = password.length > 0 && password === confirmPassword;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (isMagicLink) {
      if (!email) { setError("Please enter your email to receive a registration link."); return; }
      setIsSubmitting(true);
      setTimeout(() => {
        setIsSubmitting(false);
        toast.success("Magic sign-up link sent!");
      }, 1000);
      return;
    }

    if (!email || !password || !confirmPassword) { setError("Please fill in all fields."); return; }
    if (password.length < 8)   { setError("Password must be at least 8 characters."); return; }
    if (password !== confirmPassword) { setError("Passwords do not match."); return; }
    if (strength.score < 2)    { setError("Password is too weak. Please choose a stronger one."); return; }

    setIsSubmitting(true);
    try {
      await register(email, password);
      toast.success("Account created!");
    } catch (err: unknown) {
      const e = err as { data?: { message?: string } };
      setError(e.data?.message || "Registration failed. Try again.");
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
      <RegisterCard
        email={email}
        setEmail={setEmail}
        password={password}
        setPassword={setPassword}
        confirmPassword={confirmPassword}
        setConfirmPassword={setConfirmPassword}
        showPassword={showPassword}
        setShowPassword={setShowPassword}
        isMagicLink={isMagicLink}
        setIsMagicLink={setIsMagicLink}
        error={error}
        isSubmitting={isSubmitting}
        onSubmit={handleSubmit}
        onSocialAuth={handleSocialAuth}
        strength={strength}
        doPasswordsMatch={doPasswordsMatch}
      />
    </div>
  );
};
