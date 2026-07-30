import api from "./api";
import { setAccessToken } from "./api";

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
  async register(email: string, password: string): Promise<UserResponse> {
    const response = await api.post<UserResponse>("/auth/register", {
      email,
      password,
    });
    return response.data;
  },

  async login(email: string, password: string): Promise<TokenResponse> {
    const response = await api.post<TokenResponse>("/auth/login", {
      email,
      password,
    });
    // Store in-memory access token
    setAccessToken(response.data.access_token);
    return response.data;
  },

  async refresh(): Promise<TokenResponse> {
    const response = await api.post<TokenResponse>("/auth/refresh");
    setAccessToken(response.data.access_token);
    return response.data;
  },

  async logout(): Promise<void> {
    try {
      await api.post("/auth/logout");
    } finally {
      // Clear in-memory token regardless of API result
      setAccessToken(null);
    }
  },

  async getMe(): Promise<UserResponse> {
    const response = await api.get<UserResponse>("/auth/me");
    return response.data;
  },
};
