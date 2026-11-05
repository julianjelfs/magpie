export const FACETS = ['period', 'movement', 'region', 'medium', 'technique', 'subject'] as const;
export type Facet = (typeof FACETS)[number];

export const FACET_NAMES: Record<Facet, string> = {
  period: 'Period',
  movement: 'Movement',
  region: 'Region',
  medium: 'Medium',
  technique: 'Technique',
  subject: 'Subject'
};

/** What the museum says about a piece, as the Pi passes it on. */
export interface Meta {
  source: string;
  source_id: number;
  title: string;
  artist: string;
  artist_bio: string;
  culture: string;
  period: string;
  date: string;
  medium: string;
  dimensions: string;
  department: string;
  classification: string;
  credit_line: string;
  museum_url: string;
  image_url: string;
  highlight: boolean;
}

/** A piece waiting for a verdict. */
export interface Candidate extends Meta {
  key: string;
  wall_colour: string;
  width: number;
  height: number;
  image: string;
}

/** A piece in the hoard. */
export interface Kept extends Candidate {
  kept_at: string;
  image_status: 'pending' | 'ready' | 'failed';
  tag_status: 'pending' | 'tagged' | 'failed';
  tag_error: string | null;
  note: string | null;
  tags: Record<Facet, string[]>;
  thumb: string;
  /** Kept on this device, not yet on the Pi. */
  unsent?: boolean;
}

export type Verdict = 'keep' | 'pass';

export interface Decision {
  key: string;
  verdict: Verdict;
  decided_at: string;
  meta: Partial<Meta>;
  wall_colour: string;
  width: number;
  height: number;
}

export interface Room {
  id: number;
  name: string;
  enabled: boolean;
}
