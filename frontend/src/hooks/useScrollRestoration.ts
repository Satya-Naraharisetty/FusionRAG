import { useEffect } from "react";

const scrollPositions = new Map<string, number>();

export const useScrollRestoration = (
  id: string | null,
  containerRef: React.RefObject<HTMLDivElement>
) => {
  useEffect(() => {
    if (!id || !containerRef.current) return;

    const container = containerRef.current;

    const handleScroll = () => {
      scrollPositions.set(id, container.scrollTop);
    };

    // Restore scroll position
    const saved = scrollPositions.get(id);
    if (saved !== undefined) {
      container.scrollTop = saved;
    } else {
      // Default to bottom for new/unvisited chats
      container.scrollTop = container.scrollHeight;
    }

    container.addEventListener("scroll", handleScroll);
    return () => {
      container.removeEventListener("scroll", handleScroll);
    };
  }, [id, containerRef]);
};
