import api, { setAccessToken, executeRefresh } from "./client";

export interface UserResponse {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
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

  deleteAccount(password: string): Promise<void> {
    // The backend requires the password to be re-entered (account-takeover
    // protection). `api.delete` passes the body through raw, so stringify here.
    return api.delete("/auth/account", {
      body: JSON.stringify({ password }),
    });
  },
};
