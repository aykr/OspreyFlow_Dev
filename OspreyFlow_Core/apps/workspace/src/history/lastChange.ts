// The canvas toolbar's "Last change" (ADR-115 E6; the reference): the case's latest history step and
// when, from the history the History drawer lists (spec 03 §3.1).
import { whenLabel } from "../home/homeData";
import type { HistoryStepSummary } from "../workingset/models";

export function lastChangeText(steps: readonly HistoryStepSummary[], now: Date): string | null {
  if (steps.length === 0) return null;
  const latest = steps.reduce((a, b) => (a.created_at >= b.created_at ? a : b));
  return `Last change: ${latest.label}, ${whenLabel(latest.created_at, now)}`;
}
