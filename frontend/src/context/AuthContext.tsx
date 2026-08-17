import React, {
  createContext,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
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
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  deleteAccount: (password: string) => Promise<void>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextType | undefined>(
  undefined
);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [accessToken, setAccessTokenState] = useState<string | null>(null);
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

      refreshTimerRef.current = window.setTimeout(async () => {
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
    },
    [clearRefreshTimer]
  );

  const login = async (email: string, password: string) => {
    setIsLoading(true);
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
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      await authApi.register(email, password);
      // Automatically log user in upon successful registration
      await login(email, password);
    } catch (err) {
      setIsLoading(false);
      throw err;
    }
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

  const deleteAccount = useCallback(async (password: string) => {
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
  }, [clearRefreshTimer]);

  // Handle initialization and callback sync from Axios interceptors
  useEffect(() => {
    let active = true;

    const initAuth = async () => {
      try {
        const response = await authApi.refresh();
        if (active) {
          setAccessTokenState(response.access_token);
          const userProfile = await authApi.getMe();
          setUser(userProfile);
          scheduleRefresh(response.expires_in);
        }
      } catch (err) {
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

    return () => {
      active = false;
      clearRefreshTimer();
    };
  }, [scheduleRefresh, clearRefreshTimer]);

  const loginWithGoogle = () => {
    authApi.loginWithGoogle();
  };

  const value: AuthContextType = {
    user,
    accessToken,
    isAuthenticated: !!accessToken,
    isLoading,
    login,
    loginWithGoogle,
    register,
    logout,
    deleteAccount,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
