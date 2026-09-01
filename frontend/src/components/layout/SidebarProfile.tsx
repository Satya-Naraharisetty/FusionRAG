import React from "react";
import { useNavigate } from "react-router-dom";
import { Settings, LogOut, ChevronUp, Activity, Cloud, Loader2, CloudOff } from "lucide-react";
import { Avatar, AvatarFallback } from "../ui/Avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/Dropdown";
import { cn } from "../../lib/utils";
import { useLocale } from "../../lib/messages";
import { useLocalConversationMetadata } from "../../hooks/useLocalConversationMetadata";

interface SidebarProfileProps {
  user: { email: string; role: string } | null;
  logout: () => void;
  collapsed: boolean;
}

export const SidebarProfile: React.FC<SidebarProfileProps> = ({ user, logout, collapsed }) => {
  const { t } = useLocale();
  const navigate = useNavigate();
  const { syncStatus } = useLocalConversationMetadata();

  const initials = user?.email
    ? user.email
        .split("@")[0]
        .split(/[._-]/)
        .slice(0, 2)
        .map((p) => p[0]?.toUpperCase() || "")
        .join("") || "US"
    : "US";

  return (
    <div className="p-2 mt-auto border-t border-[var(--border-subtle)]/50">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className={cn(
              "flex items-center w-full rounded-[var(--radius-lg)] px-2 py-2 hover:bg-[var(--bg-tertiary)] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/50 cursor-pointer text-left min-h-[44px]",
              collapsed ? "justify-center" : "gap-3",
            )}
            aria-label="User profile menu"
          >
            <Avatar className="h-8 w-8 flex-shrink-0 bg-[#f97373] text-white border-0 shadow-xs">
              <AvatarFallback className="text-[11px] font-bold text-white bg-[#f97373]">
                {initials}
              </AvatarFallback>
            </Avatar>

            {!collapsed && user && (
              <>
                <div className="flex-1 min-w-0 text-left">
                  <p className="text-[13px] font-medium text-[var(--text-primary)] truncate leading-tight">
                    {user.email}
                  </p>
                  <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)] mt-0.5 leading-tight">
                    <span className="capitalize">{user.role === "admin" ? "Admin" : "User"}</span>
                    <span>•</span>
                    <span
                      className={cn(
                        "flex items-center gap-0.5 text-[10px]",
                        syncStatus === "saving" && "text-amber-500",
                        syncStatus === "error" && "text-red-400",
                        syncStatus === "synced" && "text-emerald-500 dark:text-emerald-400",
                      )}
                    >
                      {syncStatus === "saving" ? (
                        <>
                          <Loader2 size={10} className="animate-spin" />
                          <span>Syncing...</span>
                        </>
                      ) : syncStatus === "error" ? (
                        <>
                          <CloudOff size={10} />
                          <span>Sync error</span>
                        </>
                      ) : (
                        <>
                          <Cloud size={10} />
                          <span>Synced</span>
                        </>
                      )}
                    </span>
                  </div>
                </div>
                <ChevronUp
                  size={14}
                  className="flex-shrink-0 text-[var(--text-muted)] opacity-70"
                />
              </>
            )}
          </button>
        </DropdownMenuTrigger>

        <DropdownMenuContent side="top" align="start" className="w-52 mb-1">
          {/* User info header */}
          {user && (
            <div className="px-2.5 py-2 mb-1">
              <p className="text-xs font-medium text-[var(--text-primary)] truncate">
                {user.email}
              </p>
              <p className="text-[11px] text-[var(--text-muted)] capitalize mt-0.5">{user.role}</p>
            </div>
          )}

          <DropdownMenuItem onClick={() => navigate("/settings")} className="gap-2 cursor-pointer">
            <Settings size={13} />
            <span>{t("nav.settings")}</span>
          </DropdownMenuItem>

          {user?.role === "admin" && (
            <DropdownMenuItem
              onClick={() => navigate("/admin/dashboard")}
              className="gap-2 cursor-pointer"
            >
              <Activity size={13} className="text-[var(--accent-primary)]" />
              <span>{t("nav.admin")}</span>
            </DropdownMenuItem>
          )}

          <DropdownMenuSeparator />

          <DropdownMenuItem
            onClick={logout}
            className="gap-2 text-[var(--accent-error)] focus:bg-red-500/10 focus:text-red-400 cursor-pointer"
          >
            <LogOut size={13} />
            <span>{t("nav.logout")}</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
};
