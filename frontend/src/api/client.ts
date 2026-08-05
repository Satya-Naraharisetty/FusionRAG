import axios from "axios";
import { SSEEvent, SSEEventType } from "../types";

// Base API configuration
const api = axios.create({
  baseURL:
    (import.meta.env.VITE_API_URL || "http://localhost:8000") + "/api/v1",
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

let accessToken: string | null = null;
let onTokenRefreshed: ((token: string) => void) | null = null;
let onAuthFailure: (() => void) | null = null;

export const setAccessToken = (token: string | null) => {
  accessToken = token;
};

export const getAccessToken = () => accessToken;

export const registerTokenRefreshHandler = (handler: (token: string) => void) => {
  onTokenRefreshed = handler;
};

export const registerAuthFailureHandler = (handler: () => void) => {
  onAuthFailure = handler;
};

// Request Interceptor to inject bearer token
api.interceptors.request.use(
  (config) => {
    const token = getAccessToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

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

// Response Interceptor for handling 401 and silent refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Do not attempt to refresh if the request failed was the refresh endpoint itself
    if (originalRequest.url?.includes("/auth/refresh")) {
      return Promise.reject(error);
    }

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return api(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      isRefreshing = true;

      try {
        const response = await api.post("/auth/refresh");
        const { access_token } = response.data;

        setAccessToken(access_token);
        originalRequest.headers.Authorization = `Bearer ${access_token}`;

        if (onTokenRefreshed) {
          onTokenRefreshed(access_token);
        }

        processQueue(null, access_token);
        isRefreshing = false;

        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        isRefreshing = false;

        if (onAuthFailure) {
          onAuthFailure();
        }
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

/**
 * Creates an SSE Stream generator using native fetch, attaching the Authorization header.
 */
export async function* createSSEStream(
  path: string,
  body: object,
  signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const url = ((import.meta.env.VITE_API_URL || "http://localhost:8000") + "/api/v1" + path);

  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });

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
        currentData += trimmed.slice(5).trim();
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

export default api;
