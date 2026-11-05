import type { Decision } from './types';

/** The parts of localStorage the outbox needs, so tests can hand it a Map. */
export interface KeyValue {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

const KEY = 'magpie.outbox';

/**
 * Verdicts given on this device that the Pi hasn't confirmed yet.
 *
 * Every verdict goes in here first and leaves only once the Pi has answered, so one
 * made with the Pi out of reach survives a reload and goes when it is back. A second
 * verdict on the same piece replaces the first: the Pi only needs the latest.
 */
export class Outbox {
  constructor(private store: KeyValue) {}

  all(): Decision[] {
    try {
      return JSON.parse(this.store.getItem(KEY) ?? '[]');
    } catch {
      return [];
    }
  }

  private save(decisions: Decision[]) {
    try {
      this.store.setItem(KEY, JSON.stringify(decisions));
    } catch {
      // Storage full or blocked: the verdict still goes now if the Pi is there.
    }
  }

  add(decision: Decision) {
    this.save([...this.all().filter((d) => d.key !== decision.key), decision]);
  }

  /**
   * Send everything waiting. Anything given while the request was in flight stays for
   * next time. Throws (and keeps everything) if the Pi can't be reached.
   */
  async flush(send: (decisions: Decision[]) => Promise<unknown>): Promise<number> {
    const sending = this.all();
    if (sending.length === 0) return 0;
    await send(sending);
    const sent = new Set(sending.map((d) => `${d.key}@${d.decided_at}`));
    this.save(this.all().filter((d) => !sent.has(`${d.key}@${d.decided_at}`)));
    return sending.length;
  }
}
