import React, { useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { RegisterCard } from "./RegisterCard";
import { checkPasswordStrength } from "../../lib/passwordStrength";
import toast from "react-hot-toast";

export const RegisterForm: React.FC = () => {
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isMagicLink, setIsMagicLink] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Password strength checking
  const strength = checkPasswordStrength(password);
  const doPasswordsMatch = password.length > 0 && password === confirmPassword;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (isMagicLink) {
      if (!email) {
        setError("Please enter your email to receive a registration link.");
        return;
      }
      setIsSubmitting(true);
      setTimeout(() => {
        setIsSubmitting(false);
        toast.success("Magic sign-up link sent to your email!");
      }, 1000);
      return;
    }

    if (!email || !password || !confirmPassword) {
      setError("Please fill in all fields.");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (strength.score < 2) {
      setError("Password is too weak. Please choose a stronger password.");
      return;
    }

    setIsSubmitting(true);
    try {
      await register(email, password);
      toast.success("Account created successfully!");
    } catch (err: unknown) {
      const e = err as { response?: { data?: { message?: string } } };
      const msg = e.response?.data?.message || "Registration failed. Try again.";
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSocialAuth = (provider: string) => {
    toast.success(`Redirecting to secure ${provider} registration...`);
  };

  return (
    <div className="min-h-screen w-screen flex items-center justify-center bg-zinc-50 dark:bg-[#0D0D0D] px-4 relative overflow-hidden select-none">
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
