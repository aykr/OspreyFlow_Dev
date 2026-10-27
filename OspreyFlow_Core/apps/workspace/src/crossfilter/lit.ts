// What is lit (ADR-128 decision 2, B3): the part of the canvas the timeline's window lights.
//
// A link is lit when at least one of its events falls inside the window, the window's own ends
// included. An undated link (one with no event at all) is never lit, which is why the action says
// "undated links are not included". A node is lit when a lit link touches it. The server answers
// which links have an event in the window (`first_seen`, in its own access-filtered query); this
// module reads that answer against the links the canvas holds, so what it names is always from the
// view the canvas already has and never from an id the server volunteered.
import type { FirstSeen } from "./emergence";
import type { TimeWindow } from "./store";

/** A link in the canvas's own view. */
export interface LitLink {
  id: string;
  source: string;
  target: string;
}

export interface LitSet {
  /** Lit nodes, each once, in the order the links give them. */
  nodeIds: string[];
  edgeIds: string[];
}

/** Said beside the result, so the analyst is never left to guess which way undated links went. */
export const UNDATED_NOT_INCLUDED = "undated links are not included";

/**
 * The lit links and nodes among `links`. A link is lit when `firstSeen` gives it an instant and
 * that instant lies in `window`, ends included; the check is repeated here, not left to the server
 * alone, so a window edge is decided in one place a test can name.
 */
export function litSet(firstSeen: FirstSeen, window: TimeWindow, links: readonly LitLink[]): LitSet {
  const from = Date.parse(window.validFrom);
  const to = window.validTo === null ? Number.POSITIVE_INFINITY : Date.parse(window.validTo);
  const edgeIds: string[] = [];
  const nodeIds: string[] = [];
  const seen = new Set<string>();
  for (const link of links) {
    const first = firstSeen.edges[link.id];
    if (first === undefined) continue;
    const at = Date.parse(first);
    if (!(at >= from && at <= to)) continue;
    edgeIds.push(link.id);
    for (const end of [link.source, link.target]) {
      if (seen.has(end)) continue;
      seen.add(end);
      nodeIds.push(end);
    }
  }
  return { nodeIds, edgeIds };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

interface Day {
  day: number;
  month: number;
  year: number;
}

function dayOf(at: Date): Day {
  return { day: at.getUTCDate(), month: at.getUTCMonth(), year: at.getUTCFullYear() };
}

const sameDay = (a: Day, b: Day) => a.day === b.day && a.month === b.month && a.year === b.year;

const withoutYear = (d: Day) => `${d.day} ${MONTHS[d.month]}`;
const withYear = (d: Day) => `${withoutYear(d)} ${d.year}`;

/** How a window reads: its range, a single day, or "from" a date when it has no end. */
function windowWords(window: TimeWindow): { range: string; open: boolean; oneDay: boolean } {
  const start = dayOf(new Date(window.validFrom));
  if (window.validTo === null) return { range: withYear(start), open: true, oneDay: false };
  // The end is lit (`litSet` includes an event at exactly `validTo`), so the label names the day the
  // end instant falls on, midnight included: a window to 1 May 00:00 reaches 1 May.
  const last = dayOf(new Date(window.validTo));
  if (sameDay(start, last)) return { range: withYear(start), open: false, oneDay: true };
  const range =
    start.year === last.year
      ? `${withoutYear(start)} – ${withYear(last)}`
      : `${withYear(start)} – ${withYear(last)}`;
  return { range, open: false, oneDay: false };
}

/**
 * The tab a branch of what is lit opens in, named from the window: "5 Jan – 30 Apr 2026, selected".
 * The end is included in what is lit, so it is named by the day it falls on, an end at midnight
 * included. Dates are UTC, as the timeline's are.
 */
export function litTabName(window: TimeWindow): string {
  const { range, open } = windowWords(window);
  return open ? `From ${range}, selected` : `${range}, selected`;
}

/** The sentence beside a lit selection: "Lit in 5 Jan – 30 Apr 2026: undated links are not
 * included", "Lit on 2 Mar 2026: …" for one day, "Lit from 5 Jan 2026: …" for a window with no end. */
export function litNote(window: TimeWindow): string {
  const { range, open, oneDay } = windowWords(window);
  const lead = open ? "Lit from" : oneDay ? "Lit on" : "Lit in";
  return `${lead} ${range}: ${UNDATED_NOT_INCLUDED}`;
}
