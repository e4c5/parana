import { useCallback, useState } from 'react';
import { sendMessage as apiSend } from './api';
import type { Message, ResultPayload } from './types';

function uid(): string {
  return Math.random().toString(36).slice(2);
}

interface UseChatReturn {
  messages: Message[];
  isStreaming: boolean;
  sendMessage: (text: string) => Promise<void>;
}

export function useChat(sessionId: string): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const sendMessage = useCallback(
    async (text: string) => {
      if (isStreaming || !text.trim()) return;

      // Append user message
      const userMsg: Message = { id: uid(), role: 'user', text };
      // Placeholder assistant message that grows as chunks arrive
      const assistantId = uid();
      const assistantMsg: Message = { id: assistantId, role: 'assistant', text: '' };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      await apiSend(sessionId, text, {
        onTextDelta: (delta) => {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, text: m.text + delta } : m)),
          );
        },
        onResult: (result: ResultPayload) => {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, result } : m)),
          );
        },
        onDone: () => {
          setIsStreaming(false);
        },
        onError: (msg) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, text: m.text || `Error: ${msg}` } : m,
            ),
          );
          setIsStreaming(false);
        },
      });
    },
    [sessionId, isStreaming],
  );

  return { messages, isStreaming, sendMessage };
}
