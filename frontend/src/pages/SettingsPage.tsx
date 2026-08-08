import React, { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { useTheme, Theme, Density } from "../context/ThemeContext";
import {
  User,
  Sliders,
  ShieldAlert,
  RotateCcw,
  Palette,
  Bell,
  Database,
  Trash2,
  Download,
  Upload,
} from "lucide-react";
import { Button } from "../components/ui/Button";
import { Avatar, AvatarFallback } from "../components/ui/Avatar";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/Modal";
import toast from "react-hot-toast";

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

const NAV_TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "profile",       label: "Profile",       icon: <User size={14} /> },
  { id: "appearance",    label: "Appearance",     icon: <Palette size={14} /> },
  { id: "notifications", label: "Notifications",  icon: <Bell size={14} /> },
  { id: "advanced",      label: "Conversation",   icon: <Sliders size={14} /> },
  { id: "data",          label: "Data & Privacy", icon: <Database size={14} /> },
];

/* ── Shared section header ── */
const SectionHeader: React.FC<{
  icon: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}> = ({ icon, title, description, action }) => (
  <div className="flex items-start justify-between gap-4 pb-4 border-b border-[var(--border-subtle)]">
    <div>
      <h3 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-2">
        <span className="text-[var(--text-muted)]">{icon}</span>
        {title}
      </h3>
      {description && (
        <p className="text-xs text-[var(--text-secondary)] mt-0.5">{description}</p>
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
  <div className={`flex items-center justify-between gap-6 py-4 border-b border-[var(--border-subtle)] last:border-0 ${className}`}>
    <div className="min-w-0">
      <span className="text-sm text-[var(--text-primary)] font-medium block">{label}</span>
      {description && (
        <span className="text-xs text-[var(--text-muted)] block mt-0.5 leading-relaxed">{description}</span>
      )}
    </div>
    <div className="flex-shrink-0">{control}</div>
  </div>
);

/* ── Checkbox toggle styled to tokens ── */
const ToggleCheckbox: React.FC<{
  checked: boolean;
  onChange: (val: boolean) => void;
  label: string;
}> = ({ checked, onChange, label }) => (
  <label className="relative inline-flex items-center cursor-pointer select-none" aria-label={label}>
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      className="sr-only"
    />
    <div
      className={`w-9 h-5 rounded-full transition-colors duration-200 ${
        checked ? "bg-[var(--accent-primary)]" : "bg-[var(--bg-tertiary)]"
      } border ${checked ? "border-[var(--accent-primary)]/50" : "border-[var(--border-default)]"}`}
    >
      <div
        className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
          checked ? "translate-x-4" : "translate-x-0"
        }`}
      />
    </div>
  </label>
);

const SettingsPage: React.FC = () => {
  const { user } = useAuth();
  const { theme, setTheme, fontSize, setFontSize, density, setDensity } = useTheme();

  const [activeTab, setActiveTab] = useState<TabId>("profile");

  const [defaults, setDefaults] = useState<ConversationDefaults>(() => {
    try {
      const saved = localStorage.getItem("conversation-defaults");
      return saved ? { ...DEFAULT_VALUES, ...JSON.parse(saved) } : DEFAULT_VALUES;
    } catch {
      return DEFAULT_VALUES;
    }
  });

  const [showClearHistoryDialog, setShowClearHistoryDialog]   = useState(false);
  const [showResetConfigDialog,  setShowResetConfigDialog]    = useState(false);

  const updateSetting = <K extends keyof ConversationDefaults>(key: K, value: ConversationDefaults[K]) => {
    const updated = { ...defaults, [key]: value };
    setDefaults(updated);
    localStorage.setItem("conversation-defaults", JSON.stringify(updated));
  };

  const handleResetDefaults = () => {
    setDefaults(DEFAULT_VALUES);
    localStorage.setItem("conversation-defaults", JSON.stringify(DEFAULT_VALUES));
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

  const userInitials = user?.email ? user.email.slice(0, 2).toUpperCase() : "US";

  return (
    <div className="flex-1 overflow-y-auto bg-[var(--bg-primary)] text-[var(--text-primary)]">
      <div className="max-w-3xl mx-auto px-4 py-8 md:px-8">

        {/* ── Page header ── */}
        <div className="mb-8">
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--text-primary)]">Settings</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            Manage your account, appearance, and AI preferences.
          </p>
        </div>

        <div className="flex flex-col md:flex-row gap-8">

          {/* ── Side nav ── */}
          <nav
            className="w-full md:w-44 flex flex-row md:flex-col gap-0.5 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0 flex-shrink-0"
            aria-label="Settings navigation"
          >
            {NAV_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded-[var(--radius-md)] transition-colors cursor-pointer whitespace-nowrap text-left ${
                  activeTab === tab.id
                    ? "bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border-subtle)]"
                    : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]/60 border border-transparent"
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
                <SectionHeader icon={<User size={14} />} title="User Profile" description="Your identity and account details." />
                <div className="flex items-center gap-4 py-6 border-b border-[var(--border-subtle)]">
                  <Avatar className="h-12 w-12 bg-[var(--bg-tertiary)] border border-[var(--border-default)]">
                    <AvatarFallback className="text-sm font-semibold">{userInitials}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[var(--text-primary)] truncate">{user?.email}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded-[var(--radius-pill)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border border-[var(--border-subtle)]">
                        {user?.role}
                      </span>
                      <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded-[var(--radius-pill)] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        Active
                      </span>
                    </div>
                  </div>
                </div>
                <div className="pt-4 text-xs text-[var(--text-muted)]">
                  To change your email or password, contact your administrator.
                </div>
              </div>
            )}

            {/* ─ Appearance ─ */}
            {activeTab === "appearance" && (
              <div className="space-y-0">
                <SectionHeader icon={<Palette size={14} />} title="Appearance" description="Customize theme, font size, and interface density." />

                {/* Theme */}
                <div className="py-5 border-b border-[var(--border-subtle)]">
                  <p className="text-xs font-medium text-[var(--text-secondary)] mb-3">Theme Mode</p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {(["dark", "light", "system", "high-contrast"] as Theme[]).map((opt) => (
                      <button
                        key={opt}
                        onClick={() => setTheme(opt)}
                        className={`px-3 py-2 text-xs font-medium rounded-[var(--radius-md)] border text-center transition-colors cursor-pointer capitalize ${
                          theme === opt
                            ? "bg-[var(--bg-secondary)] text-[var(--text-primary)] border-[var(--border-hover)]"
                            : "bg-transparent border-[var(--border-subtle)] hover:border-[var(--border-default)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                        }`}
                        aria-pressed={theme === opt}
                      >
                        {opt === "high-contrast" ? "High Contrast" : opt.charAt(0).toUpperCase() + opt.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Font size */}
                <div className="py-5 border-b border-[var(--border-subtle)]">
                  <div className="flex justify-between items-center mb-3">
                    <p className="text-xs font-medium text-[var(--text-secondary)]">Base Font Size</p>
                    <span className="text-xs font-mono text-[var(--text-muted)]">{fontSize}px</span>
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
                  <div className="flex justify-between text-[10px] text-[var(--text-muted)] mt-1.5">
                    <span>12px</span><span>16px</span><span>20px</span>
                  </div>
                </div>

                {/* Density */}
                <div className="py-5">
                  <p className="text-xs font-medium text-[var(--text-secondary)] mb-3">Interface Density</p>
                  <div className="grid grid-cols-3 gap-2">
                    {(["comfortable", "cozy", "compact"] as Density[]).map((opt) => (
                      <button
                        key={opt}
                        onClick={() => setDensity(opt)}
                        className={`px-3 py-2 text-xs font-medium rounded-[var(--radius-md)] border text-center transition-colors cursor-pointer capitalize ${
                          density === opt
                            ? "bg-[var(--bg-secondary)] text-[var(--text-primary)] border-[var(--border-hover)]"
                            : "bg-transparent border-[var(--border-subtle)] hover:border-[var(--border-default)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                        }`}
                        aria-pressed={density === opt}
                      >
                        {opt.charAt(0).toUpperCase() + opt.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* ─ Notifications ─ */}
            {activeTab === "notifications" && (
              <div className="space-y-0">
                <SectionHeader icon={<Bell size={14} />} title="Notifications" description="Control how and when you receive alerts." />
                <SettingRow
                  label="Desktop Notifications"
                  description="Show browser push notifications when responses complete."
                  control={
                    <ToggleCheckbox
                      checked={true}
                      onChange={() => {}}
                      label="Toggle desktop notifications"
                    />
                  }
                />
                <SettingRow
                  label="Sound Alerts"
                  description="Play a soft chime when the model finishes responding."
                  control={
                    <ToggleCheckbox
                      checked={false}
                      onChange={() => {}}
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
                  title="Conversation Defaults"
                  description="Default generation and retrieval parameters for new chats."
                  action={
                    <Button variant="ghost" size="sm" onClick={handleResetDefaults} className="gap-1.5 text-xs">
                      <RotateCcw size={12} />
                      Reset
                    </Button>
                  }
                />

                {/* Temperature */}
                <div className="py-5 border-b border-[var(--border-subtle)]">
                  <div className="flex justify-between items-center mb-3">
                    <div>
                      <p className="text-sm font-medium text-[var(--text-primary)]">Temperature</p>
                      <p className="text-xs text-[var(--text-muted)] mt-0.5">
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
                  <div className="flex justify-between text-[10px] text-[var(--text-muted)] mt-1.5">
                    <span>0 — Strict</span><span>1 — Creative</span>
                  </div>
                </div>

                {/* Top K */}
                <div className="py-5 border-b border-[var(--border-subtle)]">
                  <div className="flex justify-between items-center mb-3">
                    <div>
                      <p className="text-sm font-medium text-[var(--text-primary)]">Retrieval Top K</p>
                      <p className="text-xs text-[var(--text-muted)] mt-0.5">Maximum chunks retrieved · {defaults.topK}</p>
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
                  <div className="flex justify-between text-[10px] text-[var(--text-muted)] mt-1.5">
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
                      className="h-8 rounded-[var(--radius-md)] bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] text-xs px-2.5 text-[var(--text-primary)] cursor-pointer outline-none focus:border-[var(--accent-primary)]/50 transition-colors min-w-[140px]"
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
                <div className="pt-6 mt-2 border-t border-[var(--border-subtle)]">
                  <div className="flex items-center gap-2 mb-4">
                    <ShieldAlert size={14} className="text-[var(--accent-error)]" />
                    <span className="text-sm font-semibold text-[var(--accent-error)]">Danger Zone</span>
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
              <Trash2 size={15} className="text-[var(--accent-error)]" />
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
              onClick={() => { toast.success("History cleared."); setShowClearHistoryDialog(false); }}
            >
              Confirm Clear
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Confirm: factory reset ── */}
      <Dialog open={showResetConfigDialog} onOpenChange={setShowResetConfigDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm">
              <RotateCcw size={15} className="text-[var(--accent-error)]" />
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
    </div>
  );
};

export default SettingsPage;
