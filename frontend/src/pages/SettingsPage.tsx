import React, { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { useTheme, Theme, Density } from "../context/ThemeContext";
import {
  Settings as SettingsIcon,
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

const defaultValues: ConversationDefaults = {
  temperature: 0.0,
  retrievalMode: "hybrid",
  topK: 10,
  stream: false,
  hybridEnabled: true,
};

const SettingsPage: React.FC = () => {
  const { user } = useAuth();
  const { theme, setTheme, fontSize, setFontSize, density, setDensity } = useTheme();

  const [activeTab, setActiveTab] = useState<"profile" | "appearance" | "notifications" | "data" | "advanced">("profile");

  // Defaults
  const [defaults, setDefaults] = useState<ConversationDefaults>(() => {
    const saved = localStorage.getItem("conversation-defaults");
    if (saved) {
      try {
        return { ...defaultValues, ...JSON.parse(saved) };
      } catch (_e) {
        // use default
      }
    }
    return defaultValues;
  });

  // Modal checks
  const [showClearHistoryDialog, setShowClearHistoryDialog] = useState(false);
  const [showResetConfigDialog, setShowResetConfigDialog] = useState(false);

  const updateSetting = <K extends keyof ConversationDefaults>(
    key: K,
    value: ConversationDefaults[K]
  ) => {
    const updated = { ...defaults, [key]: value };
    setDefaults(updated);
    localStorage.setItem("conversation-defaults", JSON.stringify(updated));
  };

  const handleResetDefaults = () => {
    setDefaults(defaultValues);
    localStorage.setItem("conversation-defaults", JSON.stringify(defaultValues));
    toast.success("Conversation defaults reset to system defaults!");
  };

  const handleExportData = () => {
    const data: Record<string, string> = {};
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key) {
        data[key] = localStorage.getItem(key) || "";
      }
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `hybrid-rag-backup-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    toast.success("Preferences and folder data exported successfully.");
  };

  const handleImportData = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const parsed = JSON.parse(event.target?.result as string);
        Object.entries(parsed).forEach(([key, val]) => {
          localStorage.setItem(key, val as string);
        });
        toast.success("Configuration imported! Reloading...");
        setTimeout(() => window.location.reload(), 1000);
      } catch (_e) {
        toast.error("Invalid configuration backup file.");
      }
    };
    reader.readAsText(file);
  };

  const handleClearHistory = () => {
    // Mock deleting conversation history
    toast.success("All conversation history cleared.");
    setShowClearHistoryDialog(false);
  };

  const handleWipePreferences = () => {
    localStorage.clear();
    toast.success("All preferences reset! Reloading...");
    setTimeout(() => window.location.reload(), 1000);
  };

  const userInitials = user?.email
    ? user.email.slice(0, 2).toUpperCase()
    : "US";

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 md:p-8 bg-white dark:bg-[var(--bg-primary,#0D0D0D)] scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="space-y-1">
          <h1 className="text-lg font-bold font-title text-zinc-800 dark:text-zinc-150 flex items-center gap-2">
            <SettingsIcon size={18} className="text-zinc-500" />
            <span>Settings Console</span>
          </h1>
          <p className="text-xs text-zinc-500">
            Configure system execution defaults and user account preferences.
          </p>
        </div>

        <div className="flex flex-col md:flex-row gap-6">
          {/* Navigation tabs column */}
          <div className="w-full md:w-48 flex flex-row md:flex-col gap-1 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0 border-b md:border-b-0 md:border-r border-zinc-200/50 dark:border-zinc-900 pr-0 md:pr-4 flex-shrink-0 select-none">
            {([
              { id: "profile", label: "Profile", icon: <User size={14} /> },
              { id: "appearance", label: "Appearance", icon: <Palette size={14} /> },
              { id: "notifications", label: "Notifications", icon: <Bell size={14} /> },
              { id: "advanced", label: "Conversation", icon: <Sliders size={14} /> },
              { id: "data", label: "Data Sync", icon: <Database size={14} /> },
            ] as const).map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-xl transition-all duration-205 cursor-pointer whitespace-nowrap ${
                  activeTab === tab.id
                    ? "bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-150 border border-zinc-200/60 dark:border-zinc-700/40 shadow-xs"
                    : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-350 hover:bg-zinc-100/50 dark:hover:bg-zinc-900/20 border border-transparent"
                }`}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </div>

          {/* Tab content panel */}
          <div className="flex-1 min-w-0">
            {activeTab === "profile" && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="border-b border-[var(--border-color)] pb-3">
                  <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-1.5">
                    <User size={14} className="text-zinc-500" />
                    <span>User Profile</span>
                  </h3>
                  <p className="text-[11px] text-zinc-500 mt-0.5">Your identity details</p>
                </div>
                
                <div className="flex items-center gap-4 py-1">
                    <Avatar className="h-12 w-12 bg-violet-950/40 border border-violet-900/30 text-violet-300 shadow-md">
                      <AvatarFallback className="text-sm font-bold bg-transparent">
                        {userInitials}
                      </AvatarFallback>
                    </Avatar>
                    <div className="space-y-1 min-w-0">
                      <h4 className="text-xs font-bold text-zinc-200 truncate">
                        {user?.email}
                      </h4>
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center px-1.5 py-0.5 text-[8px] font-extrabold uppercase rounded bg-zinc-900 text-zinc-400 border border-zinc-800/40">
                          Role: {user?.role}
                        </span>
                        <span className="inline-flex items-center px-1.5 py-0.5 text-[8px] font-extrabold uppercase rounded bg-emerald-950 text-emerald-400 border border-emerald-900/10">
                          Active
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

            {activeTab === "appearance" && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="border-b border-[var(--border-color)] pb-3">
                  <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-1.5">
                    <Palette size={14} className="text-zinc-500" />
                    <span>Appearance Options</span>
                  </h3>
                  <p className="text-[11px] text-zinc-500 mt-0.5">Customize font sizes, theme selection, and spacing layout density</p>
                </div>

                {/* Theme Selector */}
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block">
                    Theme Mode
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {[
                      { id: "dark", label: "Dark mode" },
                      { id: "light", label: "Light mode" },
                      { id: "system", label: "System theme" },
                      { id: "high-contrast", label: "High contrast" },
                    ].map((opt) => (
                      <button
                        key={opt.id}
                        onClick={() => setTheme(opt.id as Theme)}
                        className={`px-3 py-2.5 text-xs font-semibold rounded-xl border text-center transition-all duration-200 cursor-pointer ${
                          theme === opt.id
                            ? "bg-zinc-200 dark:bg-zinc-800 text-zinc-950 dark:text-zinc-150 border-zinc-300 dark:border-zinc-700 shadow-xs"
                            : "bg-transparent border-[var(--border-color)] hover:border-[var(--border-hover)] text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Font Size Slider */}
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-xs font-semibold text-zinc-300">
                    <span>Base Font Size ({fontSize}px)</span>
                    <span className="text-[10px] text-zinc-500">Adjust text size globally</span>
                  </div>
                  <input
                    type="range"
                    min="12"
                    max="20"
                    step="1"
                    value={fontSize}
                    onChange={(e) => setFontSize(parseInt(e.target.value, 10))}
                    className="w-full h-1 bg-zinc-900 rounded-lg appearance-none cursor-pointer accent-zinc-700 focus-visible:outline-none"
                  />
                </div>

                {/* Layout Density */}
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block">
                    Interface Spacing Density
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { id: "comfortable", label: "Comfortable" },
                      { id: "cozy", label: "Cozy" },
                      { id: "compact", label: "Compact" },
                    ].map((opt) => (
                      <button
                        key={opt.id}
                        onClick={() => setDensity(opt.id as Density)}
                        className={`px-3 py-2 text-xs font-semibold rounded-xl border text-center transition-all duration-200 cursor-pointer ${
                          density === opt.id
                            ? "bg-zinc-200 dark:bg-zinc-800 text-zinc-950 dark:text-zinc-150 border-zinc-300 dark:border-zinc-700 shadow-xs"
                            : "bg-transparent border-[var(--border-color)] hover:border-[var(--border-hover)] text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === "notifications" && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="border-b border-[var(--border-color)] pb-3">
                  <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-1.5">
                    <Bell size={14} className="text-zinc-500" />
                    <span>Notification Settings</span>
                  </h3>
                  <p className="text-[11px] text-zinc-500 mt-0.5">Manage push notifications and sound alerts</p>
                </div>

                <div className="space-y-3.5">
                  <div className="flex items-center justify-between gap-4">
                    <div className="space-y-0.5">
                      <span className="text-xs font-semibold text-zinc-300 block">Desktop Notifications</span>
                      <span className="text-[9px] text-zinc-500 block">Show browser push notifications for answers</span>
                    </div>
                    <input
                      type="checkbox"
                      defaultChecked
                      className="h-4 w-4 bg-zinc-900 border-zinc-800 rounded accent-zinc-700 focus-visible:outline-none cursor-pointer"
                    />
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <div className="space-y-0.5">
                      <span className="text-xs font-semibold text-zinc-300 block">Sound alerts</span>
                      <span className="text-[9px] text-zinc-500 block">Play soft notification chimes when tool finishes</span>
                    </div>
                    <input
                      type="checkbox"
                      className="h-4 w-4 bg-zinc-900 border-zinc-800 rounded accent-zinc-700 focus-visible:outline-none cursor-pointer"
                    />
                  </div>
                </div>
              </div>
            )}

            {activeTab === "advanced" && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-3">
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-1.5">
                      <Sliders size={14} className="text-zinc-500" />
                      <span>Conversation Defaults</span>
                    </h3>
                    <p className="text-[11px] text-zinc-500 mt-0.5">Adjust default generation settings for LLM sessions</p>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={handleResetDefaults}
                    className="h-7 text-[10px] gap-1 hover:bg-zinc-800 hover:text-zinc-100 text-zinc-400 font-semibold cursor-pointer rounded-lg border border-[var(--border-color)] px-2.5"
                  >
                    <RotateCcw size={10} />
                    <span>Reset Defaults</span>
                  </Button>
                </div>

                {/* Temperature */}
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-[11px] font-semibold text-zinc-300">
                    <span>LLM Temperature ({defaults.temperature.toFixed(1)})</span>
                    <span className="text-[10px] text-zinc-500">
                      {defaults.temperature === 0 ? "Strict / Deterministic" : "Creative / Generative"}
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={defaults.temperature}
                    onChange={(e) => updateSetting("temperature", parseFloat(e.target.value))}
                    className="w-full h-1 bg-zinc-900 rounded-lg appearance-none cursor-pointer accent-zinc-700 focus-visible:outline-none"
                  />
                </div>

                {/* Top K */}
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-[11px] font-semibold text-zinc-300">
                    <span>Retrieval Top K ({defaults.topK})</span>
                    <span className="text-[10px] text-zinc-500">Maximum retrieved chunks</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="20"
                    step="1"
                    value={defaults.topK}
                    onChange={(e) => updateSetting("topK", parseInt(e.target.value, 10))}
                    className="w-full h-1 bg-zinc-900 rounded-lg appearance-none cursor-pointer accent-zinc-700 focus-visible:outline-none"
                  />
                </div>

                {/* Retrieval Mode select */}
                <div className="flex items-center justify-between gap-4">
                  <div className="space-y-0.5">
                    <span className="text-[11px] font-semibold text-zinc-300 block">Retrieval Mode</span>
                    <span className="text-[9px] text-zinc-500 block">Grounding search method</span>
                  </div>
                  <select
                    value={defaults.retrievalMode}
                    onChange={(e) => updateSetting("retrievalMode", e.target.value as ConversationDefaults["retrievalMode"])}
                    className="h-8.5 rounded-xl bg-zinc-900 border border-[var(--border-color)] text-xs px-3 focus-visible:outline-none focus:ring-1 focus:ring-zinc-700 focus:border-zinc-700 text-zinc-300 font-semibold cursor-pointer"
                  >
                    <option value="hybrid">Hybrid Search</option>
                    <option value="semantic">Semantic (Dense)</option>
                    <option value="sparse">Keyword (Sparse)</option>
                    <option value="auto">Auto Selection</option>
                  </select>
                </div>

                {/* Toggle Streaming */}
                <div className="flex items-center justify-between gap-4">
                  <div className="space-y-0.5">
                    <span className="text-[11px] font-semibold text-zinc-300 block">SSE Response Streaming</span>
                    <span className="text-[9px] text-zinc-500 block">Streams LLM tokens chunk-by-chunk</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={defaults.stream}
                    onChange={(e) => updateSetting("stream", e.target.checked)}
                    className="h-4 w-4 bg-zinc-900 border-[var(--border-color)] rounded accent-zinc-700 focus-visible:outline-none cursor-pointer"
                  />
                </div>

                {/* Toggle Hybrid search */}
                <div className="flex items-center justify-between gap-4">
                  <div className="space-y-0.5">
                    <span className="text-[11px] font-semibold text-zinc-300 block">Enable Reciprocal Rank Fusion</span>
                    <span className="text-[9px] text-zinc-500 block">Merges keyword and semantic results</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={defaults.hybridEnabled}
                    onChange={(e) => updateSetting("hybridEnabled", e.target.checked)}
                    className="h-4 w-4 bg-zinc-900 border-[var(--border-color)] rounded accent-zinc-700 focus-visible:outline-none cursor-pointer"
                  />
                </div>
              </div>
            )}

            {activeTab === "data" && (
              <div className="space-y-8 animate-in fade-in duration-200">
                {/* Sync & Backup */}
                <div className="space-y-4">
                  <div className="border-b border-[var(--border-color)] pb-3">
                    <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-1.5">
                      <Database size={14} className="text-zinc-500" />
                      <span>Data Sync & Backup</span>
                    </h3>
                    <p className="text-[11px] text-zinc-500 mt-0.5">Export preferences and folder data locally</p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    {/* Export */}
                    <div className="p-4 bg-zinc-900/10 border border-[var(--border-color)] rounded-xl space-y-2">
                      <span className="text-[11px] font-bold text-zinc-250 flex items-center gap-1">
                        <Download size={12} className="text-zinc-400" />
                        <span>Backup Preferences</span>
                      </span>
                      <p className="text-[9px] text-zinc-500 leading-normal">
                        Download folder structures, pinned conversation markers, custom search criteria, and workspace parameters.
                      </p>
                      <Button
                        onClick={handleExportData}
                        className="h-8.5 w-full bg-zinc-900/30 border border-[var(--border-color)] hover:bg-zinc-800 text-zinc-300 text-[10px] font-bold cursor-pointer rounded-xl gap-1.5 mt-1"
                      >
                        Export Backup JSON
                      </Button>
                    </div>

                    {/* Import */}
                    <div className="p-4 bg-zinc-900/10 border border-[var(--border-color)] rounded-xl space-y-2">
                      <span className="text-[11px] font-bold text-zinc-250 flex items-center gap-1">
                        <Upload size={12} className="text-zinc-400" />
                        <span>Restore Preferences</span>
                      </span>
                      <p className="text-[9px] text-zinc-500 leading-normal">
                        Restore backup configuration parameters. Warning: this replaces all active local settings and page layout folders.
                      </p>
                      <div className="relative">
                        <input
                          type="file"
                          accept=".json"
                          onChange={handleImportData}
                          className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
                        />
                        <Button className="h-8.5 w-full bg-zinc-900/30 border border-[var(--border-color)] hover:bg-zinc-800 text-zinc-300 text-[10px] font-bold cursor-pointer rounded-xl gap-1.5 mt-1">
                          Load JSON File
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Danger Zone */}
                <div className="space-y-4">
                  <div className="border-b border-red-900/20 pb-3">
                    <h3 className="text-sm font-semibold text-red-400 flex items-center gap-1.5">
                      <ShieldAlert size={14} className="text-red-500" />
                      <span>Danger Zone</span>
                    </h3>
                    <p className="text-[11px] text-zinc-500 mt-0.5">Destructive actions on local store data</p>
                  </div>

                  <div className="space-y-3.5">
                    {/* Clear history */}
                    <div className="flex items-center justify-between gap-4">
                      <div className="space-y-0.5">
                        <span className="text-xs font-bold text-zinc-200 block">Clear History</span>
                        <span className="text-[9px] text-zinc-500 block">Delete all conversation records and summaries.</span>
                      </div>
                      <Button
                        variant="destructive"
                        onClick={() => setShowClearHistoryDialog(true)}
                        className="bg-red-950/20 hover:bg-red-950/40 text-red-550 border border-red-900/35 text-[10px] font-bold h-8 px-4 cursor-pointer rounded-xl"
                      >
                        Clear History
                      </Button>
                    </div>

                    {/* Wipe all preferences */}
                    <div className="flex items-center justify-between gap-4">
                      <div className="space-y-0.5">
                        <span className="text-xs font-bold text-zinc-200 block">Factory Reset</span>
                        <span className="text-[9px] text-zinc-500 block">Clear local preferences, folders, tags, and sign out.</span>
                      </div>
                      <Button
                        variant="destructive"
                        onClick={() => setShowResetConfigDialog(true)}
                        className="bg-red-650 hover:bg-red-750 text-white text-[10px] font-bold h-8 px-4 cursor-pointer rounded-xl"
                      >
                        Reset Console
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <Dialog open={showClearHistoryDialog} onOpenChange={setShowClearHistoryDialog}>
        <DialogContent className="bg-[var(--bg-secondary,#171717)] border-[var(--border-color)] text-zinc-200 sm:max-w-md rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-zinc-100 flex items-center gap-2 text-sm font-semibold">
              <Trash2 size={16} className="text-red-500" />
              <span>Clear Conversation History?</span>
            </DialogTitle>
            <DialogDescription className="text-zinc-400 text-xs mt-2">
              This will permanently delete all conversations and message transcripts. This action is irreversible.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4 flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowClearHistoryDialog(false)}
              className="bg-transparent border-[var(--border-color)] text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 text-xs h-10 rounded-xl"
            >
              Cancel
            </Button>
            <Button
              onClick={handleClearHistory}
              className="bg-red-600 hover:bg-red-700 text-white text-xs font-semibold h-10 rounded-xl"
            >
              Confirm Clear
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showResetConfigDialog} onOpenChange={setShowResetConfigDialog}>
        <DialogContent className="bg-[var(--bg-secondary,#171717)] border-[var(--border-color)] text-zinc-200 sm:max-w-md rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-zinc-100 flex items-center gap-2 text-sm font-semibold">
              <RotateCcw size={16} className="text-red-500" />
              <span>Perform Factory Reset?</span>
            </DialogTitle>
            <DialogDescription className="text-zinc-400 text-xs mt-2">
              This will wipe all custom folders, color tag setups, pinned records, layout configurations, and settings. You will be signed out.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4 flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowResetConfigDialog(false)}
              className="bg-transparent border-[var(--border-color)] text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100 text-xs h-10 rounded-xl"
            >
              Cancel
            </Button>
            <Button
              onClick={handleWipePreferences}
              className="bg-red-600 hover:bg-red-700 text-white text-xs font-semibold h-10 rounded-xl"
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
