import { useSyncExternalStore } from "react";

const en = {
  // Navigation & Sidebar
  "nav.newChat": "New Chat",
  "nav.documents": "Documents",
  "nav.conversations": "Conversations",
  "nav.searchPlaceholder": "Search conversations...",
  "nav.folders": "Folders",
  "nav.pinned": "Pinned",
  "nav.settings": "Settings",
  "nav.logout": "Log out",
  "nav.admin": "Admin Dashboard",
  "nav.today": "Today",
  "nav.yesterday": "Yesterday",
  "nav.last7Days": "Previous 7 days",
  "nav.older": "Older",
  "nav.noConversations": "No conversations yet",
  "nav.createFolder": "New folder",
  "nav.rename": "Rename",
  "nav.delete": "Delete",
  "nav.pin": "Pin conversation",
  "nav.unpin": "Unpin conversation",
  "nav.moveToFolder": "Move to folder",

  // Chat-scoped attachment chips strip & composer
  "chatFiles.header": "Chat files — only this conversation can use them",
  "chatFiles.caption": "Only usable in this chat — deleted with the conversation.",
  "chatFiles.tooltip": "Only this chat can use this file",
  "chatFiles.removeAria": "Remove {filename} from this chat",

  // Composer copy
  "chat.offlineWarning": "Sending disabled — you are offline.",
  "chat.documentMode": "Document mode — answers will prioritize your uploaded documents",
  "chat.uploadLimit": "You can attach up to {max} files per message.",
  "chat.uploadRoomOne": "Only {room} more attachment can be added (max {max}).",
  "chat.uploadRoomOther": "Only {room} more attachments can be added (max {max}).",
  "chat.uploadFailed": "Upload failed",
  "chat.placeholderDefault": "Message Hybrid RAG...",
  "chat.placeholderStreaming": "AI is responding...",
  "chat.placeholderDrop": "Drop files here to attach...",
  "chat.commandSearchPlaceholder": "Search commands…",
  "chat.commandEmpty": "No commands found.",

  // Empty chat view
  "chat.emptyHeading": "How can I help you today?",
  "chat.emptySub": "Upload PDF, TXT, DOCX, MD, or image files to your library, then ask questions to retrieve grounded insights.",
  "chat.example1": "Summarize my documents",
  "chat.example1Prompt": "Can you provide a comprehensive summary of my uploaded documents?",
  "chat.example2": "Explain this concept",
  "chat.example2Prompt": "Explain how our retrieval pipeline merges vector and sparse results.",
  "chat.example3": "Search my knowledge base",
  "chat.example3Prompt": "Find all key references to security policies inside the documents.",
  "chat.example4": "Compare these documents",
  "chat.example4Prompt": "Compare the architecture guidelines in file A and file B.",

  // Commands
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

  // Settings page
  "settings.title": "Settings",
  "settings.subtitle": "Manage your preferences, appearance, and account.",
  "settings.tab.profile": "Profile",
  "settings.tab.appearance": "Appearance",
  "settings.tab.notifications": "Notifications",
  "settings.tab.conversation": "Conversation",
  "settings.tab.data": "Data & Privacy",

  "settings.profile.title": "Profile",
  "settings.profile.desc": "Manage your account identity and credentials.",
  "settings.profile.email": "Email Address",
  "settings.profile.role": "Role",
  "settings.profile.id": "Account ID",
  "settings.profile.joined": "Joined",
  "settings.profile.dangerZone": "Danger Zone",
  "settings.profile.deleteAccount": "Delete Account",
  "settings.profile.deleteAccountDesc": "Permanently remove your account and all associated data.",

  "settings.appearance.title": "Appearance",
  "settings.appearance.desc": "Customize the visual presentation of the application.",
  "settings.appearance.theme": "Theme",
  "settings.appearance.themeDark": "Dark",
  "settings.appearance.themeLight": "Light",
  "settings.appearance.themeSystem": "System",
  "settings.appearance.themeHighContrast": "High Contrast",
  "settings.appearance.density": "Interface Density",
  "settings.appearance.densityComfortable": "Comfortable",
  "settings.appearance.densityCozy": "Cozy",
  "settings.appearance.densityCompact": "Compact",
  "settings.language": "Language",
  "settings.languageDescription": "Interface language for the app.",

  "settings.notifications.title": "Notifications",
  "settings.notifications.desc": "Control how and when you receive alerts.",
  "settings.notifications.desktop": "Desktop Notifications",
  "settings.notifications.desktopDesc": "Show browser push notifications when responses complete.",
  "settings.notifications.sound": "Sound Alerts",
  "settings.notifications.soundDesc": "Play an audio chime when an AI response completes.",

  "settings.conversation.title": "Conversation Defaults",
  "settings.conversation.desc": "Adjust how models and retrieval algorithms behave.",
  "settings.conversation.temperature": "Temperature",
  "settings.conversation.temperatureDesc": "Controls randomness: lower is deterministic, higher is creative.",
  "settings.conversation.strict": "Strict",
  "settings.conversation.creative": "Creative",
  "settings.conversation.topK": "Retrieval Top K",
  "settings.conversation.topKDesc": "Maximum chunks retrieved for context.",
  "settings.conversation.mode": "Retrieval Mode",
  "settings.conversation.modeDesc": "The search strategy used to ground responses.",
  "settings.conversation.stream": "Stream Responses",
  "settings.conversation.streamDesc": "Render responses token by token as they generate.",
  "settings.conversation.hybrid": "Hybrid Search",
  "settings.conversation.hybridDesc": "Combine dense embeddings and BM25 sparse lexical search.",
  "settings.conversation.reset": "Reset Defaults",

  "settings.data.title": "Data & Privacy",
  "settings.data.desc": "Manage your local data, exports, and history.",
  "settings.data.clearHistory": "Clear Conversation History",
  "settings.data.clearHistoryDesc": "Permanently delete all your chat conversations.",
  "settings.data.export": "Export Configuration",
  "settings.data.exportDesc": "Download a JSON backup of your application settings.",
  "settings.data.import": "Import Configuration",
  "settings.data.importDesc": "Restore settings from a previously exported JSON backup.",

  // Documents Page
  "docs.title": "Documents",
  "docs.subtitle": "Upload and manage reference documents for grounded AI search.",
  "docs.upload": "Upload Documents",
  "docs.searchPlaceholder": "Search documents by title...",
  "docs.dropzoneText": "Drag & drop files here or click to browse",
  "docs.empty": "No documents uploaded yet",
  "docs.emptySub": "Upload PDF, TXT, MD, or DOCX files to get started.",
} as const;

