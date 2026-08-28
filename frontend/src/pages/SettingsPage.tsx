import React, { useState, useMemo } from "react";
import { useAuth } from "../hooks/useAuth";
import { useTheme, Theme, Density } from "../context/ThemeContext";
import { useConversations, useDeleteConversation } from "../hooks/useConversations";
import {
  ensureNotificationPermission,
  getNotificationPrefs,
  isNotificationSupported,
  NotificationPrefs,
  playChime,
  setNotificationPrefs,
} from "../lib/notifications";
import {
  User,
  UserX,
  Sliders,
  ShieldAlert,
  RotateCcw,
  Palette,
  Bell,
  Database,
  Trash2,
  Download,
  Upload,
  Languages,
  Globe,
  Sparkles,
} from "lucide-react";
import {
  useLocale,
  LANGUAGE_OPTIONS,
  type LanguageOption,
} from "../lib/messages";
import { Button } from "../components/ui/Button";
import { Avatar, AvatarFallback } from "../components/ui/Avatar";
import ReauthDialog from "../components/auth/ReauthDialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/Modal";
import toast from "react-hot-toast";

import { useUserSettings, useUpdateUserSettings } from "../hooks/useUserSettings";

interface ConversationDefaults {
  temperature: number;
  retrievalMode: "hybrid" | "semantic" | "sparse" | "auto";
  topK: number;
  stream: boolean;
  hybridEnabled: boolean;
}

const DEFAULT_VALUES: ConversationDefaults = {
  temperature: 0.0,
  retrievalMode: "hybrid",
  topK: 10,
  stream: false,
  hybridEnabled: true,
};

type TabId = "profile" | "appearance" | "notifications" | "advanced" | "data";

/* ── Shared section header ── */
const SectionHeader: React.FC<{
  icon: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}> = ({ icon, title, description, action }) => (
  <div className="flex items-start justify-between gap-4 border-b border-(--border-subtle) pb-[calc(var(--space-factor,1)*16px)]">
    <div>
      <h3 className="flex items-center gap-2 text-sm font-semibold text-(--text-primary)">
        <span className="text-(--text-muted)">{icon}</span>
        {title}
      </h3>
      {description && (
        <p className="mt-0.5 text-xs text-(--text-secondary)">{description}</p>
      )}
    </div>
    {action}
  </div>
);

/* ── Setting row (label + control) ── */
const SettingRow: React.FC<{
  label: string;
  description?: string;
  control: React.ReactNode;
  className?: string;
}> = ({ label, description, control, className = "" }) => (
  <div className={`flex items-center justify-between gap-6 border-b border-(--border-subtle) py-[calc(var(--space-factor,1)*16px)] last:border-0 ${className}`}>
    <div className="min-w-0">
      <span className="block text-sm font-medium text-(--text-primary)">{label}</span>
      {description && (
        <span className="mt-0.5 block text-xs leading-relaxed text-(--text-muted)">{description}</span>
      )}
    </div>
    <div className="shrink-0">{control}</div>
  </div>
);

