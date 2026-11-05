import { describe, expect, it } from 'vitest';
import { Outbox, type KeyValue } from './outbox';
import type { Decision } from './types';

class MemoryStorage implements KeyValue {
  map = new Map<string, string>();
  getItem(k: string) {
    return this.map.get(k) ?? null;
  }
  setItem(k: string, v: string) {
    this.map.set(k, v);
  }
}

const decision = (key: string, verdict: 'keep' | 'pass', at: string): Decision => ({
  key,
  verdict,
  decided_at: at,
  meta: { title: key },
  wall_colour: '#333333',
  width: 10,
  height: 10
});

describe('invariant 6: a verdict given with the Pi out of reach is not lost', () => {
  it('survives a reload and reaches the Pi when it is back', async () => {
    const storage = new MemoryStorage();
    new Outbox(storage).add(decision('met-1', 'keep', '2026-11-05T10:00:00Z'));

    // Pi unreachable: the send fails and nothing leaves the outbox.
    await expect(
      new Outbox(storage).flush(() => Promise.reject(new Error('unreachable')))
    ).rejects.toThrow();

    // A reload builds a fresh Outbox from the same storage; the Pi is back.
    const received: Decision[][] = [];
    await new Outbox(storage).flush(async (d) => received.push(d));

    expect(received).toEqual([[decision('met-1', 'keep', '2026-11-05T10:00:00Z')]]);
    expect(new Outbox(storage).all()).toEqual([]);
  });

  it('keeps a verdict given while an earlier send was in flight', async () => {
    const outbox = new Outbox(new MemoryStorage());
    outbox.add(decision('met-1', 'keep', '2026-11-05T10:00:00Z'));

    await outbox.flush(async () => {
      outbox.add(decision('met-2', 'pass', '2026-11-05T10:00:02Z'));
    });

    expect(outbox.all().map((d) => d.key)).toEqual(['met-2']);
  });
});
