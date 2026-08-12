/**
 * Centralized user-facing copy, keyed by stable message id so components never
 * embed strings. This is the i18n seam: every locale is a dict with the same
 * keys (enforced by the `Record<MessageKey, string>` type — a locale missing a
 * key or adding an unknown one fails to compile), and `t` resolves against the
 * active locale. `setLocale` switches it at runtime; components call `t` with
 * no locale argument, so translating never touches component code.
 *
 * The active locale is resolved once at module load: a persisted choice in
 * localStorage wins, otherwise the browser language is auto-detected
 * (English fallback). `setLocale` switches it at runtime and persists the
 * choice. The app ships English and French.
 */

export type Locale = "en" | "fr";

const en = {
  // Chat-scoped attachment chips strip (ConversationDocumentChips) and the
  // composer's in-flight upload tray (ChatInput).
  "chatFiles.header": "Chat files — only this conversation can use them",
  "chatFiles.caption":
    "Only usable in this chat — deleted with the conversation.",
  "chatFiles.tooltip": "Only this chat can use this file",
  "chatFiles.removeAria": "Remove {filename} from this chat",

  // Composer copy (ChatInput).
  "chat.offlineWarning": "Sending disabled — you are offline.",
  "chat.documentMode":
    "Document mode — answers will prioritize your uploaded documents",
  "chat.uploadLimit": "You can attach up to {max} files per message.",
  "chat.uploadRoomOne":
    "Only {room} more attachment can be added (max {max}).",
  "chat.uploadRoomOther":
    "Only {room} more attachments can be added (max {max}).",
  "chat.uploadFailed": "Upload failed",

  // Settings page (SettingsPage).
  "settings.language": "Language",
  "settings.languageDescription": "Interface language for the app.",

  // Composer placeholders + slash command palette (ChatInput).
  "chat.placeholderDefault": "Message Hybrid RAG...",
  "chat.placeholderStreaming": "AI is responding...",
  "chat.placeholderDrop": "Drop files here to attach...",
  "chat.commandSearchPlaceholder": "Search commands…",
  "chat.commandEmpty": "No commands found.",

  "commands.documents.label": "Documents priority",
  "commands.documents.description": "Prioritize your uploaded documents",
  "commands.search.label": "Search documents",
  "commands.search.description": "Query your knowledge base",
  "commands.summarize.label": "Summarize",
  "commands.summarize.description": "Summarize selected documents",
  "commands.explain.label": "Explain concept",
  "commands.explain.description": "Get detailed explanation",
  "commands.compare.label": "Compare",
  "commands.compare.description": "Compare two documents",
  "commands.code.label": "Code helper",
  "commands.code.description": "Generate or explain code",
  "commands.settings.label": "Settings",
  "commands.settings.description": "Open settings panel",
} as const;

export type MessageKey = keyof typeof en;

const MESSAGES: Record<Locale, Record<MessageKey, string>> = {
  en,
  fr: {
    "chatFiles.header":
      "Fichiers de conversation — seule cette conversation peut les utiliser",
    "chatFiles.caption":
      "Utilisables uniquement dans cette conversation — supprimés avec la conversation.",
    "chatFiles.tooltip": "Seule cette conversation peut utiliser ce fichier",
    "chatFiles.removeAria": "Retirer {filename} de cette conversation",
    "chat.offlineWarning": "Envoi désactivé — vous êtes hors ligne.",
    "chat.documentMode":
      "Mode documents — les réponses privilégieront vos documents téléversés",
    "chat.uploadLimit":
      "Vous pouvez joindre jusqu'à {max} fichiers par message.",
    "chat.uploadRoomOne":
      "Vous pouvez encore ajouter {room} pièce jointe (max {max}).",
    "chat.uploadRoomOther":
      "Vous pouvez encore ajouter {room} pièces jointes (max {max}).",
    "chat.uploadFailed": "Échec du téléversement",
    "settings.language": "Langue",
    "settings.languageDescription": "Langue de l'interface de l'application.",
    "chat.placeholderDefault": "Écrivez votre message…",
    "chat.placeholderStreaming": "L'IA répond…",
    "chat.placeholderDrop": "Déposez des fichiers pour les joindre…",
    "chat.commandSearchPlaceholder": "Rechercher des commandes…",
    "chat.commandEmpty": "Aucune commande trouvée.",

    "commands.documents.label": "Priorité documents",
    "commands.documents.description": "Priorise vos documents téléversés",
    "commands.search.label": "Rechercher dans les documents",
    "commands.search.description": "Interroger votre base de connaissances",
    "commands.summarize.label": "Résumer",
    "commands.summarize.description": "Résumer les documents sélectionnés",
    "commands.explain.label": "Expliquer un concept",
    "commands.explain.description": "Obtenir une explication détaillée",
    "commands.compare.label": "Comparer",
    "commands.compare.description": "Comparer deux documents",
    "commands.code.label": "Assistant code",
    "commands.code.description": "Générer ou expliquer du code",
    "commands.settings.label": "Paramètres",
    "commands.settings.description": "Ouvrir le panneau des paramètres",
  },
};

/**
 * Map a BCP-47 language tag (e.g. "fr-FR") to the closest supported locale,
 * falling back to English for unknown tags and missing input.
 */
export function detectLocale(language: string | undefined): Locale {
  if (!language) return "en";
  const base = language.toLowerCase().split("-")[0];
  return base === "fr" ? "fr" : "en";
}

function readNavigatorLanguage(): string | undefined {
  if (typeof navigator === "undefined") return undefined;
  return navigator.languages?.[0] ?? navigator.language;
}

// Where the chosen locale is persisted so it survives reloads.
export const LOCALE_STORAGE_KEY = "locale";

function readStoredLocale(): Locale | undefined {
  if (typeof localStorage === "undefined") return undefined;
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  return stored === "en" || stored === "fr" ? stored : undefined;
}

// Seed the active locale once, at module load: a persisted choice wins,
// otherwise auto-detect from the browser language.
let activeLocale: Locale =
  readStoredLocale() ?? detectLocale(readNavigatorLanguage());

// Self-named labels per locale; keyed by Locale so adding a locale to the
// union forces a label here (and in the switcher below).
const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  fr: "Français",
};

/** Locales offered in the UI, labeled in their own language. */
export const SUPPORTED_LOCALES: { value: Locale; label: string }[] = (
  Object.keys(LOCALE_LABELS) as Locale[]
).map((value) => ({ value, label: LOCALE_LABELS[value] }));

/** Switch the active locale for all future `t` calls (and persist it). */
export function setLocale(locale: Locale): void {
  activeLocale = locale;
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  }
}

export function getLocale(): Locale {
  return activeLocale;
}

export function t(
  key: MessageKey,
  params?: Record<string, string | number>
): string {
  let str = MESSAGES[activeLocale][key];
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      // split/join instead of replaceAll to stay safe across TS lib targets.
      str = str.split(`{${name}}`).join(String(value));
    }
  }
  return str;
}
