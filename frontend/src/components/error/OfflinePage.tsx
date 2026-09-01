import React from "react";
import { WifiOff, RefreshCw } from "lucide-react";
import { Button } from "../ui/Button";

export const OfflinePage: React.FC = () => {
  const handleReload = () => {
    window.location.reload();
  };

  return (
    <div className="flex h-dvh w-dvw flex-col items-center justify-center bg-[var(--bg-primary)] p-6 text-center text-[var(--text-primary)] select-none">
      <div className="flex h-16 w-16 items-center justify-center rounded-[var(--radius-xl)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] mb-5">
        <WifiOff size={32} className="text-red-400 animate-pulse" />
      </div>
      <h1 className="font-title font-bold text-xl text-[var(--text-primary)] mb-1">
        You're Offline
      </h1>
      <p className="text-xs text-[var(--text-secondary)] max-w-sm mb-6 leading-relaxed">
        We can't establish a connection to the network. Check your device's Wi-Fi or data connection
        and try again.
      </p>
      <Button variant="secondary" size="sm" onClick={handleReload} className="gap-1.5">
        <RefreshCw size={14} />
        <span>Try Reconnecting</span>
      </Button>
    </div>
  );
};
