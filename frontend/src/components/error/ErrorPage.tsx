import React from "react";
import { useNavigate } from "react-router-dom";
import { ShieldAlert, FileQuestion, ServerCrash, Home, RefreshCw } from "lucide-react";
import { Button } from "../ui/button";

interface ErrorPageProps {
  status: 401 | 403 | 404 | 500;
}

export const ErrorPage: React.FC<ErrorPageProps> = ({ status }) => {
  const navigate = useNavigate();

  const configs = {
    401: {
      icon: <ShieldAlert size={32} className="text-amber-500" />,
      title: "Session Expired",
      desc: "Your secure session has expired or has been invalidated. Please log back in to continue.",
      action: () => navigate("/login"),
      label: "Go to Sign In",
    },
    403: {
      icon: <ShieldAlert size={32} className="text-red-500" />,
      title: "Access Denied",
      desc: "You do not have the required permissions to view this resource.",
      action: () => navigate("/"),
      label: "Go to Dashboard",
    },
    404: {
      icon: <FileQuestion size={32} className="text-zinc-500" />,
      title: "Page Not Found",
      desc: "The page you are looking for does not exist or has been relocated.",
      action: () => navigate("/"),
      label: "Go to Dashboard",
    },
    500: {
      icon: <ServerCrash size={32} className="text-red-500" />,
      title: "System Error",
      desc: "Our backend API servers encountered an unexpected failure. We are working on resolving it.",
      action: () => window.location.reload(),
      label: "Try Reconnecting",
    },
  };

  const current = configs[status] || configs[404];

  return (
    <div className="flex h-screen w-screen flex-col items-center justify-center bg-zinc-950 p-6 text-center text-zinc-300 select-none">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-900 border border-zinc-800/80 mb-5 shadow-lg">
        {current.icon}
      </div>
      <h1 className="font-title font-bold text-lg text-zinc-100 mb-1">{current.title}</h1>
      <p className="text-xs text-zinc-500 max-w-sm mb-6 leading-relaxed">{current.desc}</p>
      <Button
        onClick={current.action}
        className="bg-violet-600 hover:bg-violet-700 text-white text-xs px-4 h-9 gap-1.5 shadow-md"
      >
        {status === 500 ? <RefreshCw size={14} /> : <Home size={14} />}
        <span>{current.label}</span>
      </Button>
    </div>
  );
};
