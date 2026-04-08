import type { ResultPayload, SSEChunk, AuthResponse, User } from './types';

// The base URL for the API. In development with Vite, 
// this is handled by the proxy in vite.config.ts.
const API_BASE = '/api';

export interface SendMessageCallbacks {
  onTextDelta: (delta: string) => void;
  onResult: (result: ResultPayload) => void;
  onDone: () => void;
  onError: (msg: string) => void;
}

/**
 * POST /auth/register
 */
export async function register(username: string, password: string): Promise<User> {
  const resp = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });

  if (!resp.ok) {
    const error = await resp.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Registration failed (HTTP ${resp.status})`);
  }

  return resp.json();
}

/**
 * POST /auth/token
 */
export async function login(username: string, password: string): Promise<AuthResponse> {
  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);

  const resp = await fetch(`${API_BASE}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData.toString(),
  });

  if (!resp.ok) {
    const error = await resp.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(error.detail || `Login failed (HTTP ${resp.status})`);
  }

  return resp.json();
}

/**
 * POST /chat and consume the text/event-stream response.
 */
export async function sendMessage(
  sessionId: string,
  message: string,
  token: string | null,
  callbacks: SendMessageCallbacks,
): Promise<void> {
  const { onTextDelta, onResult, onDone, onError } = callbacks;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ session_id: sessionId, message }),
    });
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err));
    return;
  }

  if (!response.ok || !response.body) {
    if (response.status === 401) {
      onError('Authentication required or session expired.');
    } else {
      onError(`HTTP ${response.status}`);
    }
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      // Keep the last (potentially incomplete) line in the buffer.
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const json = line.slice(6).trim();
        if (!json) continue;

        let chunk: SSEChunk;
        try {
          chunk = JSON.parse(json) as SSEChunk;
        } catch {
          continue;
        }

        if (chunk.type === 'text_delta' && typeof chunk.data === 'string') {
          onTextDelta(chunk.data);
        } else if (chunk.type === 'result' && chunk.data && typeof chunk.data === 'object') {
          onResult(chunk.data as ResultPayload);
        } else if (chunk.type === 'done') {
          onDone();
        } else if (chunk.type === 'error') {
          onError(typeof chunk.data === 'string' ? chunk.data : 'Unknown error');
        }
      }
    }
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err));
  }
}
