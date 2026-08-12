import { afterEach, describe, expect, it, vi } from "vitest";
import {
  t,
  setLocale,
  getLocale,
  detectLocale,
  LOCALE_STORAGE_KEY,
} from "../lib/messages";

describe("messages i18n", () => {
  afterEach(() => {
    // Restore the default so other tests (and this file's other cases) always
    // see English copy regardless of run order.
    setLocale("en");
  });

  it("defaults to English for an English browser", () => {
    // jsdom's navigator.language is "en-US", so module-load detection yields
    // English (the static import above already ran the auto-detect).
    expect(getLocale()).toBe("en");
    expect(t("chatFiles.caption")).toContain("Only usable in this chat");
    expect(t("chatFiles.header")).toContain("only this conversation can use them");
    expect(t("chatFiles.tooltip")).toBe("Only this chat can use this file");
    expect(t("chatFiles.removeAria", { filename: "a.pdf" })).toBe(
      "Remove a.pdf from this chat"
    );
    expect(t("chat.placeholderDefault")).toBe("Message Hybrid RAG...");
    expect(t("chat.placeholderStreaming")).toBe("AI is responding...");
    expect(t("chat.placeholderDrop")).toBe("Drop files here to attach...");
    expect(t("commands.documents.label")).toBe("Documents priority");
    expect(t("commands.documents.description")).toBe(
      "Prioritize your uploaded documents"
    );
  });

  it("switches locales end-to-end and back", () => {
    setLocale("fr");
    expect(getLocale()).toBe("fr");
    expect(t("chatFiles.header")).toBe(
      "Fichiers de conversation — seule cette conversation peut les utiliser"
    );
    expect(t("chatFiles.caption")).toBe(
      "Utilisables uniquement dans cette conversation — supprimés avec la conversation."
    );
    expect(t("chatFiles.tooltip")).toBe(
      "Seule cette conversation peut utiliser ce fichier"
    );
    expect(t("chatFiles.removeAria", { filename: "a.pdf" })).toBe(
      "Retirer a.pdf de cette conversation"
    );

    setLocale("en");
    expect(t("chatFiles.header")).toBe(
      "Chat files — only this conversation can use them"
    );
    expect(t("chatFiles.caption")).toBe(
      "Only usable in this chat — deleted with the conversation."
    );
  });

  it("interpolates {params} in messages", () => {
    expect(t("chat.uploadLimit", { max: 5 })).toBe(
      "You can attach up to 5 files per message."
    );
    expect(t("chat.uploadRoomOne", { room: 1, max: 5 })).toBe(
      "Only 1 more attachment can be added (max 5)."
    );
    expect(t("chat.uploadRoomOther", { room: 3, max: 5 })).toBe(
      "Only 3 more attachments can be added (max 5)."
    );
    expect(t("chat.uploadFailed")).toBe("Upload failed");
  });

  it("returns French copy for the migrated composer messages", () => {
    setLocale("fr");
    expect(t("chat.offlineWarning")).toBe(
      "Envoi désactivé — vous êtes hors ligne."
    );
    expect(t("chat.documentMode")).toBe(
      "Mode documents — les réponses privilégieront vos documents téléversés"
    );
    expect(t("chat.uploadLimit", { max: 5 })).toBe(
      "Vous pouvez joindre jusqu'à 5 fichiers par message."
    );
    expect(t("chat.uploadRoomOne", { room: 1, max: 5 })).toBe(
      "Vous pouvez encore ajouter 1 pièce jointe (max 5)."
    );
    expect(t("chat.uploadRoomOther", { room: 3, max: 5 })).toBe(
      "Vous pouvez encore ajouter 3 pièces jointes (max 5)."
    );
    expect(t("chat.uploadFailed")).toBe("Échec du téléversement");
    expect(t("chat.placeholderDefault")).toBe("Écrivez votre message…");
    expect(t("chat.placeholderStreaming")).toBe("L'IA répond…");
    expect(t("chat.placeholderDrop")).toBe("Déposez des fichiers pour les joindre…");
    expect(t("commands.documents.label")).toBe("Priorité documents");
    expect(t("commands.settings.label")).toBe("Paramètres");
    expect(t("commands.code.description")).toBe(
      "Générer ou expliquer du code"
    );
  });

  it("detectLocale maps language tags to supported locales with an English fallback", () => {
    expect(detectLocale("fr-FR")).toBe("fr");
    expect(detectLocale("FR")).toBe("fr");
    expect(detectLocale("en-US")).toBe("en");
    expect(detectLocale("de-DE")).toBe("en");
    expect(detectLocale(undefined)).toBe("en");
  });

  it("auto-detects the locale from navigator.language when nothing is persisted", async () => {
    // Reload the module against a French browser to prove the seed path:
    // getLocale() reflects navigator.language with no setLocale call and an
    // empty storage (earlier tests persist their setLocale choices).
    vi.resetModules();
    localStorage.removeItem(LOCALE_STORAGE_KEY);
    vi.stubGlobal("navigator", { language: "fr-FR" });
    const fresh = await import("../lib/messages");
    expect(fresh.getLocale()).toBe("fr");
    expect(fresh.t("chat.offlineWarning")).toBe(
      "Envoi désactivé — vous êtes hors ligne."
    );
    vi.unstubAllGlobals();
  });

  it("persists setLocale and restores the choice on module reload", async () => {
    setLocale("fr");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("fr");

    // A fresh module instance (as after a page reload) restores the persisted
    // choice even when the browser itself is English.
    vi.resetModules();
    vi.stubGlobal("navigator", { language: "en-US" });
    const fresh = await import("../lib/messages");
    expect(fresh.getLocale()).toBe("fr");
    expect(fresh.t("chat.offlineWarning")).toBe(
      "Envoi désactivé — vous êtes hors ligne."
    );
    vi.unstubAllGlobals();
  });

  it("ignores an invalid persisted value and falls back to detection", async () => {
    vi.resetModules();
    localStorage.setItem(LOCALE_STORAGE_KEY, "xx");
    vi.stubGlobal("navigator", { language: "en-US" });
    const fresh = await import("../lib/messages");
    expect(fresh.getLocale()).toBe("en");
    vi.unstubAllGlobals();
  });
});
