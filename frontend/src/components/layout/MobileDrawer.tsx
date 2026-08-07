import React, { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Menu } from "lucide-react";
import { Sidebar } from "../sidebar/Sidebar";
import { Button } from "../ui/button";
import { cn } from "../../lib/utils";

interface MobileDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const MobileDrawer: React.FC<MobileDrawerProps> = ({ open, onOpenChange }) => {
  const location = useLocation();
  const [translateY, setTranslateY] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const touchStart = useRef<{ y: number; time: number } | null>(null);
  const sheetRef = useRef<HTMLDivElement>(null);

  // Close drawer on path change
  useEffect(() => {
    onOpenChange(false);
  }, [location.pathname, onOpenChange]);

  // Reset local offsets when open state changes
  useEffect(() => {
    setTranslateY(0);
  }, [open]);

  // Touch handlers for sheet dragging
  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0];
    touchStart.current = { y: touch.clientY, time: Date.now() };
    setIsDragging(true);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchStart.current) return;
    const touch = e.touches[0];
    const diffY = touch.clientY - touchStart.current.y;

    // Only allow swiping down to close (diffY > 0)
    if (diffY > 0) {
      setTranslateY(diffY);
    }
  };

  const handleTouchEnd = () => {
    if (!touchStart.current) return;
    setIsDragging(false);

    const deltaY = translateY;
    const deltaTime = Date.now() - touchStart.current.time;
    const velocity = deltaY / (deltaTime || 1); // pixels per ms

    touchStart.current = null;

    // If dragged down past threshold (120px) or swiped down fast (velocity > 0.5 px/ms), close it.
    if (deltaY > 120 || velocity > 0.5) {
      onOpenChange(false);
    } else {
      // Bounce back to open position
      setTranslateY(0);
    }
  };

  return (
    <>
      {/* Trigger Button (Visible on mobile headers) */}
      <Button
        variant="ghost"
        size="icon"
        onClick={() => onOpenChange(true)}
        className="md:hidden h-9 w-9 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 focus-visible:ring-0 cursor-pointer"
        aria-label="Open navigation menu"
      >
        <Menu size={20} />
      </Button>

      {/* Sheet Backdrop blur overlay */}
      {open && (
        <div
          onClick={() => onOpenChange(false)}
          className="fixed inset-0 bg-black/60 backdrop-blur-xs z-40 md:hidden transition-opacity duration-300 animate-in fade-in"
          aria-hidden="true"
        />
      )}

      {/* Swipeable Bottom Sheet */}
      <div
        ref={sheetRef}
        style={{
          transform: open
            ? `translateY(${translateY}px)`
            : "translateY(100%)",
          transition: isDragging ? "none" : "transform 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        }}
        className={cn(
          "fixed bottom-0 left-0 right-0 h-[80vh] bg-zinc-950 border-t border-zinc-800/80 rounded-t-[24px] shadow-2xl z-50 md:hidden flex flex-col overflow-hidden select-none",
          !open && "pointer-events-none"
        )}
      >
        {/* Drag Handle Area */}
        <div
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          className="w-full py-4 flex items-center justify-center cursor-grab active:cursor-grabbing border-b border-zinc-900/30 flex-shrink-0"
        >
          <div className="w-12 h-1 bg-zinc-800 rounded-full hover:bg-zinc-700 transition-colors duration-200" />
        </div>

        {/* Sidebar View content nested */}
        <div className="flex-1 overflow-hidden">
          <Sidebar className="w-full h-full border-r-0" />
        </div>
      </div>
    </>
  );
};
