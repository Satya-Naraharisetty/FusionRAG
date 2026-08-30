import { SSEEvent, SSEEventType } from "../types";

// Base API configuration
const envUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL;
const rawBase = (envUrl !== undefined && envUrl !== "" ? envUrl : (import.meta.env.DEV ? "http://localhost:8000" : "")).replace(/\/$/, "");
const BASE_URL = rawBase.endsWith("/api/v1") ? rawBase : `${rawBase}/api/v1`;

export interface TokenResponse {
  access_token: string;
  expires_in: number;
}

const TOKEN_KEY = "fusionrag_access_token";

let accessToken: string | null =
  typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;

let onTokenRefreshed: ((token: string) => void) | null = null;
let onAuthFailure: (() => void) | null = null;
let activeRefreshPromise: Promise<TokenResponse> | null = null;

export const setAccessToken = (token: string | null) => {
  accessToken = token;
  if (typeof window !== "undefined") {
    try {
      if (token) {
        localStorage.setItem(TOKEN_KEY, token);
      } else {
        localStorage.removeItem(TOKEN_KEY);
      }
    } catch {
      // Ignore storage errors in restricted contexts
    }
  }
};

export const getAccessToken = () => {
  if (!accessToken && typeof window !== "undefined") {
    try {
      accessToken = localStorage.getItem(TOKEN_KEY);
    } catch {
      // Ignore
    }
  }
  return accessToken;
};

export const registerTokenRefreshHandler = (handler: (token: string) => void) => {
  onTokenRefreshed = handler;
};

export const registerAuthFailureHandler = (handler: () => void) => {
  onAuthFailure = handler;
};

export const executeRefresh = async (): Promise<TokenResponse> => {
  if (activeRefreshPromise) {
    return activeRefreshPromise;
  }

  activeRefreshPromise = (async () => {
    const response = await fetch(`${BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = (await response.json()) as TokenResponse;
    setAccessToken(data.access_token);
    return data;
  })().finally(() => {
    activeRefreshPromise = null;
  });

  return activeRefreshPromise;
};

/**
 * Error thrown by the API layer. `data` carries the parsed response body and
 * `status` the HTTP code, so callers can show the backend's message.
 */
export interface ApiError extends Error {
  status: number;
  data: unknown;
}

function toApiError(status: number, data: unknown, fallback: string): ApiError {
  const detail = (data as { detail?: unknown } | null)?.detail;
  const message =
    (data as { message?: string } | null)?.message ||
    // FastAPI validation errors carry `detail` as an array — only use it when it's a string.
    (typeof detail === "string" ? detail : undefined) ||
    (data as { error?: { message?: string } } | null)?.error?.message ||
    fallback;
  const err = new Error(message) as ApiError;
  err.status = status;
  err.data = data;
  return err;
}

async function parseError(response: Response): Promise<ApiError> {
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = undefined;
  }
  return toApiError(response.status, data, `HTTP ${response.status}`);
}

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | null | undefined>;
}

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (token) {
      prom.resolve(token);
    } else {
      prom.reject(error);
    }
  });
  failedQueue = [];
};

async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const { params, ...requestInit } = init;
  let url = `${BASE_URL}${path}`;
  if (params) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) search.set(key, String(value));
    });
    const qs = search.toString();
    if (qs) url += `?${qs}`;
  }

  const doFetch = (token: string | null): Promise<Response> => {
    const headers = new Headers(requestInit.headers);
    // JSON bodies are stringified by the api helpers; never override the
    // Content-Type for FormData/other body types.
    if (typeof requestInit.body === "string" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    return fetch(url, { ...requestInit, headers, credentials: "include" });
  };

  let response = await doFetch(getAccessToken());

  // Single 401 retry: refresh the token once, then replay.
  // Never attempt to refresh on auth endpoints (login, register, refresh, oauth) where 401 is an expected credential error.
  const isAuthEndpoint =
    path.includes("/auth/login") ||
    path.includes("/auth/register") ||
    path.includes("/auth/refresh") ||
    path.includes("/auth/oauth") ||
    path.includes("/auth/verify-email") ||
    path.includes("/auth/resend-verification");

  if (response.status === 401 && !isAuthEndpoint) {
    if (isRefreshing) {
      const token = await new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      });
      response = await doFetch(token);
    } else {
      isRefreshing = true;
      try {
        const tokenResponse = await executeRefresh();
        processQueue(null, tokenResponse.access_token);
        if (onTokenRefreshed) {
          onTokenRefreshed(tokenResponse.access_token);
        }
        response = await doFetch(tokenResponse.access_token);
      } catch (refreshError) {
        processQueue(refreshError, null);
        if (onAuthFailure) {
          onAuthFailure();
        }
        throw refreshError;
      } finally {
        isRefreshing = false;
      }
    }
  }

  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  if (!text) {
    return undefined as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    return undefined as T;
  }
}

/** Minimal fetch-based HTTP client mirroring the old axios surface. */
export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, {
      ...options,
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, {
      ...options,
      method: "PUT",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, {
      ...options,
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  delete: <T = void>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "DELETE" }),
};

export default api;

/**
 * Creates an SSE Stream generator using native fetch, attaching the Authorization header.
 */
export async function* createSSEStream(
  path: string,
  body: object,
  signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
  const url = BASE_URL + path;

  const doFetch = (authToken: string | null): Promise<Response> => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (authToken) {
      headers["Authorization"] = `Bearer ${authToken}`;
    }
    return fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal,
      credentials: "include",
    });
  };

  let response = await doFetch(getAccessToken());

  // Automatic token refresh on 401 for idle sessions
  if (response.status === 401) {
    try {
      const tokenResponse = await executeRefresh();
      if (onTokenRefreshed) {
        onTokenRefreshed(tokenResponse.access_token);
      }
      response = await doFetch(tokenResponse.access_token);
    } catch (refreshError) {
      if (onAuthFailure) {
        onAuthFailure();
      }
      throw refreshError;
    }
  }

  if (!response.ok) {
    const errText = await response.text();
    let errJSON: Record<string, unknown> = {};
    try {
      errJSON = JSON.parse(errText);
    } catch (_e) {
      // Ignored
    }
    const errorObj = errJSON.error as Record<string, unknown> | undefined;
    const message = errorObj?.message as string | undefined;
    throw new Error(message || `HTTP ${response.status}: Failed to connect to stream`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("No response body reader available");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent: SSEEventType | null = null;
  let currentData = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    // Keep the last partial line in the buffer
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        // Empty line signals end of event
        if (currentEvent && currentData) {
          try {
            yield {
              event: currentEvent,
              data: JSON.parse(currentData),
            };
          } catch (_e) {
            // parsing error, skip
          }
          currentEvent = null;
          currentData = "";
        }
        continue;
      }

      if (trimmed.startsWith("event:")) {
        currentEvent = trimmed.slice(6).trim() as SSEEventType;
      } else if (trimmed.startsWith("data:")) {
        const chunk = trimmed.slice(5).trim();
        currentData = currentData ? `${currentData}\n${chunk}` : chunk;
      }
    }
  }

  // Handle remaining buffer
  if (buffer) {
    const trimmed = buffer.trim();
    if (trimmed.startsWith("data:") && currentEvent) {
      try {
        yield {
          event: currentEvent,
          data: JSON.parse(trimmed.slice(5).trim()),
        };
      } catch (_e) {
        // ignore
      }
    }
  }
}
