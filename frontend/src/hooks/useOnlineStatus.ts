import { useState, useEffect } from "react";
import toast from "react-hot-toast";

export const useOnlineStatus = () => {
  const [isOnline, setIsOnline] = useState<boolean>(() => navigator.onLine);
  const [wasOffline, setWasOffline] = useState<boolean>(false);

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      setWasOffline(true);
      toast.success("Connection restored. You're back online.", {
        id: "offline-reconnect",
      });

      const timer = setTimeout(() => {
        setWasOffline(false);
      }, 3000);
      return () => clearTimeout(timer);
    };

    const handleOffline = () => {
      setIsOnline(false);
      toast.error("Internet connection lost. Offline mode active.", {
        id: "offline-reconnect",
        duration: Infinity,
      });
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  return { isOnline, wasOffline };
};
