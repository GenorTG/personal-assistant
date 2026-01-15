// API response types

export interface ModelInfo {
  model_id: string;
  name: string;
  path?: string;
  size?: string;
  format?: string;
  downloaded: boolean;
  repo_id?: string;
  author?: string;
  description?: string;
  huggingface_url?: string;
  downloaded_at?: string;
  has_metadata?: boolean;
  moe?: {
    num_experts?: number;
    num_experts_per_tok?: number;
  } | null;
  supports_tool_calling?: boolean;
}

export interface ModelMetadata {
  model_id: string;
  repo_id?: string;
  repo_name?: string;
  author?: string;
  architecture?: string;
  parameters?: number;
  quantization?: string;
  context_length?: number;
  moe?: {
    num_experts?: number;
    num_experts_per_tok?: number;
  } | null;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  metadata?: Record<string, unknown>;
}

export interface Conversation {
  conversation_id: string;
  name?: string;
  created_at?: string;
  updated_at?: string;
  pinned?: boolean;
}

export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

export interface ToolCallResult {
  id: string;
  name: string;
  success: boolean;
  result: unknown;
  error?: string;
}

export interface ApiError {
  error?: string;
  detail?: string;
  message?: string;
}




