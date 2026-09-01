import React from "react";
import { useNavigate } from "react-router-dom";
import { ShieldAlert, FileQuestion, ServerCrash, Home, RefreshCw } from "lucide-react";
import { Button } from "../ui/Button";

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
      icon: <FileQuestion size={32} className="text-[var(--text-muted)]" />,
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
    <div className="flex h-dvh w-dvw flex-col items-center justify-center bg-[var(--bg-primary)] p-6 text-center text-[var(--text-primary)] select-none">
      <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-[var(--radius-2xl)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
        {current.icon}
      </div>
      <h1 className="mb-1 text-2xl font-semibold tracking-tight text-[var(--text-primary)]">
        {current.title}
      </h1>
      <p className="mb-6 max-w-sm text-sm leading-relaxed text-[var(--text-secondary)]">
        {current.desc}
      </p>
      <Button variant="default" size="sm" onClick={current.action} className="gap-1.5">
        {status === 500 ? <RefreshCw size={14} /> : <Home size={14} />}
        <span>{current.label}</span>
      </Button>
    </div>
  );
};
