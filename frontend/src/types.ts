export interface ResultPayload {
  result_type: 'table' | 'text';
  columns?: string[];
  rows?: Record<string, unknown>[];
}

export interface SSEChunk {
  type: 'text_delta' | 'result' | 'done' | 'error';
  data?: string | ResultPayload;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  result?: ResultPayload;
}

export interface User {
  id: number;
  username: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}
