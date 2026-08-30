import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatMessage as ChatMessageComponent } from "../components/chat/ChatMessage";
import { ChatMessage } from "../types";
import { conversationsApi } from "../api/conversations";
import api from "../api/client";

describe("ChatMessage Editing and Truncation", () => {
  const userMessage: ChatMessage = {
    id: "msg-1",
    role: "user",
    content: "First query",
    status: "completed",
  };

  it("renders edit button and triggers onEditPrompt on save", async () => {
    const handleEditPrompt = vi.fn();

    render(
      <ChatMessageComponent
        message={userMessage}
        onEditPrompt={handleEditPrompt}
      />
    );

    // Find the edit button
    const editBtn = screen.getByLabelText("Edit message");
    expect(editBtn).toBeInTheDocument();

    // Click edit
    fireEvent.click(editBtn);

    // Edit textarea should appear with current content
    const textarea = screen.getByDisplayValue("First query");
    expect(textarea).toBeInTheDocument();

    // Modify text
    fireEvent.change(textarea, { target: { value: "Edited query text" } });

    // Click Save & Submit
    const saveBtn = screen.getByRole("button", { name: /Save & Submit/i });
    fireEvent.click(saveBtn);

    // Verify onEditPrompt callback is called with message ID and trimmed text
    expect(handleEditPrompt).toHaveBeenCalledWith(
      "msg-1",
      "Edited query text"
    );
  });

  it("calls conversationsApi.deleteMessagesFrom to truncate messages on backend", async () => {
    const deleteSpy = vi.spyOn(api, "delete").mockResolvedValueOnce({
      deleted_count: 3,
    });

    const res = await conversationsApi.deleteMessagesFrom("conv-1", "msg-1");
    expect(deleteSpy).toHaveBeenCalledWith(
      "/conversations/conv-1/messages/msg-1"
    );
    expect(res).toEqual({ deleted_count: 3 });
  });
});
