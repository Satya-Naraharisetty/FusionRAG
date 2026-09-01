import { beforeEach, describe, expect, it } from "vitest";
import {
  clearHighlightCache,
  escapeHtml,
  getHighlightCacheSize,
  highlightCode,
} from "../lib/highlighter";
import { createLruCache } from "../lib/utils";

describe("highlightCode", () => {
  it("falls back to escaped plain text for unknown languages", async () => {
    const out = await highlightCode("<script>alert(1)</script>", "definitely-not-a-lang");
    expect(out).toContain('class="shiki');
    // shiki v4 escapes '<' as the hex entity &#x3C; — the important part is no raw tag survives
    expect(out).not.toContain("<script>alert");
    expect(out).not.toContain("</script>");
    expect(out).toContain("&#x3C;script>alert(1)&#x3C;/script>");
  });

  it("highlights supported languages with token spans", async () => {
    const out = await highlightCode("const x: number = 1;", "ts");
    expect(out).toContain('class="shiki');
    expect(out).toContain("<code");
    expect(out).toContain("const");
    // alias "ts" -> typescript produced real tokens, not escaped plain text
    expect(out).toContain("<span");
  });

  it("handles plain text without loading a grammar", async () => {
    const out = await highlightCode("just some text", "text");
    expect(out).toContain("just some text");
  });

  it("escapes HTML entities", () => {
    expect(escapeHtml(`<a href="x">'&'</a>`)).toBe(
      "&lt;a href=&quot;x&quot;&gt;&#039;&amp;&#039;&lt;/a&gt;",
    );
  });

  it("returns the cached result for the same code + language (no recompute)", async () => {
    const first = await highlightCode("const x = 1;", "ts");
    const sizeAfterFirst = getHighlightCacheSize();
    const second = await highlightCode("const x = 1;", "ts");
    expect(second).toEqual(first);
    // The second call was a cache hit: no new entry was added.
    expect(getHighlightCacheSize()).toBe(sizeAfterFirst);
  });

  it("shares cache entries across language aliases", async () => {
    const before = getHighlightCacheSize();
    const viaAlias = await highlightCode("let y: number = 2;", "js");
    const viaCanonical = await highlightCode("let y: number = 2;", "javascript");
    expect(viaCanonical).toEqual(viaAlias);
    // One entry serves both the alias and the canonical name.
    expect(getHighlightCacheSize()).toBe(before + 1);
  });

  it("does not return a cached result for different code", async () => {
    const one = await highlightCode("const a = 1;", "ts");
    const two = await highlightCode("const b = 2;", "ts");
    expect(two).not.toEqual(one);
  });

  it("bounds the highlight cache to its capacity", async () => {
    // Capacity is 50; pushing more distinct blocks than that must cap the size.
    const before = getHighlightCacheSize();
    await highlightCode("block-0", "text");
    for (let i = 1; i <= 50; i++) {
      await highlightCode(`block-${i}`, "text");
    }
    expect(getHighlightCacheSize()).toBe(Math.min(before + 51, 50));
  });
});

describe("createLruCache", () => {
  it("returns undefined for missing keys", () => {
    const cache = createLruCache<string, number>(3);
    expect(cache.get("nope")).toBeUndefined();
    expect(cache.has("nope")).toBe(false);
  });

  it("stores and returns values, tracking size", () => {
    const cache = createLruCache<string, number>(3);
    cache.set("a", 1);
    cache.set("b", 2);
    expect(cache.size).toBe(2);
    expect(cache.get("a")).toBe(1);
    expect(cache.has("b")).toBe(true);
  });

  it("evicts the least recently used entry when full", () => {
    const cache = createLruCache<string, number>(3);
    cache.set("a", 1);
    cache.set("b", 2);
    cache.set("c", 3);
    cache.set("d", 4); // evicts "a" (oldest)
    expect(cache.get("a")).toBeUndefined();
    expect(cache.get("b")).toBe(2);
    expect(cache.get("c")).toBe(3);
    expect(cache.get("d")).toBe(4);
    expect(cache.size).toBe(3);
  });

  it("refreshes recency on get, protecting the entry from eviction", () => {
    const cache = createLruCache<string, number>(3);
    cache.set("a", 1);
    cache.set("b", 2);
    cache.set("c", 3);
    cache.get("a"); // "a" is now most recent
    cache.set("d", 4); // evicts "b" (now the oldest)
    expect(cache.get("a")).toBe(1);
    expect(cache.get("b")).toBeUndefined();
    expect(cache.get("d")).toBe(4);
  });

  it("updates in place and clears", () => {
    const cache = createLruCache<string, number>(3);
    cache.set("a", 1);
    cache.set("a", 2);
    expect(cache.size).toBe(1);
    expect(cache.get("a")).toBe(2);
    cache.clear();
    expect(cache.size).toBe(0);
    expect(cache.get("a")).toBeUndefined();
  });
});

describe("clearHighlightCache", () => {
  beforeEach(() => {
    clearHighlightCache();
  });

  it("forces recomputation on the next call", async () => {
    const first = await highlightCode("const c = 3;", "ts");
    const hit = await highlightCode("const c = 3;", "ts");
    expect(hit).toEqual(first);
    clearHighlightCache();
    expect(getHighlightCacheSize()).toBe(0);
    const recomputed = await highlightCode("const c = 3;", "ts");
    expect(recomputed).toEqual(first);
    expect(getHighlightCacheSize()).toBe(1);
  });
});
