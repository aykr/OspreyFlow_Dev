import type { PreviewCount } from "./nodeGestures";

/**
 * Seen 3 October 2026: a double-click on a busy Enron address added all 1,090 of its neighbours at
 * once, which left an unreadable disc and no layout (it is past the layout's own size limit).
 * An expansion that would add more than this many nodes asks first.
 */
export const EXPANSION_CONFIRM_ABOVE = 500;

export type ExpansionGate =
  { kind: "proceed" } | { kind: "ask"; wouldAdd: PreviewCount };

/**
 * Whether an expansion may go ahead. One whose size could not be counted asks too: not knowing is
 * a reason to ask, and never a reason to assume it is small.
 */
export function gateExpansion(wouldAdd: PreviewCount): ExpansionGate {
  if (wouldAdd === "unavailable") return { kind: "ask", wouldAdd };
  return wouldAdd > EXPANSION_CONFIRM_ABOVE
    ? { kind: "ask", wouldAdd }
    : { kind: "proceed" };
}

export interface NarrowingOption {
  edgeType: string;
  wouldAdd: PreviewCount;
}

/**
 * The relationship types an analyst could expand by instead, largest first. A type that adds
 * nothing is left out; one whose count failed is kept, last, so it can still be tried.
 */
export function narrowingOptions(
  perType: Record<string, PreviewCount>,
): NarrowingOption[] {
  const counted = Object.entries(perType).filter(
    (entry): entry is [string, number] =>
      typeof entry[1] === "number" && entry[1] > 0,
  );
  const failed = Object.entries(perType).filter(
    ([, count]) => count === "unavailable",
  );
  return [
    ...counted
      .sort((a, b) => b[1] - a[1])
      .map(([edgeType, wouldAdd]) => ({ edgeType, wouldAdd })),
    ...failed.map(([edgeType]) => ({
      edgeType,
      wouldAdd: "unavailable" as const,
    })),
  ];
}
