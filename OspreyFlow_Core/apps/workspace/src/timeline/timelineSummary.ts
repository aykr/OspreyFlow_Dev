// What the folded timeline shows (ADR-115 E4): the open timeline's own density histogram, published
// as it is read, so the folded row draws exactly what the timeline holds and asks for nothing more.
import { useSyncExternalStore } from "react";

import type { Histogram } from "../../../../packages/schemas/generated";

const listeners = new Set<() => void>();
let current: Histogram | null = null;

export function publishTimelineSummary(histogram: Histogram | null): void {
  current = histogram;
  listeners.forEach((listener) => listener());
}

export function useTimelineSummary(): Histogram | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}

/** What was last published, for a caller outside React (and the tests). */
export function currentTimelineSummary(): Histogram | null {
  return current;
}

/** For tests: forget what was published. */
export function forgetTimelineSummaryForTest(): void {
  current = null;
  listeners.forEach((listener) => listener());
}
