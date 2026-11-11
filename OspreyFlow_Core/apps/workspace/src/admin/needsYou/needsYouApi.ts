// The reader's *Needs you* (ADR-145 decision 11, A2; L2.7): one read, `GET /v1/me/needs-you`, for the
// top bar's *Needs you · n* and the Studio's *1 Model · n proposed*. What it lists is gated in the
// Conduit, as the reader (`services/api/needs_you.py`), so nothing here filters.
import type { NeedsYou } from "../../../../../packages/schemas/generated";

export type { NeedsYou };

export async function readNeedsYou(
  apiBaseUrl: string,
  bearerToken: string,
  fetcher: typeof fetch = fetch,
): Promise<NeedsYou> {
  const response = await fetcher(`${apiBaseUrl}/v1/me/needs-you`, {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!response.ok) throw new Error(`needs-you ${response.status}`);
  const body = (await response.json()) as Partial<NeedsYou> | null;
  // An answer not of this shape is said as a failed read, never shown as nothing waiting.
  if (
    !body ||
    !Array.isArray(body.promotions_overdue) ||
    !Array.isArray(body.proposals) ||
    (body.schedule_notices !== undefined && !Array.isArray(body.schedule_notices)) ||
    (body.schedule_notices_total !== undefined && typeof body.schedule_notices_total !== "number")
  ) {
    throw new Error("needs-you: the answer was not the reader's Needs you");
  }
  // A Conduit from before ADR-110 Amendment 19 serves no notices: none, not a failed read.
  return {
    ...body,
    schedule_notices: body.schedule_notices ?? [],
    schedule_notices_total: body.schedule_notices_total ?? body.schedule_notices?.length ?? 0,
  } as NeedsYou;
}

/** How many things wait for the reader: each overdue promotion, each proposed link type they may
 * decide (a dataset they may not read the proposals of is never listed, ADR-143 Amendment 4's
 * *Open*), and each of their own scheduled loads' notices of the last seven days, all of them, not
 * only those listed (ADR-110 Amendment 19). */
export function needsYouCount(needs: NeedsYou): number {
  return (
    needs.promotions_overdue.length +
    needs.proposals.reduce((n, p) => n + p.to_decide, 0) +
    (needs.schedule_notices_total ?? needs.schedule_notices?.length ?? 0)
  );
}

/** The proposals to decide in one dataset, for its Model tab. */
export function proposedIn(
  needs: NeedsYou | null,
  datasetId: string | null,
): number {
  if (!needs || !datasetId) return 0;
  return (
    needs.proposals.find((p) => p.dataset_id === datasetId)?.to_decide ?? 0
  );
}

const plural = (n: number, one: string, many: string) =>
  `${n} ${n === 1 ? one : many}`;

/** The words of an entry and its tip (what it is, and what follows), in one place for the top bar,
 * the Studio's reminder and their tests. */
export const NEEDS_YOU_WORDS = {
  proposals: (n: number, dataset: string) =>
    `${plural(n, "proposed link type", "proposed link types")} to decide in ${dataset}`,
  proposalsTip:
    "Analysts proposed these link types in cases reading this dataset. On its Model tab, add each to the draft model or decline it, with a reason; until then its links stay in their case and cannot be promoted.",
  promotionTip:
    "A promotion has waited past the days your administrator set. Review it, or ask its dataset's other reviewers. It stays here while it still waits and you may still review it.",
  reminder: (n: number) =>
    `${plural(n, "proposed link type waits", "proposed link types wait")} for you on the Model tab.`,
  reminderTip:
    "Analysts proposed new link types for this dataset. Decide them on 1 Model: added to the draft model, a type is made live with the next model version.",
  noticeTip:
    "A scheduled load of yours did not run as planned. Its pipeline's Runs, in the Ingest Studio, say what happened. This stays here for seven days.",
  moreNotices: (n: number) =>
    `${plural(n, "more notice", "more notices")} of your scheduled loads, not listed here`,
  moreNoticesTip:
    "Each pipeline's Runs, in the Ingest Studio, list every run of its schedule, the ones not shown here included.",
  unread: "Needs you could not be read",
  unreadProposals: "The proposed link types waiting for you could not be counted; the Model tab lists them.",
};
