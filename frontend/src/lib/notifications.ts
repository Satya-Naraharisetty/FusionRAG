/**
 * Notification & sound preferences for stream-completion alerts.
 * Stored in localStorage so the Settings page toggles and the streaming
 * hook share one source of truth.
 */

export interface NotificationPrefs {
  desktop: boolean;
  sound: boolean;
}

const PREFS_KEY = "notification-prefs";
const DEFAULTS: NotificationPrefs = { desktop: true, sound: false };

export const getNotificationPrefs = (): NotificationPrefs => {
  if (typeof window === "undefined") return { ...DEFAULTS };
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
};

export const setNotificationPrefs = (prefs: NotificationPrefs): void => {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
};

export const isNotificationSupported = (): boolean =>
  typeof window !== "undefined" && "Notification" in window;

export const ensureNotificationPermission = async (): Promise<NotificationPermission> => {
  if (!isNotificationSupported()) return "default";
  if (Notification.permission !== "default") return Notification.permission;
  try {
    return await Notification.requestPermission();
  } catch {
    return "default";
  }
};

export const notifyStreamComplete = (opts: { title: string; body?: string }): void => {
  if (!isNotificationSupported() || Notification.permission !== "granted") return;
  try {
    const n = new Notification(opts.title, { body: opts.body, silent: true });
    setTimeout(() => n.close(), 6000);
  } catch {
    /* Best effort — some environments (e.g. cross-origin iframes) throw. */
  }
};

/** Soft two-note chime via WebAudio. Best effort: needs a user gesture to start. */
let audioCtx: AudioContext | null = null;

export const playChime = (): void => {
  try {
    const w = window as Window & { webkitAudioContext?: typeof AudioContext };
    const Ctor = window.AudioContext || w.webkitAudioContext;
    if (!Ctor) return;
    audioCtx = audioCtx || new Ctor();
    if (audioCtx.state === "suspended") void audioCtx.resume();

    const now = audioCtx.currentTime;
    [660, 880].forEach((freq, i) => {
      const osc = audioCtx!.createOscillator();
      const gain = audioCtx!.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      const start = now + i * 0.12;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.05, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.35);
      osc.connect(gain).connect(audioCtx!.destination);
      osc.start(start);
      osc.stop(start + 0.4);
    });
  } catch {
    /* Best effort. */
  }
};

/** Fire the enabled stream-complete alerts (desktop notification + chime). */
export const maybeNotifyStreamComplete = (opts: { title: string; body?: string }): void => {
  const prefs = getNotificationPrefs();
  if (prefs.desktop) notifyStreamComplete(opts);
  if (prefs.sound) playChime();
};
