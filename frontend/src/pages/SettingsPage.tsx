import React, { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { Settings, User, Sliders, ShieldAlert, RotateCcw } from "lucide-react";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Avatar, AvatarFallback } from "../components/ui/avatar";

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
  const { user, logout } = useAuth();

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

  const updateSetting = <K extends keyof ConversationDefaults>(
    key: K,
    value: ConversationDefaults[K]
  ) => {
    const updated = { ...defaults, [key]: value };
    setDefaults(updated);
    localStorage.setItem("conversation-defaults", JSON.stringify(updated));
  };

  const handleReset = () => {
    setDefaults(defaultValues);
    localStorage.setItem("conversation-defaults", JSON.stringify(defaultValues));
  };

  const userInitials = user?.email
    ? user.email.slice(0, 2).toUpperCase()
    : "US";

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 md:p-8 bg-zinc-950 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="space-y-1">
          <h1 className="text-lg font-bold font-title text-zinc-100 flex items-center gap-2">
            <Settings size={18} className="text-violet-500" />
            <span>Settings Console</span>
          </h1>
          <p className="text-xs text-zinc-500">
            Configure system execution defaults and user account preferences.
          </p>
        </div>

        {/* Profile Card */}
        <Card className="bg-zinc-950/40 border-zinc-900">
          <CardContent className="p-4 space-y-4">
            <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5 border-b border-zinc-900 pb-2">
              <User size={14} className="text-zinc-500" />
              <span>User Profile</span>
            </h3>
            
            <div className="flex items-center gap-4">
              <Avatar className="h-12 w-12 bg-violet-950/40 border border-violet-900/30 text-violet-300">
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
          </CardContent>
        </Card>

        {/* Conversation Settings Card */}
        <Card className="bg-zinc-950/40 border-zinc-900">
          <CardContent className="p-4 space-y-5">
            <div className="flex items-center justify-between border-b border-zinc-900 pb-2">
              <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                <Sliders size={14} className="text-zinc-500" />
                <span>Conversation Defaults</span>
              </h3>
              <Button
                variant="ghost"
                onClick={handleReset}
                className="h-6 text-[10px] gap-1 hover:bg-zinc-900 hover:text-zinc-100 text-zinc-500 font-semibold cursor-pointer"
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
                className="w-full h-1 bg-zinc-900 rounded-lg appearance-none cursor-pointer accent-violet-600 focus-visible:outline-none"
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
                className="w-full h-1 bg-zinc-900 rounded-lg appearance-none cursor-pointer accent-violet-600 focus-visible:outline-none"
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
                className="h-8 rounded-md bg-zinc-900 border border-zinc-800 text-xs px-3 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-violet-600 text-zinc-300 font-semibold cursor-pointer"
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
                className="h-4 w-4 bg-zinc-900 border-zinc-800 rounded accent-violet-600 focus-visible:outline-none cursor-pointer"
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
                className="h-4 w-4 bg-zinc-900 border-zinc-800 rounded accent-violet-600 focus-visible:outline-none cursor-pointer"
              />
            </div>
          </CardContent>
        </Card>

        {/* Danger Zone Card */}
        <Card className="bg-red-950/5 border-red-900/10">
          <CardContent className="p-4 space-y-4">
            <h3 className="text-xs font-bold text-red-400 flex items-center gap-1.5 border-b border-red-900/10 pb-2">
              <ShieldAlert size={14} className="text-red-500" />
              <span>Danger Zone</span>
            </h3>
            
            <div className="flex items-center justify-between gap-4">
              <div className="space-y-0.5">
                <span className="text-xs font-bold text-zinc-200 block">Sign Out</span>
                <span className="text-[9px] text-zinc-500 block">Log out and terminate current session</span>
              </div>
              <Button
                variant="destructive"
                onClick={logout}
                className="bg-red-650 hover:bg-red-700 text-white text-xs h-8 px-4 font-semibold shadow-md cursor-pointer"
              >
                Logout
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default SettingsPage;
