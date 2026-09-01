import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number, decimals = 2) {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
}

export function relativeTime(dateString: string | Date): string {
  try {
    const date = typeof dateString === "string" ? new Date(dateString) : dateString;
    if (isNaN(date.getTime())) return "Unknown date";

    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return "yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch (_e) {
    return "Unknown date";
  }
}

const startOfDay = (d: Date): number =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

/** True if `date` is the current calendar day (local time). */
export function isToday(date: Date): boolean {
  return startOfDay(date) === startOfDay(new Date());
}

/** True if `date` is the previous calendar day (local time). */
export function isYesterday(date: Date): boolean {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  return startOfDay(date) === startOfDay(yesterday);
}

/** True if `date` is strictly after `reference`. */
export function isAfter(date: Date, reference: Date): boolean {
  return date.getTime() > reference.getTime();
}

/** Subtract `amount` days (DST-safe via setDate). */
export function subDays(date: Date, amount: number): Date {
  const copy = new Date(date);
  copy.setDate(copy.getDate() - amount);
  return copy;
}

export function truncate(str: string, maxLength: number): string {
  if (!str) return "";
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength) + "...";
}

export interface LruCache<K, V> {
  get(key: K): V | undefined;
  has(key: K): boolean;
  set(key: K, value: V): void;
  clear(): void;
  readonly size: number;
}

/**
 * Minimal least-recently-used cache backed by a Map. `get`/`set` refresh
 * recency; once full, the least-recently-used entry is evicted.
 */
export function createLruCache<K, V>(capacity: number): LruCache<K, V> {
  const map = new Map<K, V>();
  return {
    get(key) {
      const value = map.get(key);
      if (value === undefined) return undefined;
      // Refresh recency: delete + re-insert moves the entry to the newest slot.
      map.delete(key);
      map.set(key, value);
      return value;
    },
    has(key) {
      return map.has(key);
    },
    set(key, value) {
      if (map.has(key)) map.delete(key);
      map.set(key, value);
      while (map.size > capacity) {
        const oldest = map.keys().next().value;
        if (oldest === undefined) break;
        map.delete(oldest);
      }
    },
    clear() {
      map.clear();
    },
    get size() {
      return map.size;
    },
  };
}
