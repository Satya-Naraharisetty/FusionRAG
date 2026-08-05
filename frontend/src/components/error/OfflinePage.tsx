import React from "react";
import { WifiOff, RefreshCw } from "lucide-react";
import { Button } from "../ui/button";

export const OfflinePage: React.FC = () => {
  const handleReload = () => {
    window.location.reload();
  };

  return (
    <div className="flex h-screen w-screen flex-col items-center justify-center bg-zinc-950 p-6 text-center text-zinc-300 select-none">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-900 border border-zinc-800/80 mb-5 shadow-lg">
        <WifiOff size={32} className="text-red-500 animate-pulse" />
      </div>
      <h1 className="font-title font-bold text-lg text-zinc-100 mb-1">
        You're Offline
      </h1>
      <p className="text-xs text-zinc-500 max-w-sm mb-6 leading-relaxed">
        We can't establish a connection to the network. Check your device's Wi-Fi or data connection and try again.
      </p>
      <Button
        onClick={handleReload}
        className="bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-300 text-xs px-4 h-9 gap-1.5 shadow-md"
      >
        <RefreshCw size={14} />
        <span>Try Reconnecting</span>
      </Button>
    </div>
  );
};
