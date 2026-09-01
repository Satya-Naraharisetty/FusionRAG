/* eslint-disable @typescript-eslint/no-explicit-any */
import { ComponentType, lazy } from "react";

/**
 * Wraps React.lazy with automatic reload on dynamic import failure.
 *
 * When a new deployment occurs on Vercel, old hashed chunk files (e.g. ChatPage-oldHash.js)
 * are removed from the server. If a client is running an older index.html, navigating to a
 * lazy route will fail with a TypeError / 404 chunk error.
 *
 * This wrapper catches that error, triggers a single automatic page reload to fetch the
 * latest index.html with new chunk hashes, and recovers smoothly.
 */
export function lazyWithRetry<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
) {
  return lazy(async () => {
    try {
      const module = await factory();
      window.sessionStorage.removeItem("retry-lazy-refreshed");
      return module;
    } catch (error) {
      const hasReloaded = window.sessionStorage.getItem("retry-lazy-refreshed");
      if (!hasReloaded) {
        window.sessionStorage.setItem("retry-lazy-refreshed", "true");
        window.location.reload();
        return new Promise<{ default: T }>(() => {});
      }
      window.sessionStorage.removeItem("retry-lazy-refreshed");
      throw error;
    }
  });
}
