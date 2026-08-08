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
    <div className="p-3 border-t border-zinc-800/40 mt-auto bg-[#171717]/80 backdrop-blur-md">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className={cn(
              "flex items-center w-full rounded-xl hover:bg-zinc-800/40 border border-transparent transition-all duration-200 focus:outline-none p-1.5 cursor-pointer text-left",
              collapsed ? "justify-center" : "justify-between"
            )}
            aria-label="User profile menu"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <Avatar className="h-8 w-8 bg-zinc-800 border border-zinc-700/60 text-zinc-300 flex-shrink-0">
                <AvatarFallback className="text-[11px] font-bold bg-transparent">
                  {userInitials}
                </AvatarFallback>
              </Avatar>
              {!collapsed && user && (
                <div className="text-left min-w-0 flex-1">
                  <p className="text-[11px] font-bold text-zinc-200 truncate leading-tight">
                    {user.email}
                  </p>
                  <span className="inline-flex items-center px-1.5 py-0.5 mt-0.5 text-[8px] font-extrabold uppercase rounded bg-zinc-900 text-zinc-400 border border-zinc-800/50 tracking-wider">
                    {user.role}
                  </span>
                </div>
              )}
            </div>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-[190px] bg-zinc-950 border-zinc-850 text-zinc-300">
          <DropdownMenuItem
            onClick={() => navigate("/settings")}
            className="gap-2 focus:bg-zinc-900 focus:text-zinc-100 cursor-pointer text-xs font-medium"
          >
            <Settings size={14} />
            <span>Settings</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator className="bg-zinc-900" />
          <DropdownMenuItem
            onClick={logout}
            className="gap-2 text-red-400 focus:bg-red-950/20 focus:text-red-300 cursor-pointer text-xs font-medium"
          >
            <LogOut size={14} />
            <span>Sign Out</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
};
