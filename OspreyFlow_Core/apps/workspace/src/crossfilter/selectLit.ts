// Select what is lit, the read half (ADR-128 decision 2, B3): which links have an event in the
// window, asked of the server for the window alone, read against the links the canvas holds.
import type { EventFilter, FirstSeenResult } from "../../../../packages/schemas/generated";
import { firstSeenFrom } from "./emergence";
import { litSet, type LitLink, type LitSet } from "./lit";
import { buildEventFilter, type TimeWindow, type WeekdayHourCell } from "./store";

export type LitRead =
  | { ok: true; lit: LitSet; window: TimeWindow }
  | { ok: false; message: string };

/**
 * `ask` is the first-seen read. The filter holds the window and the chosen weekly cells, as the
 * dimming's own read does (ADR-130 Amendment 1), and nothing else: a selection already on the
 * canvas, or a node restriction the cross-filter holds, must not narrow what is lit. A read
 * that fails is reported and selects nothing; one that finds nothing lit is a result with an empty
 * set, which the caller says in words.
 */
export async function readLit(
  ask: (filter: EventFilter) => Promise<FirstSeenResult>,
  investigationScope: string,
  window: TimeWindow,
  links: readonly LitLink[],
  cells: readonly WeekdayHourCell[] | null = null,
): Promise<LitRead> {
  try {
    const answer = await ask(buildEventFilter(investigationScope, window, null, cells));
    return { ok: true, lit: litSet(firstSeenFrom(answer), window, links), window };
  } catch (err) {
    return {
      ok: false,
      message: `Could not read what is lit: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}

/** Said when a lit answer is dropped because the selection moved while it was being read. */
export const LIT_ANSWER_LATE =
  "The selection changed while what is lit was being read, so the answer was not applied. The selection is unchanged. Press Select what is lit again.";

/** Whether the live selection is no longer what it was when the press was made. */
export function selectionChangedSince(atPress: readonly string[], now: ReadonlySet<string>): boolean {
  if (atPress.length !== now.size) return true;
  return atPress.some((id) => !now.has(id));
}
