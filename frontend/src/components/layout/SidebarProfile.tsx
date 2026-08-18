import React from "react";
import { useNavigate } from "react-router-dom";
import { Settings, LogOut, ChevronUp, Activity } from "lucide-react";
import { Avatar, AvatarFallback } from "../ui/Avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/Dropdown";
import { cn } from "../../lib/utils";

interface SidebarProfileProps {
  user: { email: string; role: string } | null;
  logout: () => void;
  collapsed: boolean;
}

export const SidebarProfile: React.FC<SidebarProfileProps> = ({ user, logout, collapsed }) => {
  const navigate = useNavigate();
  const initials = user?.email ? user.email.slice(0, 2).toUpperCase() : "US";

  return (
    <div className="p-2 mt-auto">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className={cn(
              "flex items-center w-full rounded-[var(--radius-md)] px-2 py-2 hover:bg-[var(--bg-tertiary)] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/50 cursor-pointer text-left min-h-[44px]",
              collapsed ? "justify-center" : "gap-2.5"
            )}
            aria-label="User profile menu"
          >
            <Avatar className="h-7 w-7 flex-shrink-0 bg-[var(--bg-tertiary)] border border-[var(--border-default)]">
              <AvatarFallback className="text-[11px] font-semibold">{initials}</AvatarFallback>
            </Avatar>

            {!collapsed && user && (
              <>
                <div className="flex-1 min-w-0 text-left">
                  <p className="text-[13px] font-medium text-[var(--text-primary)] truncate leading-snug">
                    {user.email}
                  </p>
                  <span className="text-[11px] text-[var(--text-muted)] capitalize block leading-tight">
                    {user.role}
                  </span>
                </div>
                <ChevronUp size={13} className="flex-shrink-0 text-[var(--text-muted)]" />
              </>
            )}
          </button>
        </DropdownMenuTrigger>

        <DropdownMenuContent side="top" align="start" className="w-52 mb-1">
          {/* User info header */}
          {user && (
            <div className="px-2.5 py-2 mb-1">
              <p className="text-xs font-medium text-[var(--text-primary)] truncate">{user.email}</p>
              <p className="text-[11px] text-[var(--text-muted)] capitalize mt-0.5">{user.role}</p>
            </div>
          )}

          <DropdownMenuItem
            onClick={() => navigate("/settings")}
            className="gap-2 cursor-pointer"
          >
            <Settings size={13} />
            <span>Settings</span>
          </DropdownMenuItem>

          {user?.role === "admin" && (
            <DropdownMenuItem
              onClick={() => navigate("/admin/dashboard")}
              className="gap-2 cursor-pointer"
            >
              <Activity size={13} className="text-[var(--accent-primary)]" />
              <span>Admin Console</span>
            </DropdownMenuItem>
          )}

          <DropdownMenuSeparator />

          <DropdownMenuItem
            onClick={logout}
            className="gap-2 text-[var(--accent-error)] focus:bg-red-500/10 focus:text-red-400 cursor-pointer"
          >
            <LogOut size={13} />
            <span>Sign out</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
};
