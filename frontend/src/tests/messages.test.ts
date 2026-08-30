import { afterEach, describe, expect, it } from "vitest";
import {
  t,
  setLocale,
  getLocale,
  detectLocale,
  LANGUAGE_OPTIONS,
} from "../lib/messages";

describe("messages i18n", () => {
  afterEach(() => {
    setLocale("en");
  });

  it("defaults to English", () => {
    expect(getLocale()).toBe("en");
    expect(t("chatFiles.caption")).toContain("Only usable in this chat");
    expect(t("chatFiles.header")).toContain("only this conversation can use them");
    expect(t("chatFiles.tooltip")).toBe("Only this chat can use this file");
    expect(t("chatFiles.removeAria", { filename: "a.pdf" })).toBe(
      "Remove a.pdf from this chat"
    );
    expect(t("chat.placeholderDefault")).toBe("Message NexusRAG...");
    expect(t("chat.placeholderStreaming")).toBe("AI is responding...");
    expect(t("chat.placeholderDrop")).toBe("Drop files here to attach...");
    expect(t("commands.documents.label")).toBe("Documents priority");
    expect(t("commands.documents.description")).toBe(
      "Prioritize your uploaded documents"
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

  it("exposes English as available and international languages as coming-soon", () => {
    const english = LANGUAGE_OPTIONS.find((l) => l.code === "en");
    expect(english?.status).toBe("available");

    const hindi = LANGUAGE_OPTIONS.find((l) => l.code === "hi");
    expect(hindi?.status).toBe("coming-soon");
    expect(hindi?.nativeName).toBe("हिन्दी");

    const telugu = LANGUAGE_OPTIONS.find((l) => l.code === "te");
    expect(telugu?.status).toBe("coming-soon");
    expect(telugu?.nativeName).toBe("తెలుగు");

    const french = LANGUAGE_OPTIONS.find((l) => l.code === "fr");
    expect(french?.status).toBe("coming-soon");
    expect(french?.nativeName).toBe("Français");
  });

  it("detectLocale maps cleanly to English", () => {
    expect(detectLocale("en-US")).toBe("en");
    expect(detectLocale("fr-FR")).toBe("en");
    expect(detectLocale(undefined)).toBe("en");
  });
});
