// The Runs tab's grid (ADR-140 decision 16; the prototype's "Airflow grid"): one row per deployed
// pipeline, one cell per day, read from the run ledger (ADR-110 decision 6). Pure, so the colour of
// a day is decided in one place and tested without a screen.
import type { ScheduleRunView } from "../../../../../packages/schemas/generated";

/** succeeded: every run that day loaded cleanly. attention: a person is needed (rows held, or a run
 * failed, was refused or was blocked). running: a run has not finished. scheduled: today, a schedule
 * or watch is set and nothing has run yet. other: only skipped or missed slots. none: no run. */
export type DayState = "succeeded" | "attention" | "running" | "scheduled" | "other" | "none";

export interface DayCell {
  /** The day, `YYYY-MM-DD` in UTC, as the ledger's times are kept. */
  day: string;
  state: DayState;
  runs: ScheduleRunView[];
}

const NEEDS_A_PERSON = new Set(["failed", "refused", "blocked"]);

function dayOf(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}

/** The last `count` days ending `today`, oldest first. */
export function lastDays(today: Date, count: number): string[] {
  const days: string[] = [];
  for (let back = count - 1; back >= 0; back -= 1) {
    const day = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - back));
    days.push(day.toISOString().slice(0, 10));
  }
  return days;
}

export function stateOf(runs: readonly ScheduleRunView[], scheduledToday: boolean): DayState {
  if (runs.length === 0) return scheduledToday ? "scheduled" : "none";
  if (runs.some((r) => r.outcome === "running")) return "running";
  if (runs.some((r) => NEEDS_A_PERSON.has(r.outcome) || (r.rows_held ?? 0) > 0)) return "attention";
  if (runs.some((r) => r.outcome === "succeeded")) return "succeeded";
  return "other";
}

/** A pipeline's row of cells over `days`. `scheduled` says a schedule or a folder watch is set and
 * not paused; it marks only the last day (today), and only when nothing ran on it. */
export function rowCells(
  runs: readonly ScheduleRunView[],
  days: readonly string[],
  scheduled: boolean,
): DayCell[] {
  const today = days[days.length - 1];
  return days.map((day) => {
    const onDay = runs.filter((r) => dayOf(r.started_at) === day);
    return { day, state: stateOf(onDay, scheduled && day === today), runs: onDay };
  });
}

/** What a cell says in words, for its accessible name and its legend. */
export const STATE_WORDS: Record<DayState, string> = {
  succeeded: "succeeded",
  attention: "needs a person",
  running: "running",
  scheduled: "scheduled, not yet run",
  other: "skipped or missed",
  none: "no run",
};