/* ── Checkbox toggle styled to tokens ── */
const ToggleCheckbox: React.FC<{
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label: string;
}> = ({ checked, onChange, disabled = false, label }) => (
  <label className="relative inline-flex items-center cursor-pointer select-none">
    <input
      type="checkbox"
      className="sr-only peer"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      disabled={disabled}
      aria-label={label}
    />
    <div
      className={`w-9 h-5 rounded-full transition-colors duration-200 ${
        checked ? "bg-(--accent-primary)" : "bg-(--bg-tertiary)"
      } border ${checked ? "border-(--accent-primary)/50" : "border-(--border-default)"}`}
    >
      <div
        className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-(--bg-primary) shadow-sm transition-transform duration-200 ${
          checked ? "translate-x-4" : "translate-x-0"
        }`}
      />
    </div>
  </label>
);

const SettingsPage: React.FC = () => {
  const { user, deleteAccount } = useAuth();
  const { theme, setTheme, fontSize, setFontSize, density, setDensity } = useTheme();
  const { locale, setLocale, t } = useLocale();
  const { data: conversationsData } = useConversations();
  const deleteConversation = useDeleteConversation();

  const [activeTab, setActiveTab] = useState<TabId>("profile");
  const [notifPrefs, setNotifPrefs] = useState<NotificationPrefs>(() => getNotificationPrefs());
  const [isClearingHistory, setIsClearingHistory] = useState(false);

  const navTabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: "profile", label: t("settings.tab.profile"), icon: <User size={14} /> },
    { id: "appearance", label: t("settings.tab.appearance"), icon: <Palette size={14} /> },
    { id: "notifications", label: t("settings.tab.notifications"), icon: <Bell size={14} /> },
    { id: "advanced", label: t("settings.tab.conversation"), icon: <Sliders size={14} /> },
    { id: "data", label: t("settings.tab.data"), icon: <Database size={14} /> },
  ];

  const { data: settingsData } = useUserSettings();
  const updateSettingsMutation = useUpdateUserSettings();

  const defaults: ConversationDefaults = useMemo(() => {
    const cloudDefaults = (settingsData?.preferences?.conversation_defaults as ConversationDefaults) || null;
    return cloudDefaults ? { ...DEFAULT_VALUES, ...cloudDefaults } : DEFAULT_VALUES;
  }, [settingsData?.preferences]);

  const [showClearHistoryDialog, setShowClearHistoryDialog] = useState(false);
  const [showResetConfigDialog, setShowResetConfigDialog] = useState(false);
  const [showDeleteAccountDialog, setShowDeleteAccountDialog] = useState(false);
  const [comingSoonLang, setComingSoonLang] = useState<LanguageOption | null>(null);

  const updateSetting = <K extends keyof ConversationDefaults>(key: K, value: ConversationDefaults[K]) => {
    const updated = { ...defaults, [key]: value };
    updateSettingsMutation.mutate({
      preferences: { conversation_defaults: updated },
    });
  };

  const handleResetDefaults = () => {
    updateSettingsMutation.mutate({
      preferences: { conversation_defaults: DEFAULT_VALUES },
    });
    toast.success("Defaults reset.");
  };

  const handleExportData = () => {
    const data: Record<string, string> = {};
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key) data[key] = localStorage.getItem(key) || "";
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `hybrid-rag-backup-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    toast.success("Backup exported.");
  };

  const handleImportData = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target?.result as string);
        Object.entries(parsed).forEach(([k, v]) => localStorage.setItem(k, v as string));
        toast.success("Configuration imported! Reloading…");
        setTimeout(() => window.location.reload(), 1000);
      } catch {
        toast.error("Invalid backup file.");
      }
    };
    reader.readAsText(file);
  };

  const handleDesktopNotificationsChange = async (enabled: boolean) => {
    if (enabled && isNotificationSupported()) {
      const permission = await ensureNotificationPermission();
      if (permission === "denied") {
        toast.error("Notifications are blocked in your browser settings.");
        return;
      }
      if (permission !== "granted") {
        toast("Notification permission not granted — enable it in your browser to see alerts.");
      }
    }
    const next = { ...notifPrefs, desktop: enabled };
    setNotifPrefs(next);
    setNotificationPrefs(next);
  };

  const handleSoundAlertsChange = (enabled: boolean) => {
    const next = { ...notifPrefs, sound: enabled };
    setNotifPrefs(next);
    setNotificationPrefs(next);
    if (enabled) playChime(); // instant audible preview
  };

  const handleClearHistory = async () => {
    const conversations = conversationsData?.conversations || [];
    setIsClearingHistory(true);
    const toastId = toast.loading(
      conversations.length === 0 ? "Checking history…" : `Deleting ${conversations.length} conversation(s)…`
    );
    try {
      await Promise.all(conversations.map((c) => deleteConversation.mutateAsync(c.id)));
      toast.success(
        conversations.length === 0 ? "Conversation history is already empty." : "Conversation history cleared.",
        { id: toastId }
      );
    } catch {
      toast.error("Failed to clear some conversations.", { id: toastId });
    } finally {
      setIsClearingHistory(false);
      setShowClearHistoryDialog(false);
    }
  };

  const userInitials = user?.email ? user.email.slice(0, 2).toUpperCase() : "US";

  return (
    <div className="flex-1 overflow-y-auto bg-(--bg-primary) text-(--text-primary)">
      <div className="max-w-3xl mx-auto px-4 py-6 pt-14 md:py-[calc(var(--space-factor,1)*32px)] md:px-8">

        {/* ── Page header ── */}
        <div className="mb-8">
          <h1 className="text-2xl font-semibold tracking-tight text-(--text-primary)">{t("settings.title")}</h1>
          <p className="mt-1 text-sm text-(--text-secondary)">
            {t("settings.subtitle")}
          </p>
        </div>

        <div className="flex flex-col md:flex-row gap-8">

          {/* ── Side nav ── */}
          <nav
            className="w-full shrink-0 flex-row gap-0.5 overflow-x-auto pb-2 md:w-44 md:flex-col md:overflow-x-visible md:pb-0"
            aria-label="Settings navigation"
          >
            {navTabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex cursor-pointer items-center gap-2.5 whitespace-nowrap rounded-md px-3 py-2 text-left text-xs font-medium transition-colors ${
                  activeTab === tab.id
                    ? "border border-(--border-subtle) bg-(--bg-secondary) text-(--text-primary)"
                    : "border border-transparent text-(--text-muted) hover:bg-(--bg-secondary)/60 hover:text-(--text-primary)"
                }`}
                aria-current={activeTab === tab.id ? "page" : undefined}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </nav>

          {/* ── Tab content ── */}
          <div className="flex-1 min-w-0 animate-in fade-in duration-200">

            {/* ─ Profile ─ */}
            {activeTab === "profile" && (
              <div className="space-y-0">
                <SectionHeader icon={<User size={14} />} title={t("settings.profile.title")} description={t("settings.profile.desc")} />
                <div className="flex items-center gap-4 border-b border-(--border-subtle) py-[calc(var(--space-factor,1)*24px)]">
                  <Avatar className="h-12 w-12 border border-(--border-default) bg-(--bg-tertiary)">
                    <AvatarFallback className="text-sm font-semibold">{userInitials}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-(--text-primary)">{user?.email}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="inline-flex items-center rounded-pill border border-(--border-subtle) bg-(--bg-tertiary) px-2 py-0.5 text-[10px] font-medium text-(--text-secondary)">
                        {user?.role}
                      </span>
                      <span className="inline-flex items-center rounded-pill border border-(--accent-success)/20 bg-(--accent-success)/10 px-2 py-0.5 text-[10px] font-medium text-(--accent-success)">
                        Active
                      </span>
                    </div>
                  </div>
                </div>
                <div className="pt-4 text-xs text-(--text-muted)">
                  To change your email or password, contact your administrator.
                </div>
              </div>
            )}

            {/* ─ Appearance ─ */}
            {activeTab === "appearance" && (
              <div className="space-y-0">
                <SectionHeader icon={<Palette size={14} />} title={t("settings.appearance.title")} description={t("settings.appearance.desc")} />

                {/* Theme */}
                <div className="border-b border-(--border-subtle) py-[calc(var(--space-factor,1)*20px)]">
                  <p className="mb-3 text-xs font-medium text-(--text-secondary)">{t("settings.appearance.theme")}</p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {(["dark", "light", "system", "high-contrast"] as Theme[]).map((opt) => {
                      const themeLabel =
                        opt === "dark"
                          ? t("settings.appearance.themeDark")
                          : opt === "light"
                          ? t("settings.appearance.themeLight")
                          : opt === "system"
                          ? t("settings.appearance.themeSystem")
                          : t("settings.appearance.themeHighContrast");
                      return (
                        <button
                          key={opt}
                          onClick={() => setTheme(opt)}
                          className={`cursor-pointer rounded-md border px-3 py-2 text-center text-xs font-medium capitalize transition-colors ${
                            theme === opt
                              ? "border-(--border-hover) bg-(--bg-secondary) text-(--text-primary)"
                              : "border-(--border-subtle) bg-transparent text-(--text-muted) hover:border-(--border-default) hover:text-(--text-primary)"
                          }`}
                          data-active={theme === opt}
                        >
                          {themeLabel}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Font size */}
                <div className="border-b border-(--border-subtle) py-[calc(var(--space-factor,1)*20px)]">
                  <div className="mb-3 flex items-center justify-between">
                    <p className="text-xs font-medium text-(--text-secondary)">Base Font Size</p>
                    <span className="font-mono text-xs text-(--text-muted)">{fontSize}px</span>
                  </div>
                  <input
                    type="range"
                    min="12"
                    max="20"
                    step="1"
                    value={fontSize}
                    onChange={(e) => setFontSize(parseInt(e.target.value, 10))}
                    aria-label={`Font size: ${fontSize}px`}
                  />
                  <div className="mt-1.5 flex justify-between text-[10px] text-(--text-muted)">
                    <span>12px</span><span>16px</span><span>20px</span>
                  </div>
                </div>

                {/* Density */}
                <div className="border-b border-(--border-subtle) py-[calc(var(--space-factor,1)*20px)]">
                  <p className="mb-3 text-xs font-medium text-(--text-secondary)">{t("settings.appearance.density")}</p>
                  <div className="grid grid-cols-3 gap-2">
                    {(["comfortable", "cozy", "compact"] as Density[]).map((opt) => {
                      const densityLabel =
                        opt === "comfortable"
                          ? t("settings.appearance.densityComfortable")
                          : opt === "cozy"
                          ? t("settings.appearance.densityCozy")
                          : t("settings.appearance.densityCompact");
                      return (
                        <button
                          key={opt}
                          onClick={() => setDensity(opt)}
                          className={`cursor-pointer rounded-md border px-3 py-2 text-center text-xs font-medium capitalize transition-colors ${
                            density === opt
                              ? "border-(--border-hover) bg-(--bg-secondary) text-(--text-primary)"
                              : "border-(--border-subtle) bg-transparent text-(--text-muted) hover:border-(--border-default) hover:text-(--text-primary)"
                          }`}
                          data-active={density === opt}
                        >
                          {densityLabel}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Language */}
                <div className="py-[calc(var(--space-factor,1)*20px)]">
                  <p className="mb-3 text-xs font-medium text-(--text-secondary)">{t("settings.language")}</p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {LANGUAGE_OPTIONS.map((opt) => {
                      const isSelected = opt.code === "en" && locale === "en";
                      return (
                        <button
                          key={opt.code}
                          onClick={() => {
                            if (opt.status === "available") {
                              setLocale("en");
                            } else {
                              setComingSoonLang(opt);
                            }
                          }}
                          className={`group relative flex items-center justify-between gap-1.5 cursor-pointer rounded-md border px-3 py-2 text-left text-xs font-medium transition-colors ${
                            isSelected
                              ? "border-(--border-hover) bg-(--bg-secondary) text-(--text-primary)"
                              : "border-(--border-subtle) bg-transparent text-(--text-muted) hover:border-(--border-default) hover:text-(--text-primary)"
                          }`}
                          data-active={isSelected}
                          title={opt.status === "coming-soon" ? `${opt.name} — Coming Soon` : opt.name}
                        >
                          <span className="flex items-center gap-1.5 truncate">
                            <span className="text-sm">{opt.flag}</span>
                            <span className="truncate">{opt.nativeName}</span>
                          </span>
                          {opt.status === "coming-soon" && (
                            <span className="shrink-0 text-[9px] font-semibold uppercase tracking-wider text-amber-500/80 bg-amber-500/10 border border-amber-500/20 rounded px-1 py-0.2">
                              Soon
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                  <p className="mt-2 flex items-center gap-1 text-[11px] text-(--text-muted)">
                    <Languages size={12} className="flex-shrink-0" />
                    <span>English is currently active. Click other languages to preview upcoming support.</span>
                  </p>
                </div>
              </div>
            )}

            {/* ─ Notifications ─ */}
            {activeTab === "notifications" && (
              <div className="space-y-0">
                <SectionHeader icon={<Bell size={14} />} title={t("settings.notifications.title")} description={t("settings.notifications.desc")} />
                <SettingRow
                  label={t("settings.notifications.desktop")}
                  description={t("settings.notifications.desktopDesc")}
                  control={
                    <ToggleCheckbox
                      checked={notifPrefs.desktop}
                      onChange={handleDesktopNotificationsChange}
                      disabled={!isNotificationSupported()}
                      label="Toggle desktop notifications"
                    />
                  }
                />
                <SettingRow
                  label={t("settings.notifications.sound")}
                  description={t("settings.notifications.soundDesc")}
                  control={
                    <ToggleCheckbox
                      checked={notifPrefs.sound}
                      onChange={handleSoundAlertsChange}
                      label="Toggle sound alerts"
                    />
                  }
                />
              </div>
            )}

            {/* ─ Conversation defaults ─ */}
            {activeTab === "advanced" && (
              <div className="space-y-0">
                <SectionHeader
                  icon={<Sliders size={14} />}
                  title={t("settings.conversation.title")}
                  description={t("settings.conversation.desc")}
                  action={
                    <Button variant="ghost" size="sm" onClick={handleResetDefaults} className="gap-1.5 text-xs">
                      <RotateCcw size={12} />
                      Reset
                    </Button>
                  }
                />

                {/* Temperature */}
                <div className="border-b border-(--border-subtle) py-[calc(var(--space-factor,1)*20px)]">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-(--text-primary)">Temperature</p>
                      <p className="mt-0.5 text-xs text-(--text-muted)">
                        {defaults.temperature === 0 ? "Deterministic" : "Creative"} · {defaults.temperature.toFixed(1)}
                      </p>
                    </div>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={defaults.temperature}
                    onChange={(e) => updateSetting("temperature", parseFloat(e.target.value))}
                    aria-label={`Temperature: ${defaults.temperature}`}
                  />
                  <div className="mt-1.5 flex justify-between text-[10px] text-(--text-muted)">
                    <span>0 — Strict</span><span>1 — Creative</span>
                  </div>
                </div>

                {/* Top K */}
                <div className="border-b border-(--border-subtle) py-[calc(var(--space-factor,1)*20px)]">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-(--text-primary)">Retrieval Top K</p>
                      <p className="mt-0.5 text-xs text-(--text-muted)">Maximum chunks retrieved · {defaults.topK}</p>
                    </div>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="20"
                    step="1"
                    value={defaults.topK}
                    onChange={(e) => updateSetting("topK", parseInt(e.target.value, 10))}
                    aria-label={`Top K: ${defaults.topK}`}
                  />
                  <div className="mt-1.5 flex justify-between text-[10px] text-(--text-muted)">
                    <span>1</span><span>20</span>
                  </div>
                </div>

                {/* Retrieval mode */}
                <SettingRow
                  label="Retrieval Mode"
                  description="The search strategy used to ground responses."
                  control={
                    <select
                      value={defaults.retrievalMode}
                      onChange={(e) => updateSetting("retrievalMode", e.target.value as ConversationDefaults["retrievalMode"])}
                      className="h-8 min-w-35 cursor-pointer rounded-md border border-(--border-default) bg-(--bg-input) px-2.5 text-xs text-(--text-primary) outline-none transition-colors hover:border-(--border-hover) focus:border-(--accent-primary)/50"
                      title="Retrieval mode"
                    >
                      <option value="hybrid">Hybrid Search</option>
                      <option value="semantic">Semantic (Dense)</option>
                      <option value="sparse">Keyword (Sparse)</option>
                      <option value="auto">Auto Select</option>
                    </select>
                  }
                />

                <SettingRow
                  label="SSE Response Streaming"
                  description="Stream LLM tokens chunk-by-chunk as they are generated."
                  control={
                    <ToggleCheckbox
                      checked={defaults.stream}
                      onChange={(v) => updateSetting("stream", v)}
                      label="Toggle response streaming"
                    />
                  }
                />

                <SettingRow
                  label="Reciprocal Rank Fusion"
                  description="Merge keyword and semantic scores using RRF for hybrid retrieval."
                  control={
                    <ToggleCheckbox
                      checked={defaults.hybridEnabled}
                      onChange={(v) => updateSetting("hybridEnabled", v)}
                      label="Toggle reciprocal rank fusion"
                    />
                  }
                />
              </div>
            )}

            {/* ─ Data & Privacy ─ */}
            {activeTab === "data" && (
              <div className="space-y-0">
                <SectionHeader icon={<Database size={14} />} title="Data & Privacy" description="Export your preferences or wipe local data." />

                {/* Export */}
                <SettingRow
                  label="Export Preferences"
                  description="Download a JSON backup of all local settings, folders, and pinned items."
                  control={
                    <Button variant="secondary" size="sm" onClick={handleExportData} className="gap-1.5">
                      <Download size={13} />
                      Export
                    </Button>
                  }
                />

                {/* Import */}
                <SettingRow
                  label="Import Preferences"
                  description="Restore from a previously exported backup. This replaces all current local settings."
                  control={
                    <div className="relative">
                      <input
                        type="file"
                        accept=".json"
                        onChange={handleImportData}
                        className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
                        aria-label="Import preferences file"
                      />
                      <Button variant="secondary" size="sm" className="gap-1.5 pointer-events-none">
                        <Upload size={13} />
                        Import
                      </Button>
                    </div>
                  }
                />

                {/* Danger zone */}
                <div className="mt-2 border-t border-(--border-subtle) pt-[calc(var(--space-factor,1)*24px)]">
                  <div className="flex items-center gap-2 mb-4">
                    <ShieldAlert size={14} className="text-(--accent-error)" />
                    <span className="text-sm font-semibold text-(--accent-error)">Danger Zone</span>
                  </div>

                  <SettingRow
                    label="Clear Conversation History"
                    description="Permanently delete all conversation records and message transcripts."
                    control={
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => setShowClearHistoryDialog(true)}
                        className="gap-1.5"
                      >
                        <Trash2 size={13} />
                        Clear
                      </Button>
                    }
                  />

                  <SettingRow
                    label="Factory Reset"
                    description="Wipe all local preferences, folders, tags, and settings. You will be signed out."
                    control={
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => setShowResetConfigDialog(true)}
                        className="gap-1.5"
                      >
                        <RotateCcw size={13} />
                        Reset
                      </Button>
                    }
                  />

                  <SettingRow
                    label="Delete Account"
                    description="Permanently delete your account, all conversations, and documents. This cannot be undone."
                    control={
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => setShowDeleteAccountDialog(true)}
                        className="gap-1.5"
                      >
                        <UserX size={13} />
                        Delete
                      </Button>
                    }
                  />
                </div>
              </div>
            )}

          </div>
        </div>
      </div>

      {/* ── Confirm: clear history ── */}
      <Dialog open={showClearHistoryDialog} onOpenChange={setShowClearHistoryDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm">
              <Trash2 size={15} className="text-(--accent-error)" />
              Clear Conversation History?
            </DialogTitle>
            <DialogDescription>
              This will permanently delete all conversations and message transcripts. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="secondary" size="sm" onClick={() => setShowClearHistoryDialog(false)}>Cancel</Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleClearHistory}
              disabled={isClearingHistory}
              loading={isClearingHistory}
            >
              {isClearingHistory ? "Clearing…" : "Confirm Clear"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Confirm: delete account (reusable reauth gate) ── */}
      <ReauthDialog
        open={showDeleteAccountDialog}
        onOpenChange={setShowDeleteAccountDialog}
        title="Delete Account?"
        icon={<UserX size={15} className="text-(--accent-error)" />}
        description={
          <>
            This permanently deletes your account, all conversations, and documents. Type{" "}
            <span className="font-mono text-(--text-primary)">{user?.email}</span> and your
            password to confirm.
          </>
        }
        accountEmail={user?.email}
        requireEmail
        confirmLabel="Delete Account"
        submittingLabel="Deleting…"
        successMessage="Your account has been deleted."
        emailInputId="delete-account-confirm-email"
        passwordInputId="delete-account-confirm-password"
        onConfirm={deleteAccount}
        errorMessages={{ UNKNOWN: "Failed to delete account. Please try again." }}
      />

      {/* ── Confirm: factory reset ── */}
      <Dialog open={showResetConfigDialog} onOpenChange={setShowResetConfigDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm">
              <RotateCcw size={15} className="text-(--accent-error)" />
              Perform Factory Reset?
            </DialogTitle>
            <DialogDescription>
              This wipes all custom folders, pinned items, tags, layout settings, and logs you out. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="secondary" size="sm" onClick={() => setShowResetConfigDialog(false)}>Cancel</Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                localStorage.clear();
                toast.success("Preferences reset! Reloading…");
                setTimeout(() => window.location.reload(), 1000);
              }}
            >
              Wipe Everything
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Dialog: Language Coming Soon ── */}
      <Dialog open={comingSoonLang !== null} onOpenChange={(open) => !open && setComingSoonLang(null)}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] mb-3">
              <Globe size={24} />
            </div>
            <DialogTitle className="text-center text-base font-semibold">
              {comingSoonLang?.flag} {comingSoonLang?.nativeName} ({comingSoonLang?.name})
            </DialogTitle>
            <div className="flex justify-center my-1.5">
              <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium bg-amber-500/10 border border-amber-500/25 text-amber-500 dark:text-amber-400">
                <Sparkles size={11} />
                Coming Soon · In Development
              </span>
            </div>
            <DialogDescription className="text-center text-xs leading-relaxed text-[var(--text-secondary)] mt-2">
              Full localization for {comingSoonLang?.name} ({comingSoonLang?.nativeName}) is currently being translated and formatted. The application currently defaults to English.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="sm:justify-center mt-4">
            <Button
              variant="default"
              size="sm"
              onClick={() => {
                const name = comingSoonLang?.name;
                setComingSoonLang(null);
                toast.success(`We'll notify you when ${name} is available!`);
              }}
              className="w-full sm:w-auto"
            >
              Got it
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SettingsPage;
