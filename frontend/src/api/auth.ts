import api, { setAccessToken, executeRefresh } from "./client";

export interface UserResponse {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
  oauth_provider: string | null;
  has_password: boolean;
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
}

export const authApi = {
  register(email: string, password: string): Promise<UserResponse> {
    return api.post<UserResponse>("/auth/register", {
      email,
      password,
    });
  },

  async login(email: string, password: string): Promise<TokenResponse> {
    const data = await api.post<TokenResponse>("/auth/login", {
      email,
      password,
    });
    // Store in-memory access token
    setAccessToken(data.access_token);
    return data;
  },

  async verifyEmail(params: {
    token?: string;
    email?: string;
    otp?: string;
  }): Promise<TokenResponse> {
    const data = await api.post<TokenResponse>("/auth/verify-email", params);
    // Store in-memory access token
    setAccessToken(data.access_token);
    return data;
  },

  resendVerification(email: string): Promise<{ message: string }> {
    return api.post<{ message: string }>("/auth/resend-verification", {
      email,
    });
  },

  refresh(): Promise<TokenResponse> {
    return executeRefresh();
  },

  async logout(): Promise<void> {
    try {
      await api.post("/auth/logout");
    } finally {
      // Clear in-memory token regardless of API result
      setAccessToken(null);
    }
  },

  getMe(): Promise<UserResponse> {
    return api.get<UserResponse>("/auth/me");
  },

  updatePassword(newPassword: string, currentPassword?: string): Promise<{ message: string }> {
    return api.post<{ message: string }>("/auth/password", {
      new_password: newPassword,
      ...(currentPassword ? { current_password: currentPassword } : {}),
    });
  },

  deleteAccount(password?: string): Promise<void> {
    // The backend requires the password to be re-entered if the user has one.
    // `api.delete` passes the body through raw, so stringify here.
    return api.delete("/auth/account", {
      body: JSON.stringify(password ? { password } : {}),
    });
  },

  requestMagicLink(email: string): Promise<{ message: string }> {
    return api.post<{ message: string }>("/auth/magic-link", { email });
  },

  openOAuthPopup(provider: "google" | "github"): Window | null {
    const rawBase = (import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
    const apiBase = rawBase.endsWith("/api/v1") ? rawBase.replace(/\/api\/v1$/, "") : rawBase;
    const width = 500;
    const height = 620;
    const left = window.screenX + Math.max(0, (window.outerWidth - width) / 2);
    const top = window.screenY + Math.max(0, (window.outerHeight - height) / 2);
    return window.open(
      `${apiBase}/api/v1/auth/oauth/${provider}`,
      `oauth_${provider}_popup`,
      `width=${width},height=${height},left=${left},top=${top},status=no,resizable=yes,scrollbars=yes`
    );
  },

  loginWithGoogle(): void {
    const popup = this.openOAuthPopup("google");
    if (!popup || popup.closed || typeof popup.closed === "undefined") {
      const rawBase = (import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
      const apiBase = rawBase.endsWith("/api/v1") ? rawBase.replace(/\/api\/v1$/, "") : rawBase;
      window.location.href = `${apiBase}/api/v1/auth/oauth/google`;
    }
  },

  loginWithGithub(): void {
    const popup = this.openOAuthPopup("github");
    if (!popup || popup.closed || typeof popup.closed === "undefined") {
      const rawBase = (import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
      const apiBase = rawBase.endsWith("/api/v1") ? rawBase.replace(/\/api\/v1$/, "") : rawBase;
      window.location.href = `${apiBase}/api/v1/auth/oauth/github`;
    }
  },
};

