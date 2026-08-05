/**
 * Analytics utility stubs. Exposes standard tracking interface.
 */

export const track = (event: string, properties?: Record<string, unknown>): void => {
  // Safe warning/check in dev mode
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.warn(`[Analytics Track] ${event}`, properties);
  }
};

export const identify = (userId: string, traits?: Record<string, unknown>): void => {
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.warn(`[Analytics Identify] User: ${userId}`, traits);
  }
};

export const page = (name: string): void => {
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.warn(`[Analytics Page] Viewed: ${name}`);
  }
};
