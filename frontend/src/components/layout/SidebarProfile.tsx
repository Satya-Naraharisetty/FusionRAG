import React from "react";
import { useNavigate } from "react-router-dom";
import { Settings, LogOut } from "lucide-react";
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

export const SidebarProfile: React.FC<SidebarProfileProps> = ({
  user,
  logout,
  collapsed,
}) => {
  const navigate = useNavigate();

  const userInitials = user?.email
    ? user.email.slice(0, 2).toUpperCase()
    : "US";

  return (
    <div
      style={{
        padding: "10px 10px",
        borderTop: "1px solid rgba(255,255,255,0.06)",
        marginTop: "auto",
        background: "transparent",
      }}
    >
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className={cn(
              "flex items-center w-full rounded-xl transition-all duration-200 focus:outline-none cursor-pointer text-left",
              collapsed ? "justify-center p-2" : "justify-between p-2.5"
            )}
            style={{
              background: "transparent",
              border: "none",
              minHeight: "52px",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.05)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
            }}
            aria-label="User profile menu"
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
              <Avatar
                style={{
                  width: "32px",
                  height: "32px",
                  flexShrink: 0,
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.10)",
                }}
              >
                <AvatarFallback
                  style={{
                    fontSize: "12px",
                    fontWeight: 700,
                    background: "transparent",
                    color: "#d4d4d8",
                  }}
                >
                  {userInitials}
                </AvatarFallback>
              </Avatar>
              {!collapsed && user && (
                <div style={{ textAlign: "left", minWidth: 0, flex: 1 }}>
                  <p
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "#e4e4e7",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      lineHeight: 1.3,
                      marginBottom: "2px",
                    }}
                  >
                    {user.email}
                  </p>
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 500,
                      color: "var(--text-muted, #737373)",
                      textTransform: "capitalize",
                    }}
                  >
                    {user.role}
                  </span>
                </div>
              )}
            </div>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-[200px]">
          <DropdownMenuItem
            onClick={() => navigate("/settings")}
            className="gap-2 focus:bg-zinc-900 focus:text-zinc-100 cursor-pointer text-sm font-medium"
          >
            <Settings size={14} />
            <span>Settings</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator className="bg-zinc-900" />
          <DropdownMenuItem
            onClick={logout}
            className="gap-2 text-red-400 focus:bg-red-950/20 focus:text-red-300 cursor-pointer text-sm font-medium"
          >
            <LogOut size={14} />
            <span>Sign Out</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
};