export type MessageKey = keyof typeof en;

export type Locale = "en";

export interface LanguageOption {
  code: string;
  name: string;
  nativeName: string;
  flag: string;
  status: "available" | "coming-soon";
}

export const LANGUAGE_OPTIONS: LanguageOption[] = [
  { code: "en", name: "English", nativeName: "English", flag: "🇬🇧", status: "available" },
  { code: "es", name: "Spanish", nativeName: "Español", flag: "🇪🇸", status: "coming-soon" },
  { code: "fr", name: "French", nativeName: "Français", flag: "🇫🇷", status: "coming-soon" },
  { code: "de", name: "German", nativeName: "Deutsch", flag: "🇩🇪", status: "coming-soon" },
  { code: "hi", name: "Hindi", nativeName: "हिन्दी", flag: "🇮🇳", status: "coming-soon" },
  { code: "te", name: "Telugu", nativeName: "తెలుగు", flag: "🇮🇳", status: "coming-soon" },
  { code: "ja", name: "Japanese", nativeName: "日本語", flag: "🇯🇵", status: "coming-soon" },
  { code: "zh", name: "Chinese", nativeName: "简体中文", flag: "🇨🇳", status: "coming-soon" },
];

export const SUPPORTED_LOCALES: { value: Locale; label: string }[] = [
  { value: "en", label: "English" },
];

const MESSAGES: Record<Locale, Record<MessageKey, string>> = {
  en,
};

export function detectLocale(_language: string | undefined): Locale {
  return "en";
}

export const LOCALE_STORAGE_KEY = "locale";

let activeLocale: Locale = "en";

const listeners = new Set<() => void>();

export function setLocale(locale: Locale): void {
  activeLocale = locale;
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  }
  listeners.forEach((listener) => listener());
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("localechange", { detail: locale }));
  }
}

export function getLocale(): Locale {
  return activeLocale;
}

export function subscribeLocale(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useLocale(): {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: typeof t;
} {
  const locale = useSyncExternalStore(subscribeLocale, getLocale, getLocale);
  return { locale, setLocale, t };
}

export function t(
  key: MessageKey,
  params?: Record<string, string | number>
): string {
  let str = MESSAGES[activeLocale]?.[key] ?? MESSAGES.en[key] ?? String(key);
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      str = str.split(`{${name}}`).join(String(value));
    }
  }
  return str;
}
