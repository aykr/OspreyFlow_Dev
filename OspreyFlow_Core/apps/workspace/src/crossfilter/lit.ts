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

/**
 * The tab a branch of what is lit opens in, named from the window: "5 Jan – 30 Apr 2026, selected".
 * A brush across whole days ends at the start of the next day, so an end at midnight is read as the
 * end of the day before; any other end is its own day. Dates are UTC, as the timeline's are.
 */
export function litTabName(window: TimeWindow): string {
  const start = dayOf(new Date(window.validFrom));
  if (window.validTo === null) return `From ${withYear(start)}, selected`;
  const end = new Date(window.validTo);
  const atMidnight =
    end.getUTCHours() === 0 &&
    end.getUTCMinutes() === 0 &&
    end.getUTCSeconds() === 0 &&
    end.getUTCMilliseconds() === 0;
  const last = dayOf(atMidnight ? new Date(end.getTime() - 1) : end);
  if (sameDay(start, last)) return `${withYear(start)}, selected`;
  const range =
    start.year === last.year
      ? `${withoutYear(start)} – ${withYear(last)}`
      : `${withYear(start)} – ${withYear(last)}`;
  return `${range}, selected`;
}
