import { describe, it, expect, vi, beforeEach } from 'vitest';
import { sendMessage } from '../api';

function makeStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

function sseLines(...payloads: object[]): string {
  return payloads.map((p) => `data: ${JSON.stringify(p)}\n\n`).join('');
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('sendMessage', () => {
  it('dispatches text_delta, result, and done events', async () => {
    const body = sseLines(
      { type: 'text_delta', data: 'Hello ' },
      { type: 'text_delta', data: 'world' },
      { type: 'result', data: { result_type: 'table', columns: ['a'], rows: [{ a: 1 }] } },
      { type: 'done' },
    );

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: makeStream([body]),
    }));

    const deltas: string[] = [];
    const results: object[] = [];
    let done = false;

    await sendMessage('s1', 'hi', {
      onTextDelta: (d) => deltas.push(d),
      onResult: (r) => results.push(r),
      onDone: () => { done = true; },
      onError: (e) => { throw new Error(`Unexpected error: ${e}`); },
    });

    expect(deltas).toEqual(['Hello ', 'world']);
    expect(results).toHaveLength(1);
    expect((results[0] as { result_type: string }).result_type).toBe('table');
    expect(done).toBe(true);
  });

  it('calls onError for error SSE events', async () => {
    const body = sseLines(
      { type: 'error', data: 'Something went wrong' },
      { type: 'done' },
    );

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: makeStream([body]),
    }));

    const errors: string[] = [];
    await sendMessage('s2', 'fail', {
      onTextDelta: () => {},
      onResult: () => {},
      onDone: () => {},
      onError: (e) => errors.push(e),
    });

    expect(errors).toEqual(['Something went wrong']);
  });

  it('calls onError when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')));

    const errors: string[] = [];
    await sendMessage('s3', 'msg', {
      onTextDelta: () => {},
      onResult: () => {},
      onDone: () => {},
      onError: (e) => errors.push(e),
    });

    expect(errors).toEqual(['Network error']);
  });

  it('calls onError on non-ok HTTP response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      body: null,
    }));

    const errors: string[] = [];
    await sendMessage('s4', 'msg', {
      onTextDelta: () => {},
      onResult: () => {},
      onDone: () => {},
      onError: (e) => errors.push(e),
    });

    expect(errors[0]).toContain('500');
  });

  it('handles SSE chunks split across multiple stream reads', async () => {
    const full = sseLines({ type: 'text_delta', data: 'split' }, { type: 'done' });
    // Split the raw bytes in the middle of a line
    const half = Math.floor(full.length / 2);
    const part1 = full.slice(0, half);
    const part2 = full.slice(half);

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: makeStream([part1, part2]),
    }));

    const deltas: string[] = [];
    let done = false;

    await sendMessage('s5', 'msg', {
      onTextDelta: (d) => deltas.push(d),
      onResult: () => {},
      onDone: () => { done = true; },
      onError: (e) => { throw new Error(e); },
    });

    expect(deltas).toContain('split');
    expect(done).toBe(true);
  });
});
