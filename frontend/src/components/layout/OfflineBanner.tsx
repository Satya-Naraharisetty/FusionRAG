import React from "react";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { WifiOff } from "lucide-react";

export const OfflineBanner: React.FC = () => {
  const { isOnline } = useOnlineStatus();

  if (isOnline) return null;

  return (
    <div className="flex w-full items-center justify-center gap-2 bg-red-600 px-4 py-2 text-center text-xs font-semibold text-white shadow-md animate-in slide-in-from-top duration-300">
      <WifiOff size={14} className="animate-pulse" />
      <span>You are currently offline. Check your internet connection.</span>
    </div>
  );
};
