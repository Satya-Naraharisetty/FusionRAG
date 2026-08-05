import React, { useMemo } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Conversation } from "../../types";
import { ConversationItem } from "./ConversationItem";
import { isToday, isYesterday, subDays, isAfter } from "date-fns";

interface ConversationListProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
  searchQuery: string;
}

type FlatListItem =
  | { type: "header"; label: string; id: string }
  | { type: "conversation"; data: Conversation; id: string };

export const ConversationList: React.FC<ConversationListProps> = ({
  conversations,
  activeId,
  onSelect,
  onRename,
  onDelete,
  searchQuery,
}) => {
  const filteredConversations = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const lower = searchQuery.toLowerCase();
    return conversations.filter((c) => c.title.toLowerCase().includes(lower));
  }, [conversations, searchQuery]);

  // Group and flatten
  const flatItems = useMemo(() => {
    const today: Conversation[] = [];
    const yesterday: Conversation[] = [];
    const last7Days: Conversation[] = [];
    const older: Conversation[] = [];

    const now = new Date();
    const sevenDaysAgo = subDays(now, 7);

    filteredConversations.forEach((c) => {
      const date = new Date(c.updated_at || c.last_message_at || c.created_at);
      if (isToday(date)) {
        today.push(c);
      } else if (isYesterday(date)) {
        yesterday.push(c);
      } else if (isAfter(date, sevenDaysAgo)) {
        last7Days.push(c);
      } else {
        older.push(c);
      }
    });

    const items: FlatListItem[] = [];

    if (today.length > 0) {
      items.push({ type: "header", label: "Today", id: "header-today" });
      today.forEach((c) => items.push({ type: "conversation", data: c, id: c.id }));
    }

    if (yesterday.length > 0) {
      items.push({ type: "header", label: "Yesterday", id: "header-yesterday" });
      yesterday.forEach((c) => items.push({ type: "conversation", data: c, id: c.id }));
    }

    if (last7Days.length > 0) {
      items.push({ type: "header", label: "Previous 7 Days", id: "header-7days" });
      last7Days.forEach((c) => items.push({ type: "conversation", data: c, id: c.id }));
    }

    if (older.length > 0) {
      items.push({ type: "header", label: "Older Conversations", id: "header-older" });
      older.forEach((c) => items.push({ type: "conversation", data: c, id: c.id }));
    }

    return items;
  }, [filteredConversations]);

  const parentRef = React.useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => parentRef.current,
    estimateSize: (index) => {
      return flatItems[index].type === "header" ? 28 : 42;
    },
    overscan: 5,
  });

  if (filteredConversations.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 px-4 text-center">
        <span className="text-xs text-zinc-500 font-medium">
          {searchQuery ? "No conversations match search" : "No conversations yet"}
        </span>
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      className="flex-1 w-full overflow-y-auto px-2 py-1 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent"
    >
      <div
        className="w-full relative"
        style={{ height: `${virtualizer.getTotalSize()}px` }}
      >
        {virtualizer.getVirtualItems().map((vItem) => {
          const item = flatItems[vItem.index];
          return (
            <div
              key={item.id}
              className="absolute top-0 left-0 w-full"
              style={{
                height: `${vItem.size}px`,
                transform: `translateY(${vItem.start}px)`,
              }}
            >
              {item.type === "header" ? (
                <div className="px-3 pt-3 pb-1 text-[10px] font-bold text-zinc-500 uppercase tracking-wider select-none">
                  {item.label}
                </div>
              ) : (
                <ConversationItem
                  conversation={item.data}
                  isActive={item.id === activeId}
                  onSelect={() => onSelect(item.id)}
                  onRename={onRename}
                  onDelete={onDelete}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
