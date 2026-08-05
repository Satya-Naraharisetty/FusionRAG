import React, { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { Menu } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "../ui/sheet";
import { Sidebar } from "../sidebar/Sidebar";
import { Button } from "../ui/button";

interface MobileDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const MobileDrawer: React.FC<MobileDrawerProps> = ({ open, onOpenChange }) => {
  const location = useLocation();

  // Auto close drawer when route changes
  useEffect(() => {
    onOpenChange(false);
  }, [location.pathname, onOpenChange]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden h-9 w-9 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 focus-visible:ring-0"
          aria-label="Open navigation menu"
        >
          <Menu size={20} />
        </Button>
      </SheetTrigger>
      <SheetContent
        side="left"
        className="p-0 w-[260px] bg-zinc-950 border-r border-zinc-800 text-zinc-300 h-full"
      >
        <Sidebar className="w-full h-full border-r-0" />
      </SheetContent>
    </Sheet>
  );
};
