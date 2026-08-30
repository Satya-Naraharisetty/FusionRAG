export interface StrengthResult {
  score: number; // 0 to 4
  label: string; // "Very Weak" | "Weak" | "Medium" | "Strong" | "Very Strong"
  color: string; // e.g., "bg-red-500", "bg-amber-500", "bg-emerald-500"
  feedback: string;
}

export const checkPasswordStrength = (password?: string | null): StrengthResult => {
  if (!password || typeof password !== "string") {
    return { score: 0, label: "Very Weak", color: "bg-red-650", feedback: "Please enter a password." };
  }

  let score = 0;
  const warnings: string[] = [];

  // Length check
  if (password.length >= 8) {
    score += 1;
  } else {
    warnings.push("Choose a longer password.");
  }

  // Complexity checks
  const hasLower = /[a-z]/.test(password);
  const hasUpper = /[A-Z]/.test(password);
  const hasDigit = /[0-9]/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);

  if (hasLower && hasUpper) {
    score += 1;
  } else {
    warnings.push("Mix uppercase and lowercase letters.");
  }

  if (hasDigit) {
    score += 1;
  } else {
    warnings.push("Include at least one number.");
  }

  if (hasSpecial) {
    score += 1;
  } else {
    warnings.push("Include a special character.");
  }

  // Dictionary check for extremely common values
  const commonPasswords = ["password", "password123", "12345678", "admin123", "hybridrag"];
  if (commonPasswords.includes(password.toLowerCase())) {
    score = Math.max(0, score - 2); // penalize heavily
    return {
      score: 1,
      label: "Very Weak",
      color: "bg-red-650",
      feedback: "This is a very common password.",
    };
  }

  // Labels and colors mapping
  const results: Record<number, Omit<StrengthResult, "feedback">> = {
    0: { score: 0, label: "Very Weak", color: "bg-red-650" },
    1: { score: 1, label: "Weak", color: "bg-red-500" },
    2: { score: 2, label: "Medium", color: "bg-amber-500" },
    3: { score: 3, label: "Strong", color: "bg-emerald-500" },
    4: { score: 4, label: "Very Strong", color: "bg-emerald-450" },
  };

  const currentResult = results[Math.min(4, Math.max(0, score))];
  const feedbackMessage = warnings.length > 0 ? warnings[0] : "Your password is secure!";

  return {
    ...currentResult,
    feedback: feedbackMessage,
  };
};
