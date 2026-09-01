import "@testing-library/jest-dom";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./handlers";

// Establish API mocking before all tests.
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));

// Reset any request handlers that we may add during the tests,
// so they don't affect other tests.
afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
});

// Clean up after the tests are finished.
afterAll(() => server.close());

// Mocking BroadcastChannel for jsdom
if (typeof window !== "undefined" && !("BroadcastChannel" in window)) {
  class MockBroadcastChannel {
    name: string;
    onmessage: ((event: MessageEvent) => void) | null = null;
    constructor(name: string) {
      this.name = name;
    }
    postMessage() {}
    close() {}
    addEventListener() {}
    removeEventListener() {}
    dispatchEvent() {
      return true;
    }
  }
  (window as unknown as { BroadcastChannel: unknown }).BroadcastChannel = MockBroadcastChannel;
}

// Mocking window.matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {}, // Deprecated
    removeListener: () => {}, // Deprecated
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
