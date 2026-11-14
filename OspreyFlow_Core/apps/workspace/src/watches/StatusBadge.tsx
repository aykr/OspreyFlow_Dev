// `Hotlist.status`/`Monitor.status` rendering — `06_DECISIONS.md` ADR-036's own binding
// requirement, quoted directly: "A stopped monitor is surfaced as stopped somewhere the analyst or
// another owner can see it (the monitor list, or the alert inbox) rather than silently producing
// nothing forever with no visible state change." Stage 6c's backend already writes `status` on
// every evaluation attempt; this component is what makes it visible, not just present in the
// wire payload — a distinct label and colour per state, not a value that only differs in a `title`
// attribute or a class name a screen reader has no text for.
// `Hotlist.ts`/`Monitor.ts` each generate their own identical `Status = "active" | "stopped"`
// alias (no shared `WatchStatus` export exists in `packages/schemas/generated/`) — aliased here
// from `Hotlist`'s copy rather than duplicated, since both call sites need the same union.
import type { Status as WatchStatus } from "../../../../packages/schemas/generated/Hotlist";

export interface StatusBadgeProps {
  status: WatchStatus;
  /** ADR-044 Amendment 1: why it is stopped, in the Conduit's words for its owner; shown beside the
   * label while stopped, never while active. */
  why?: string | null;
  /** ADR-044 Amendment 2: while active, the Conduit's words for loads in a row that could not check its owner's
   * sign-in (`status_note`); shown beside the label while active, never while stopped. */
  note?: string | null;
}

export function StatusBadge({ status, why, note }: StatusBadgeProps) {
  const stopped = status === "stopped";
  const badge = (
    <span
      className="value"
      style={{
        color: stopped ? "var(--warning)" : "var(--success)",
        fontWeight: 600,
        textTransform: "uppercase",
        fontSize: "var(--fs-11)",
      }}
    >
      {stopped ? "Stopped" : "Active"}
    </span>
  );
  const beside = stopped ? why : note;
  if (!beside) return badge;
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: "var(--sp-2)" }}>
      {badge}
      <span className="label">{beside}</span>
    </span>
  );
}
