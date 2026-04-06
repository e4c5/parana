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
