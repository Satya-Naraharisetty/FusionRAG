import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useMessages } from "../hooks/useMessages";
import { conversationsApi, MessagesListResponse } from "../api/conversations";
import type { Message } from "../types";

// Mock the conversationsApi
vi.mock("../api/conversations", () => ({
  conversationsApi: {
    listMessages: vi.fn(),
  },
}));

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

const mockMessage = (id: string, content: string, createdAt: string): Message => ({
  id,
  conversation_id: "conv-123",
  role: "user",
  content,
  status: "completed",
  citations: null,
  prompt_tokens: 10,
  completion_tokens: 20,
  tool_calls: null,
  metadata: null,
  created_at: createdAt,
});

describe("useMessages Cursor Pagination Hook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not fetch when conversationId is null", () => {
    const { result } = renderHook(() => useMessages(null), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(conversationsApi.listMessages).not.toHaveBeenCalled();
  });

  it("fetches initial page with null cursor and handles next_cursor pagination", async () => {
    const page1: MessagesListResponse = {
      items: [
        mockMessage("msg-1", "Hello 1", "2026-08-31T20:00:00Z"),
        mockMessage("msg-2", "Hello 2", "2026-08-31T19:59:00Z"),
      ],
      messages: [
        mockMessage("msg-1", "Hello 1", "2026-08-31T20:00:00Z"),
        mockMessage("msg-2", "Hello 2", "2026-08-31T19:59:00Z"),
      ],
      limit: 2,
      next_cursor: "cursor_token_page_2",
      prev_cursor: null,
      has_next_page: true,
      has_prev_page: false,
      has_more: true,
    };

    const page2: MessagesListResponse = {
      items: [
        mockMessage("msg-3", "Hello 3", "2026-08-31T19:58:00Z"),
        mockMessage("msg-4", "Hello 4", "2026-08-31T19:57:00Z"),
      ],
      messages: [
        mockMessage("msg-3", "Hello 3", "2026-08-31T19:58:00Z"),
        mockMessage("msg-4", "Hello 4", "2026-08-31T19:57:00Z"),
      ],
      limit: 2,
      next_cursor: null,
      prev_cursor: "cursor_token_page_1_prev",
      has_next_page: false,
      has_prev_page: true,
      has_more: false,
    };

    vi.mocked(conversationsApi.listMessages)
      .mockResolvedValueOnce(page1)
      .mockResolvedValueOnce(page2);

    const { result } = renderHook(() => useMessages("conv-123", 2), {
      wrapper: createWrapper(),
    });

    // 1. Initial Page Fetch
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(conversationsApi.listMessages).toHaveBeenCalledWith("conv-123", 2, null);
    expect(result.current.data?.pages).toHaveLength(1);
    expect(result.current.data?.pages[0].items).toHaveLength(2);
    expect(result.current.hasNextPage).toBe(true);

    // 2. Fetch Next Page
    await result.current.fetchNextPage();
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2));

    expect(conversationsApi.listMessages).toHaveBeenCalledWith("conv-123", 2, "cursor_token_page_2");
    expect(result.current.hasNextPage).toBe(false);

    // 3. Page Flattening & Duplicate Verification
    const allMessages = result.current.data?.pages.flatMap((p) => p.items) || [];
    expect(allMessages).toHaveLength(4);
    const uniqueIds = new Set(allMessages.map((m) => m.id));
    expect(uniqueIds.size).toBe(4);
    expect(allMessages.map((m) => m.id)).toEqual(["msg-1", "msg-2", "msg-3", "msg-4"]);
  });

  it("handles previous page backward cursor pagination", async () => {
    const page2: MessagesListResponse = {
      items: [mockMessage("msg-3", "Hello 3", "2026-08-31T19:58:00Z")],
      messages: [mockMessage("msg-3", "Hello 3", "2026-08-31T19:58:00Z")],
      limit: 1,
      next_cursor: null,
      prev_cursor: "prev_cursor_token_for_page_1",
      has_next_page: false,
      has_prev_page: true,
      has_more: false,
    };

    const page1: MessagesListResponse = {
      items: [mockMessage("msg-1", "Hello 1", "2026-08-31T20:00:00Z")],
      messages: [mockMessage("msg-1", "Hello 1", "2026-08-31T20:00:00Z")],
      limit: 1,
      next_cursor: "cursor_token_page_2",
      prev_cursor: null,
      has_next_page: true,
      has_prev_page: false,
      has_more: true,
    };

    vi.mocked(conversationsApi.listMessages)
      .mockResolvedValueOnce(page2)
      .mockResolvedValueOnce(page1);

    const { result } = renderHook(() => useMessages("conv-123", 1), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasPreviousPage).toBe(true);

    await result.current.fetchPreviousPage();
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2));

    expect(conversationsApi.listMessages).toHaveBeenCalledWith(
      "conv-123",
      1,
      "prev_cursor_token_for_page_1"
    );
  });

  it("terminates pagination when has_next_page is false on empty response", async () => {
    const emptyPage: MessagesListResponse = {
      items: [],
      messages: [],
      limit: 50,
      next_cursor: null,
      prev_cursor: null,
      has_next_page: false,
      has_prev_page: false,
      has_more: false,
    };

    vi.mocked(conversationsApi.listMessages).mockResolvedValueOnce(emptyPage);

    const { result } = renderHook(() => useMessages("conv-123", 50), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasNextPage).toBe(false);
    expect(result.current.hasPreviousPage).toBe(false);
    expect(result.current.data?.pages[0].items).toHaveLength(0);
  });
});
