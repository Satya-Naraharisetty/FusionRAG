import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

const handlers = [
  http.post("*/api/v1/auth/login", () => {
    return HttpResponse.json({
      access_token: "mock-token",
      expires_in: 3600,
    });
  }),
  
  http.post("*/api/v1/auth/register", () => {
    return HttpResponse.json({
      id: "user-123",
      email: "test@example.com",
      role: "admin",
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  }),

  http.post("*/api/v1/auth/refresh", () => {
    return HttpResponse.json({
      access_token: "mock-rotated-token",
      expires_in: 3600,
    });
  }),

  http.post("*/api/v1/auth/logout", () => {
    return HttpResponse.json({ message: "Successfully logged out" });
  }),

  http.get("*/api/v1/auth/me", () => {
    return HttpResponse.json({
      id: "user-123",
      email: "test@example.com",
      role: "admin",
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  }),

  http.get("*/api/v1/conversations", () => {
    return HttpResponse.json({
      conversations: [
        {
          id: "conv-1",
          user_id: "user-123",
          title: "Mock Conversation",
          state: "active",
          settings: {
            temperature: 0.0,
            provider: "gemini",
            model: "gemini-1.5-flash",
            retrieval_mode: "hybrid",
            stream: false,
            hybrid_enabled: true,
            system_prompt_version: "v1",
          },
          version: 1,
          metadata: {
            message_count: 2,
            last_model: "gemini-1.5-flash",
            last_provider: "gemini",
            last_tokens: 150,
          },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          last_message_at: new Date().toISOString(),
        },
      ],
      limit: 20,
      offset: 0,
    });
  }),

  http.get("*/api/v1/conversations/:id/messages", () => {
    return HttpResponse.json({
      messages: [
        {
          id: "msg-1",
          conversation_id: "conv-1",
          role: "user",
          content: "Hello",
          status: "completed",
          created_at: new Date().toISOString(),
        },
        {
          id: "msg-2",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Hi there!",
          status: "completed",
          created_at: new Date().toISOString(),
        },
      ],
      limit: 50,
      offset: 0,
    });
  }),

  http.get("*/api/v1/documents", () => {
    return HttpResponse.json([
      {
        id: "doc-1",
        user_id: "user-123",
        filename: "test.pdf",
        original_filename: "test.pdf",
        content_type: "application/pdf",
        file_size: 1024,
        checksum: "abcdef",
        status: "completed",
        extractor_version: "1.0",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]);
  }),
];

export const server = setupServer(...handlers);
