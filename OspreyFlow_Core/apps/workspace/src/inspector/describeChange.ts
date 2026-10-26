// How a recorded change reads in the link's history (ADR-080): one line for each thing that moved,
// old value then new. Pure, so the wording can be tested without a screen.
//
// Named for its one export rather than `linkHistory`, which differed from `LinkHistory.tsx` only in
// case: on a case-insensitive disk (macOS, Windows) `./LinkHistory` resolved to this file, so the
// component import came back undefined and `tsc` refused the pair (TS1149). Two modules in one folder
// must never differ only in case.
import type { LinkChangeRecord, LinkSnapshot } from "./linkChangeApi";
import { linkTypeName } from "../canvas/linkLabel";
import { intervalText } from "./intervalText";

function show(value: unknown): string {
  if (value === undefined || value === null || value === "") return "(none)";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function dates(interval: LinkSnapshot["interval"]): string {
  if (!interval) return "none";
  return intervalText(interval, { dateOnly: true });
}

function marking(h: NonNullable<LinkSnapshot["handling"]>): string {
  return [h.classification, h.handling_code, h.action_code, h.sanitisation_code].filter(Boolean).join(", ");
}

export function describeChange(change: LinkChangeRecord): string[] {
  const { before, after } = change;
  const lines: string[] = [];
  if (before.type !== after.type) lines.push(`Type: ${linkTypeName(before.type, [])} → ${linkTypeName(after.type, [])}`);
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
  // ADR-102: only where both sides recorded it (a change made before handling could change has
  // neither, and says nothing about it).
  if (before.handling && after.handling) {
    const was = marking(before.handling);
    const now = marking(after.handling);
    if (was !== now) lines.push(`Handling: ${was} → ${now}`);
  }
  return lines;
}
