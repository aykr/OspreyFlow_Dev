// Select what is lit, the read half (ADR-128 decision 2, B3): which links have an event in the
// window, asked of the server for the window alone, read against the links the canvas holds.
import type { EventFilter, FirstSeenResult } from "../../../../packages/schemas/generated";
import { firstSeenFrom } from "./emergence";
import { litSet, type LitLink, type LitSet } from "./lit";
import { buildEventFilter, type TimeWindow } from "./store";

export type LitRead =
  | { ok: true; lit: LitSet; window: TimeWindow }
  | { ok: false; message: string };

/**
 * `ask` is the first-seen read. The filter holds the window and nothing else: a selection already
 * on the canvas, or a node restriction the cross-filter holds, must not narrow what is lit. A read
 * that fails is reported and selects nothing; one that finds nothing lit is a result with an empty
 * set, which the caller says in words.
 */
export async function readLit(
  ask: (filter: EventFilter) => Promise<FirstSeenResult>,
  investigationScope: string,
  window: TimeWindow,
  links: readonly LitLink[],
): Promise<LitRead> {
  try {
    const answer = await ask(buildEventFilter(investigationScope, window, null));
    return { ok: true, lit: litSet(firstSeenFrom(answer), window, links), window };
  } catch (err) {
    return {
      ok: false,
      message: `Could not read what is lit: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}
