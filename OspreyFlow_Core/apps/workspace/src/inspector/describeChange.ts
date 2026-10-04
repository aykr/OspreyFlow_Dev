// How a recorded change reads in the link's history (ADR-080): one line for each thing that moved,
// old value then new. Pure, so the wording can be tested without a screen.
//
// Named for its one export rather than `linkHistory`, which differed from `LinkHistory.tsx` only in
// case: on a case-insensitive disk (macOS, Windows) `./LinkHistory` resolved to this file, so the
// component import came back undefined and `tsc` refused the pair (TS1149). Two modules in one folder
// must never differ only in case.
import type { LinkChangeRecord, LinkSnapshot } from "./linkChangeApi";

function show(value: unknown): string {
  if (value === undefined || value === null || value === "") return "(none)";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function dates(interval: LinkSnapshot["interval"]): string {
  if (!interval) return "none";
  return `${interval.valid_from.slice(0, 10)} – ${interval.valid_to ? interval.valid_to.slice(0, 10) : "present"}`;
}

export function describeChange(change: LinkChangeRecord): string[] {
  const { before, after } = change;
  const lines: string[] = [];
  if (before.type !== after.type) lines.push(`Type: ${before.type} → ${after.type}`);
  const names = new Set([...Object.keys(before.properties), ...Object.keys(after.properties)]);
  for (const name of [...names].sort()) {
    const was = show(before.properties[name]);
    const now = show(after.properties[name]);
    if (was !== now) lines.push(`${name}: ${was} → ${now}`);
  }
  if (before.occurrences !== after.occurrences) {
    lines.push(`Records behind it: ${before.occurrences} → ${after.occurrences}`);
  }
  if (dates(before.interval) !== dates(after.interval)) {
    lines.push(`Dates: ${dates(before.interval)} → ${dates(after.interval)}`);
  }
  return lines;
}
