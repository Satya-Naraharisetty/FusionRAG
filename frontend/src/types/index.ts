export type RetrievalMode = "semantic" | "sparse" | "hybrid" | "auto";

// Conversation
export interface Conversation {
  id: string;
  user_id: string;
  title: string;
  state: "active" | "archived" | "deleted";
  settings: ConversationSettings;
  version: number;
  metadata: ConversationMetadata;
  created_at: string;
  updated_at: string;
  last_message_at: string;
}

export interface ConversationSettings {
  temperature: number;
  provider: "gemini" | "openai" | string;
  model: string;
  retrieval_mode: RetrievalMode;
  stream: boolean;
  hybrid_enabled: boolean;
  system_prompt_version: string;
}

export interface ConversationMetadata {
  message_count: number;
  last_model: string | null;
  last_provider: string | null;
  last_tokens: number;
  last_cost: number;
  last_latency_ms: number;
}

// Messages
export type MessageRole = "user" | "assistant" | "system" | "tool" | "developer" | "function";
export type MessageStatus = "pending" | "streaming" | "completed" | "failed" | "interrupted";

export interface Message {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  citations: Citation[] | null;
  prompt_tokens: number;
  completion_tokens: number;
  tool_calls: Record<string, unknown>[] | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

// Citations
export interface Citation {
  document_id: string;
  document_name: string;
  chunk_id: string;
  chunk_index: number;
}

// Documents
export type DocumentStatus = "pending" | "processing" | "completed" | "failed";

export interface Document {
  id: string;
  user_id: string;
  conversation_id: string | null;
  filename: string;
  original_filename: string;
  content_type: string;
  file_size: number;
  checksum: string;
  status: DocumentStatus;
  extractor_version: string;
  failure_reason: string | null;
  page_count: number | null;
  word_count: number | null;
  language: string | null;
  created_at: string;
  updated_at: string;
  processing_started_at: string | null;
  processing_completed_at: string | null;
}

export interface EmbeddingStatus {
  status: "pending" | "generating" | "completed" | "failed";
  chunks_total: number;
  embedded_chunks: number;
  failed_chunks: number;
  provider: string;
  model: string;
}

// SSE
export type SSEEventType = "metadata" | "text" | "tool_call_started" | "tool_call_completed" | "done" | "error";

export interface SSEEvent {
  event: SSEEventType;
  data: Record<string, unknown>;
}

// Chat UI Structures
export interface ChatMessage {
  id?: string;
  role: MessageRole;
  content: string;
  citations?: Citation[];
  status?: MessageStatus;
  toolCalls?: ToolCallEvent[];
  error?: string;
  // True when the backend skipped retrieval because the user has no uploaded
  // documents — the answer comes from general knowledge. Rendered as a hint.
  retrievalSkipped?: boolean;
  created_at?: string;
}

export interface ToolCallEvent {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  error?: string;
  status: "running" | "done" | "failed";
}

