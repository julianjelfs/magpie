import type { Candidate, Decision, Kept, Room } from './types';

/**
 * The Pi can't be reached: off the wifi and off the tailnet, a refused connection, a
 * four-second silence, or Caddy answering for a stopped app.
 */
export class Unreachable extends Error {
  constructor() {
    super('The Pi is out of reach');
  }
}

const TIMEOUT_MS = 4000;

export async function call<T>(path: string, init: RequestInit = {}, timeout = TIMEOUT_MS): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      signal: AbortSignal.timeout(timeout),
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) }
    });
  } catch {
    throw new Unreachable();
  }
  if (response.status >= 502 && response.status <= 504) throw new Unreachable();
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `The Pi answered ${response.status}`);
  }
  return response.json() as Promise<T>;
}

/** The Pi waits up to ten seconds for a piece when none are ready, so this one gets longer. */
export const nextPieces = (count: number, exclude: string[]) =>
  call<{ pieces: Candidate[] }>(
    `/api/next?count=${count}&exclude=${encodeURIComponent(exclude.join(','))}`,
    {},
    14000
  ).then((r) => r.pieces);

export const sendDecisions = (decisions: Decision[]) =>
  call<{ applied: string[] }>('/api/decisions', { method: 'POST', body: JSON.stringify({ decisions }) });

export const fetchHoard = () => call<{ pieces: Kept[] }>('/api/hoard').then((r) => r.pieces);

export const retryPiece = (key: string) => call(`/api/hoard/${key}/retry`, { method: 'POST' });

export type Group = { name: string; kept: number; seen: number };

export type Taste = {
  seen: number;
  kept: number;
  rooms: Group[];
  centuries: Group[];
  kinds: Group[];
  highlights: Group[];
  artists: { name: string; kept: number }[];
  steering: { rooms: { name: string; share: number }[]; highlights: number };
};

export const fetchTaste = () => call<Taste>('/api/taste');

export type RoomSettings = { rooms: Room[]; sculpture: boolean };

export const fetchRooms = () => call<RoomSettings>('/api/rooms');

export const saveRooms = (enabled: number[], sculpture: boolean) =>
  call<RoomSettings>('/api/rooms', { method: 'PUT', body: JSON.stringify({ enabled, sculpture }) });
