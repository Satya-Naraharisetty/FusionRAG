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
      role: "user",
      is_active: true,
      is_verified: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  }),

  http.post("*/api/v1/auth/verify-email", () => {
    return HttpResponse.json({
      access_token: "mock-verified-token",
      expires_in: 3600,
    });
  }),

  http.post("*/api/v1/auth/resend-verification", () => {
    return HttpResponse.json({
      message: "Verification email dispatched",
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

  http.delete("*/api/v1/auth/account", () => {
    return new HttpResponse(null, { status: 204 });
  }),

  http.get("*/api/v1/auth/me", () => {
    return HttpResponse.json({
      id: "user-123",
      email: "test@example.com",
      role: "user",
      is_active: true,
      is_verified: true,
      oauth_provider: null,
      has_password: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  }),

  http.post("*/api/v1/auth/password", () => {
    return HttpResponse.json({ message: "Password updated successfully" });
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
            model: "gemini-3.5-flash-lite",
            retrieval_mode: "hybrid",
            stream: false,
            hybrid_enabled: true,
            system_prompt_version: "v1",
          },
          version: 1,
          metadata: {
            message_count: 2,
            last_model: "gemini-3.5-flash-lite",
            last_provider: "gemini",
            last_tokens: 150,
          },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          last_message_at: new Date().toISOString(),
        },
      ],
      limit: 20,
      next_cursor: null,
      prev_cursor: null,
      has_next_page: false,
      has_prev_page: false,
      has_more: false,
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
      next_cursor: null,
      prev_cursor: null,
      has_next_page: false,
      has_prev_page: false,
      has_more: false,
    });
  }),

  http.delete("*/api/v1/conversations/:id/messages/:messageId", () => {
    return HttpResponse.json({
      deleted_count: 2,
    });
  }),

  http.get("*/api/v1/documents", () => {
    return HttpResponse.json([
      {
        id: "doc-1",
        user_id: "user-123",
        conversation_id: null,
        filename: "test.pdf",
        original_filename: "test.pdf",
        content_type: "application/pdf",
        file_size: 1024,
        checksum: "abcdef",
        status: "completed",
        extractor_version: "1.0",
        failure_reason: null,
        page_count: null,
        word_count: null,
        language: null,
        processing_started_at: new Date().toISOString(),
        processing_completed_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]);
  }),

  http.post("*/api/v1/documents/upload", () => {
    return HttpResponse.json({
      id: "doc-1",
      user_id: "user-123",
      conversation_id: null,
      filename: "test.pdf",
      original_filename: "test.pdf",
      content_type: "application/pdf",
      file_size: 1024,
      checksum: "abcdef",
      status: "completed",
      extractor_version: "1.0",
      failure_reason: null,
      page_count: null,
      word_count: null,
      language: null,
      processing_started_at: new Date().toISOString(),
      processing_completed_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  }),

  // Default: the mocked document is fully indexed, so pipeline surfaces
  // render idle. Tests that exercise the live steps override this per-test.
  http.get("*/api/v1/documents/:id/embeddings/status", () => {
    return HttpResponse.json({
      status: "completed",
      chunks_total: 5,
      embedded_chunks: 5,
      failed_chunks: 0,
      provider: "mock",
      model: "mock",
    });
  }),
];

export const server = setupServer(...handlers);
