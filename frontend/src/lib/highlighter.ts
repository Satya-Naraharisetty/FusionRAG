/**
 * Lazy-loading syntax highlighter built on shiki's core API.
 *
 * Importing from `shiki` (the main entry) statically bundles every language
 * grammar (~1.5 MB). Instead we use `shiki/core` + the JS regex engine and
 * dynamically import individual grammars (`shiki/langs/<name>.mjs`) on first
 * use, so the initial bundle only carries the highlighter skeleton.
 */
import { createHighlighterCore, type HighlighterCore } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import type { LanguageRegistration, ThemeRegistrationAny } from "shiki";
// Static import is fine — a single theme is small (~30 kB gzip).
import githubDark from "shiki/themes/github-dark-default.mjs";
import { createLruCache } from "./utils";

// Rendered HTML is deterministic for a given (code, language), so cache the
// result: re-rendering the same block (conversation switch, remount, theme
// change elsewhere in the app) skips the whole pipeline. Shiki also memoizes
// internally, but its cache is unbounded — this LRU bounds memory to 50
// entries and lets aliases (js vs javascript) share one entry.
// Worst case a large block renders to hundreds of KB of HTML, so 50 entries
// can reach a few MB — acceptable for a chat app. The theme is a module-level
// constant, so cached entries never go stale; bump the key if that changes.
const HIGHLIGHT_CACHE = createLruCache<string, string>(50);

type LangModule = () => Promise<{ default: unknown }>;

/** Languages we support, loaded on demand. Each entry becomes a lazy chunk.
 *  Note: "text"/"plaintext" are built into shiki core — no grammar file. */
const LANG_LOADERS: Record<string, LangModule> = {
  javascript: () => import("shiki/langs/javascript.mjs"),
  typescript: () => import("shiki/langs/typescript.mjs"),
  jsx: () => import("shiki/langs/jsx.mjs"),
  tsx: () => import("shiki/langs/tsx.mjs"),
  python: () => import("shiki/langs/python.mjs"),
  json: () => import("shiki/langs/json.mjs"),
  jsonc: () => import("shiki/langs/jsonc.mjs"),
  bash: () => import("shiki/langs/bash.mjs"),
  html: () => import("shiki/langs/html.mjs"),
  css: () => import("shiki/langs/css.mjs"),
  scss: () => import("shiki/langs/scss.mjs"),
  markdown: () => import("shiki/langs/markdown.mjs"),
  yaml: () => import("shiki/langs/yaml.mjs"),
  sql: () => import("shiki/langs/sql.mjs"),
  java: () => import("shiki/langs/java.mjs"),
  c: () => import("shiki/langs/c.mjs"),
  cpp: () => import("shiki/langs/cpp.mjs"),
  csharp: () => import("shiki/langs/csharp.mjs"),
  go: () => import("shiki/langs/go.mjs"),
  rust: () => import("shiki/langs/rust.mjs"),
  ruby: () => import("shiki/langs/ruby.mjs"),
  php: () => import("shiki/langs/php.mjs"),
  swift: () => import("shiki/langs/swift.mjs"),
  kotlin: () => import("shiki/langs/kotlin.mjs"),
  dockerfile: () => import("shiki/langs/dockerfile.mjs"),
  diff: () => import("shiki/langs/diff.mjs"),
  xml: () => import("shiki/langs/xml.mjs"),
  graphql: () => import("shiki/langs/graphql.mjs"),
  toml: () => import("shiki/langs/toml.mjs"),
  ini: () => import("shiki/langs/ini.mjs"),
  powershell: () => import("shiki/langs/powershell.mjs"),
};

/** Common fence labels -> canonical shiki language names. */
const ALIASES: Record<string, string> = {
  js: "javascript", node: "javascript", nodejs: "javascript", mjs: "javascript", cjs: "javascript",
  ts: "typescript",
  py: "python",
  sh: "bash", shell: "bash", shellscript: "bash", zsh: "bash",
  yml: "yaml",
  md: "markdown",
  h: "c", hpp: "cpp", cc: "cpp", cxx: "cpp", "c++": "cpp",
  cs: "csharp", "c#": "csharp",
  rs: "rust",
  rb: "ruby",
  kt: "kotlin", kts: "kotlin",
  ps1: "powershell",
  txt: "text", plain: "text",
};

const githubDarkTheme = githubDark as ThemeRegistrationAny;

let highlighterPromise: Promise<HighlighterCore> | null = null;
const loadingLangs = new Map<string, Promise<void>>();

function getHighlighter(): Promise<HighlighterCore> {
  if (!highlighterPromise) {
    // Reset on failure so a transient init error is retried on next call
    // instead of being cached as a rejected promise forever.
    highlighterPromise = createHighlighterCore({
      themes: [githubDarkTheme],
      langs: [],
      engine: createJavaScriptRegexEngine(),
    }).catch((err) => {
      highlighterPromise = null;
      throw err;
    });
  }
  return highlighterPromise;
}

function ensureLanguage(name: string): Promise<void> {
  let pending = loadingLangs.get(name);
  if (!pending) {
    pending = (async () => {
      const highlighter = await getHighlighter();
      const mod = await LANG_LOADERS[name]();
      await highlighter.loadLanguage(mod as { default: LanguageRegistration });
    })().catch((err) => {
      // Drop the failed entry so a later call retries the (maybe transient)
      // failure instead of permanently falling back to plain text.
      loadingLangs.delete(name);
      throw err;
    });
    loadingLangs.set(name, pending);
  }
  return pending;
}

/**
 * Highlight `code` in the given fence language. Returns an HTML string.
 * Unknown or unsupported languages fall back to escaped plain text so a
 * grammar failure never breaks rendering.
 */
export async function highlightCode(code: string, language: string): Promise<string> {
  const raw = (language || "text").trim().toLowerCase();
  // Canonical language: aliases (js vs javascript) share a cache entry.
  const lang = ALIASES[raw] ?? (LANG_LOADERS[raw] ? raw : "text");
  // JSON.stringify is collision-free: the key can never overlap a code string.
  const key = JSON.stringify([lang, code]);

  const cached = HIGHLIGHT_CACHE.get(key);
  if (cached !== undefined) return cached;

  try {
    // "text" is a shiki core built-in — no grammar to load.
    if (lang !== "text") {
      await ensureLanguage(lang);
    }
    const highlighter = await getHighlighter();
    const html = highlighter.codeToHtml(code, { lang, theme: githubDarkTheme });
    // Cache only successful highlights; failures fall back to plain text and
    // stay cheap to recompute.
    HIGHLIGHT_CACHE.set(key, html);
    return html;
  } catch {
    // Match shiki's normal output shape (incl. tabindex for keyboard scroll).
    return `<pre class="shiki" tabindex="0"><code>${escapeHtml(code)}</code></pre>`;
  }
}

/** Drop all cached highlight results (e.g. tests, or after a theme change). */
export function clearHighlightCache(): void {
  HIGHLIGHT_CACHE.clear();
}

/** Number of entries currently cached (diagnostics/tests). */
export function getHighlightCacheSize(): number {
  return HIGHLIGHT_CACHE.size;
}

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
