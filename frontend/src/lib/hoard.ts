import { FACETS, type Decision, type Facet, type Kept } from './types';

/**
 * The hoard as this device should show it: what the Pi last said, plus keeps still in
 * the outbox, minus pieces let go of but not yet sent.
 */
export function withOutbox(fromPi: Kept[], outbox: Decision[]): Kept[] {
  const latest = new Map(outbox.map((d) => [d.key, d]));
  const shown = fromPi.filter((p) => latest.get(p.key)?.verdict !== 'pass');
  const known = new Set(shown.map((p) => p.key));
  const unsent: Kept[] = outbox
    .filter((d) => d.verdict === 'keep' && !known.has(d.key))
    .map((d) => ({
      ...(d.meta as Kept),
      key: d.key,
      wall_colour: d.wall_colour,
      width: d.width,
      height: d.height,
      image: `/api/art/${d.key}/image`,
      thumb: `/api/art/${d.key}/image`,
      kept_at: d.decided_at,
      image_status: 'pending',
      tag_status: 'pending',
      tag_error: null,
      note: null,
      tags: Object.fromEntries(FACETS.map((f) => [f, []])) as unknown as Record<Facet, string[]>,
      unsent: true
    }));
  return [...unsent.reverse(), ...shown];
}

export type Filter = { facet: Facet; value: string };

export function matches(piece: Kept, filters: Filter[]): boolean {
  return filters.every((f) => piece.tags[f.facet]?.includes(f.value));
}

/** Tag values for one facet with how many of the given pieces carry each, commonest first. */
export function counts(pieces: Kept[], facet: Facet): { value: string; count: number }[] {
  const tally = new Map<string, number>();
  for (const p of pieces) for (const v of p.tags[facet] ?? []) tally.set(v, (tally.get(v) ?? 0) + 1);
  return [...tally.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
}

function list(values: string[]): string {
  return values.length > 1 ? `${values.slice(0, -1).join(', ')} and ${values.at(-1)}` : values[0];
}

/** One plain sentence about where the hoard leans, once there is enough to say it. */
export function leaning(pieces: Kept[]): string | null {
  const tagged = pieces.filter((p) => p.tag_status === 'tagged');
  if (tagged.length < 5) return null;
  const top = (facet: Facet) =>
    counts(tagged, facet)
      .filter((c) => c.count >= 2)
      .slice(0, 2)
      .map((c) => c.value);
  const movements = top('movement');
  const subjects = top('subject').map((s) => s.toLowerCase());
  if (!movements.length && !subjects.length) return null;
  const parts = [];
  if (movements.length) parts.push(`Leaning towards ${list(movements)}`);
  if (subjects.length) parts.push(`${movements.length ? 'mostly' : 'Mostly'} ${list(subjects)}`);
  return parts.join(', ') + '.';
}
