import { useState } from 'react';

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID — use getRandomValues
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant
  const hex = Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const SESSION_KEY = 'parana_session_id';

/**
 * Returns a stable UUID session identifier that persists across page reloads
 * via localStorage.
 */
export function useSession(): string {
  const [sessionId] = useState<string>(() => {
    try {
      const stored = localStorage.getItem(SESSION_KEY);
      if (stored) return stored;
    } catch {
      // localStorage unavailable (e.g. private browsing restrictions)
    }
    const id = generateUUID();
    try {
      localStorage.setItem(SESSION_KEY, id);
    } catch {
      // ignore
    }
    return id;
  });

  return sessionId;
}
