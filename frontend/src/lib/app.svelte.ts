import * as api from './api';
import { Unreachable } from './api';
import { withOutbox, type Filter } from './hoard';
import { Outbox } from './outbox';
import type { Candidate, Kept, Verdict } from './types';

const UPCOMING = 'magpie.upcoming';
const HOARD = 'magpie.hoard';
const QUEUE_SIZE = 6;

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage full or blocked. The app still works while open.
  }
}

/**
 * Put a picture in the service worker's 'art' cache so it is there offline. Written from
 * the page rather than left to the worker: on a first visit the worker isn't in control
 * yet, and anything fetched before it is would never be cached.
 */
async function keepOffline(src: string) {
  try {
    const cache = await caches.open('art');
    if (!(await cache.match(src))) await cache.add(src);
  } catch {
    // No Cache API (plain http), or the Pi went away mid-fetch. Try again next time.
  }
}

/** Fetch and decode a picture ahead of time, and keep it for offline. */
function preload(src: string) {
  const img = new Image();
  img.decoding = 'async';
  img.src = src;
  keepOffline(src);
}

type SavedHoard = { pieces: Kept[]; at: string | null };

class Magpie {
  /** Pieces held on this device, waiting for a verdict. The first is on the wall. */
  upcoming = $state<Candidate[]>(load(UPCOMING, []));
  /** The hoard as the Pi last described it. */
  private fromPi = $state<SavedHoard>(load(HOARD, { pieces: [], at: null }));
  reachable = $state(true);
  fetching = $state(false);
  unsent = $state(0);
  /** Bumped on every outbox change, so the derived hoard follows it. */
  private outboxVersion = $state(0);
  filters = $state<Filter[]>([]);

  private outbox = new Outbox(localStorage);
  private refilling: Promise<void> | null = null;
  private flushing: Promise<void> | null = null;

  /** The hoard as it should look on this device, outbox included. */
  hoard = $derived(withOutbox(this.fromPi.pieces, this.outboxSnapshot()));
  hoardAsOf = $derived(this.fromPi.at);
  current = $derived(this.upcoming[0] ?? null);

  constructor() {
    this.unsent = this.outbox.all().length;
    for (const p of this.upcoming) preload(p.image);
  }

  private outboxSnapshot() {
    void this.outboxVersion;
    return this.outbox.all();
  }

  private outboxChanged() {
    this.unsent = this.outbox.all().length;
    this.outboxVersion++;
  }

  start() {
    this.flush();
    this.refill();
    this.refreshHoard();
    window.addEventListener('online', () => this.wake());
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') this.wake();
    });
    // While the Pi is away, look for it every twenty seconds.
    setInterval(() => {
      if (!this.reachable || this.unsent > 0) this.wake();
    }, 20000);
  }

  wake() {
    this.flush();
    this.refill();
    this.refreshHoard();
  }

  private mark(error: unknown) {
    if (error instanceof Unreachable) this.reachable = false;
    else console.error(error);
  }

  refill(): Promise<void> {
    if (this.refilling) return this.refilling;
    const need = QUEUE_SIZE - this.upcoming.length;
    if (need < 2 && this.upcoming.length > 0) return Promise.resolve();
    this.fetching = true;
    this.refilling = (async () => {
      try {
        const exclude = [...this.upcoming.map((p) => p.key), ...this.outbox.all().map((d) => d.key)];
        const pieces = await api.nextPieces(Math.max(need, 1), exclude);
        this.reachable = true;
        const held = new Set(this.upcoming.map((p) => p.key));
        const fresh = pieces.filter((p) => !held.has(p.key));
        for (const p of fresh) preload(p.image);
        this.upcoming = [...this.upcoming, ...fresh];
        save(UPCOMING, this.upcoming);
      } catch (e) {
        this.mark(e);
      } finally {
        this.fetching = false;
        this.refilling = null;
      }
    })();
    return this.refilling;
  }

  flush(): Promise<void> {
    if (this.flushing) return this.flushing;
    this.flushing = (async () => {
      try {
        const sent = await this.outbox.flush(api.sendDecisions);
        this.reachable = true;
        if (sent) await this.refreshHoard();
      } catch (e) {
        this.mark(e);
      } finally {
        this.outboxChanged();
        this.flushing = null;
      }
    })();
    return this.flushing;
  }

  async refreshHoard() {
    try {
      const pieces = await api.fetchHoard();
      this.reachable = true;
      this.fromPi = { pieces, at: new Date().toISOString() };
      save(HOARD, this.fromPi);
      // In the background and one at a time, so a big hoard doesn't swamp the Pi.
      void (async () => {
        for (const p of pieces) if (p.image_status === 'ready') await keepOffline(p.thumb);
      })();
    } catch (e) {
      this.mark(e);
    }
  }

  private record(piece: Candidate, verdict: Verdict) {
    const { key, wall_colour, width, height, image: _image, ...meta } = piece;
    this.outbox.add({ key, verdict, decided_at: new Date().toISOString(), meta, wall_colour, width, height });
    this.outboxChanged();
    this.flush();
  }

  /** Give the piece on the wall its verdict and move on to the next. */
  decide(verdict: Verdict) {
    const piece = this.upcoming[0];
    if (!piece) return;
    this.upcoming = this.upcoming.slice(1);
    save(UPCOMING, this.upcoming);
    this.record(piece, verdict);
    this.refill();
  }

  /** Take a piece out of the hoard. It won't be offered again. */
  letGo(piece: Kept) {
    this.record(piece, 'pass');
  }

  async retry(piece: Kept) {
    try {
      await api.retryPiece(piece.key);
      await this.refreshHoard();
    } catch (e) {
      this.mark(e);
    }
  }

  /** True while some kept piece is still being fetched or tagged on the Pi. */
  get working() {
    return this.hoard.some((p) => !p.unsent && (p.image_status === 'pending' || p.tag_status === 'pending'));
  }
}

export const app = new Magpie();
export type App = Magpie;
