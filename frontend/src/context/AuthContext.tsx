import React, { createContext, useCallback, useEffect, useRef, useState } from "react";
import {
  getAccessToken,
  registerAuthFailureHandler,
  registerTokenRefreshHandler,
  setAccessToken,
} from "../services/api";
import { authApi, UserResponse } from "../services/auth";

export interface AuthContextType {
  user: UserResponse | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: () => void;
  loginWithGithub: () => void;
  register: (email: string, password: string) => Promise<void>;
  verifyEmail: (params: { token?: string; email?: string; otp?: string }) => Promise<void>;
  resendVerification: (email: string) => Promise<{ message: string }>;
  logout: () => Promise<void>;
  updatePassword: (newPassword: string, currentPassword?: string) => Promise<void>;
  deleteAccount: (password?: string) => Promise<void>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [accessToken, setAccessTokenState] = useState<string | null>(getAccessToken());
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const refreshTimerRef = useRef<number | null>(null);

  // Clear existing refresh timer
  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current) {
      window.clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  // Schedule next silent token rotation before current access token expires
  const scheduleRefresh = useCallback(
    (expiresInSeconds: number) => {
      clearRefreshTimer();

      // Attempt to refresh 60 seconds before expiration
      const refreshInMs = Math.max((expiresInSeconds - 60) * 1000, 10000);

      const timer = window.setTimeout(async () => {
        try {
          const response = await authApi.refresh();
          const updatedUser = await authApi.getMe();
          setUser(updatedUser);
          setAccessTokenState(response.access_token);
          scheduleRefresh(response.expires_in);
        } catch (err) {
          console.error("Failed to automatically refresh token:", err);
          setUser(null);
          setAccessTokenState(null);
          setAccessToken(null);
          clearRefreshTimer();
        }
      }, refreshInMs);

      if (
        typeof timer === "object" &&
        timer !== null &&
        "unref" in timer &&
        typeof (timer as { unref?: () => void }).unref === "function"
      ) {
        (timer as { unref: () => void }).unref();
      }

      refreshTimerRef.current = timer as unknown as number;
    },
    [clearRefreshTimer],
  );

  const login = async (email: string, password: string) => {
    try {
      const response = await authApi.login(email, password);
      setAccessTokenState(response.access_token);
      const userProfile = await authApi.getMe();
      setUser(userProfile);
      scheduleRefresh(response.expires_in);
    } catch (err) {
      setUser(null);
      setAccessTokenState(null);
      setAccessToken(null);
      clearRefreshTimer();
      throw err;
    }
  };

  const register = async (email: string, password: string) => {
    await authApi.register(email, password);
  };

  const verifyEmail = async (params: { token?: string; email?: string; otp?: string }) => {
    try {
      const response = await authApi.verifyEmail(params);
      setAccessTokenState(response.access_token);
      const userProfile = await authApi.getMe();
      setUser(userProfile);
      scheduleRefresh(response.expires_in);
    } catch (err) {
      setUser(null);
      setAccessTokenState(null);
      setAccessToken(null);
      clearRefreshTimer();
      throw err;
    }
  };

  const resendVerification = async (email: string) => {
    return authApi.resendVerification(email);
  };

  const logout = useCallback(async () => {
    setIsLoading(true);
    try {
      await authApi.logout();
    } catch (err) {
      console.error("Logout request failed:", err);
    } finally {
      setUser(null);
      setAccessTokenState(null);
      setAccessToken(null);
      clearRefreshTimer();
      setIsLoading(false);
    }
  }, [clearRefreshTimer]);

  const updatePassword = useCallback(async (newPassword: string, currentPassword?: string) => {
    setIsLoading(true);
    try {
      await authApi.updatePassword(newPassword, currentPassword);
      const updatedUser = await authApi.getMe();
      setUser(updatedUser);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const deleteAccount = useCallback(
    async (password?: string) => {
      setIsLoading(true);
      try {
        await authApi.deleteAccount(password);
        // Session state is now invalid server-side; clear it locally so
        // ProtectedRoute immediately bounces the user back to /login.
        // Errors propagate to the caller so the UI can show a failure toast.
        setUser(null);
        setAccessTokenState(null);
        setAccessToken(null);
        clearRefreshTimer();
      } finally {
        setIsLoading(false);
      }
    },
    [clearRefreshTimer],
  );

  // Handle initialization and callback sync from Axios interceptors
  useEffect(() => {
    let active = true;

    const initAuth = async () => {
      const storedToken = getAccessToken();
      if (storedToken) {
        try {
          // Token is already available in storage: immediately restore profile
          const userProfile = await authApi.getMe();
          if (active) {
            setUser(userProfile);
            setAccessTokenState(storedToken);
            setIsLoading(false);
          }
          return;
        } catch {
          // Stored token was expired/invalid; fall through to cookie refresh
        }
      }

      try {
        const response = await authApi.refresh();
        if (active) {
          setAccessToken(response.access_token);
          setAccessTokenState(response.access_token);
          const userProfile = await authApi.getMe();
          setUser(userProfile);
          scheduleRefresh(response.expires_in);
        }
      } catch (_err) {
        if (active) {
          setUser(null);
          setAccessTokenState(null);
          setAccessToken(null);
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };

    initAuth();

    // Register hooks to keep local React state in sync with Axios interceptor events
    registerTokenRefreshHandler((newToken) => {
      if (active) {
        setAccessTokenState(newToken);
      }
    });

    registerAuthFailureHandler(() => {
      if (active) {
        setUser(null);
        setAccessTokenState(null);
        setAccessToken(null);
        clearRefreshTimer();
      }
    });

    // Listen for OAuth completion messages from popup windows

    const handleOAuthMessage = async (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === "OAUTH_SUCCESS") {
        try {
          setIsLoading(true);
          const incomingToken = event.data?.token;
          if (incomingToken) {
            setAccessToken(incomingToken);
            setAccessTokenState(incomingToken);
          } else {
            const response = await authApi.refresh();
            setAccessToken(response.access_token);
            setAccessTokenState(response.access_token);
            scheduleRefresh(response.expires_in);
          }
          const userProfile = await authApi.getMe();
          setUser(userProfile);
        } catch (err) {
          console.error("Failed to complete OAuth popup session:", err);
        } finally {
          setIsLoading(false);
        }
      }
    };

    window.addEventListener("message", handleOAuthMessage);

    return () => {
      active = false;
      window.removeEventListener("message", handleOAuthMessage);
      clearRefreshTimer();
    };
  }, [scheduleRefresh, clearRefreshTimer]);

  const loginWithGoogle = () => {
    authApi.loginWithGoogle();
  };

  const loginWithGithub = () => {
    authApi.loginWithGithub();
  };

  const value: AuthContextType = {
    user,
    accessToken,
    isAuthenticated: !!accessToken,
    isLoading,
    login,
    loginWithGoogle,
    loginWithGithub,
    register,
    verifyEmail,
    resendVerification,
    logout,
    updatePassword,
    deleteAccount,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
