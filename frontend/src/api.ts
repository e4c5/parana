import type { ResultPayload, SSEChunk } from './types';

export interface SendMessageCallbacks {
  onTextDelta: (delta: string) => void;
  onResult: (result: ResultPayload) => void;
  onDone: () => void;
  onError: (msg: string) => void;
}

/**
 * POST /chat and consume the text/event-stream response.
 *
 * Each SSE line is `data: <json>`. We decode via ReadableStream + TextDecoder
 * so the function works in any environment that supports Fetch Streams (no
 * EventSource needed).
 */
export async function sendMessage(
  sessionId: string,
  message: string,
  callbacks: SendMessageCallbacks,
): Promise<void> {
  const { onTextDelta, onResult, onDone, onError } = callbacks;

  let response: Response;
  try {
    response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err));
    return;
  }

  if (!response.ok || !response.body) {
    onError(`HTTP ${response.status}`);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

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
}
