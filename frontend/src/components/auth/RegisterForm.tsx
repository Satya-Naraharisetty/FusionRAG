import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { Mail, Lock, Eye, EyeOff, ShieldAlert, ArrowRight, CheckCircle2, XCircle } from "lucide-react";

export const RegisterForm: React.FC = () => {
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Live password validation checks
  const isMinLength = password.length >= 8;
  const isNotCommon =
    password.length > 0 &&
    !["password", "password123", "12345678", "admin123"].includes(
      password.toLowerCase()
    );
  const doPasswordsMatch = password.length > 0 && password === confirmPassword;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

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

    setIsSubmitting(true);
    try {
      await register(email, password);
    } catch (err: any) {
      const msg =
        err.response?.data?.message || "Registration failed. Try again.";
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="auth-card-container">
      <div className="auth-card">
        {/* Decorative backgrounds */}
        <div className="glow-circle glow-1"></div>
        <div className="glow-circle glow-2"></div>

        <div className="auth-header">
          <div className="logo-badge">
            <span className="logo-text">HR</span>
          </div>
          <h1>Create Account</h1>
          <p className="auth-subtitle">
            Join us to start chatting with Hybrid RAG
          </p>
        </div>

        {error && (
          <div className="auth-error-alert">
            <ShieldAlert size={18} className="alert-icon" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="email">Email Address</label>
            <div className="input-wrapper">
              <Mail size={18} className="input-icon" />
              <input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={isSubmitting}
                className="auth-input"
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className="input-wrapper">
              <Lock size={18} className="input-icon" />
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="Minimum 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isSubmitting}
                className="auth-input"
              />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowPassword(!showPassword)}
                disabled={isSubmitting}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="confirmPassword">Confirm Password</label>
            <div className="input-wrapper">
              <Lock size={18} className="input-icon" />
              <input
                id="confirmPassword"
                type={showPassword ? "text" : "password"}
                placeholder="Repeat password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                disabled={isSubmitting}
                className="auth-input"
              />
            </div>
          </div>

          {/* Interactive password complexity checks */}
          {password.length > 0 && (
            <div className="password-rules-box">
              <div className="rule-item">
                {isMinLength ? (
                  <CheckCircle2 size={14} className="rule-success-icon" />
                ) : (
                  <XCircle size={14} className="rule-error-icon" />
                )}
                <span className={isMinLength ? "rule-checked" : "rule-error"}>
                  At least 8 characters
                </span>
              </div>
              <div className="rule-item">
                {isNotCommon ? (
                  <CheckCircle2 size={14} className="rule-success-icon" />
                ) : (
                  <XCircle size={14} className="rule-error-icon" />
                )}
                <span className={isNotCommon ? "rule-checked" : "rule-error"}>
                  Is not a common password
                </span>
              </div>
              {confirmPassword.length > 0 && (
                <div className="rule-item">
                  {doPasswordsMatch ? (
                    <CheckCircle2 size={14} className="rule-success-icon" />
                  ) : (
                    <XCircle size={14} className="rule-error-icon" />
                  )}
                  <span
                    className={doPasswordsMatch ? "rule-checked" : "rule-error"}
                  >
                    Passwords match
                  </span>
                </div>
              )}
            </div>
          )}

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={
              isSubmitting ||
              !isMinLength ||
              !isNotCommon ||
              (confirmPassword.length > 0 && !doPasswordsMatch)
            }
          >
            {isSubmitting ? (
              <span className="btn-content">
                <span className="spinner-small"></span> Creating Account...
              </span>
            ) : (
              <span className="btn-content">
                Get Started <ArrowRight size={18} className="btn-arrow" />
              </span>
            )}
          </button>
        </form>

        <div className="auth-footer">
          <p>
            Already have an account?{" "}
            <Link to="/login" className="auth-link">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};
