// Where a case's events are, said in words (`06_DECISIONS.md` ADR-099 Amendment 9): events stay with
// the case they were loaded into, so a case that only reads a dataset has none of its own. The
// server names only cases the reader can open that hold events the reader may count; every one it
// names is said, never a sample. Pure: no DOM, no fetch.
import type { CaseEvents } from "../../../../packages/schemas/generated";

export function eventsElsewhereSentence(found: CaseEvents | null): string | null {
  const held = found?.held_by ?? [];
  if (!found || found.has_events || held.length === 0) return null;
  const names = held.map((c) => c.name ?? "an untitled case");
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  return (
    "This case holds no events of its own: events stay with the case they were loaded into. " +
    `The events of the datasets it reads are in ${list}.`
  );
}
