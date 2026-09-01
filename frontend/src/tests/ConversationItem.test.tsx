import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConversationItem } from "../components/sidebar/ConversationItem";

describe("ConversationItem", () => {
  const mockConv = {
    id: "conv-1",
    user_id: "user-123",
    title: "Mock Conversation",
    state: "active" as const,
    settings: {
      temperature: 0.0,
      provider: "gemini",
      model: "gemini",
      retrieval_mode: "hybrid" as const,
      stream: false,
      hybrid_enabled: true,
      system_prompt_version: "v1",
    },
    version: 1,
    metadata: {
      message_count: 0,
      last_model: null,
      last_provider: null,
      last_tokens: 0,
      last_cost: 0,
      last_latency_ms: 0,
    },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    last_message_at: new Date().toISOString(),
  };

  it("renders conversation title correctly", () => {
    render(
      <ConversationItem
        conversation={mockConv}
        isActive={false}
        onSelect={() => {}}
        onRename={async () => {}}
        onDelete={async () => {}}
        isPinned={false}
        onTogglePin={() => {}}
        folders={[]}
        onMoveToFolder={() => {}}
        tags={[]}
        onAddTag={() => {}}
        onRemoveTag={() => {}}
      />,
    );
    expect(screen.getByText("Mock Conversation")).toBeInTheDocument();
  });

  it("triggers onSelect callback on click", () => {
    const handleSelect = vi.fn();
    render(
      <ConversationItem
        conversation={mockConv}
        isActive={false}
        onSelect={handleSelect}
        onRename={async () => {}}
        onDelete={async () => {}}
        isPinned={false}
        onTogglePin={() => {}}
        folders={[]}
        onMoveToFolder={() => {}}
        tags={[]}
        onAddTag={() => {}}
        onRemoveTag={() => {}}
      />,
    );

    fireEvent.click(screen.getByText("Mock Conversation"));
    expect(handleSelect).toHaveBeenCalled();
  });
});
