// Promotion into a dataset, and a removed case's layer merged or deleted (ADR-143 decisions 8 and
// 10; Amendment 2 decision 1; `spec/03_CONDUIT_MIDDLEWARE.md` §3.1c, *Promotion*).
//
// It decides nothing. The sheet's checks are the Conduit's, run again when the promotion is sent;
// each refusal comes back in words and is shown as given. A promotion another reader may not see is
// "not found", exactly as one that never existed (rule 3). The board's own calls are here; the
// Ingest Studio's (its Analyst promotions, a removed case's layer) are in
// `ingest/runs/promotionsApi.ts`, the place whose screens make them.
import type {
  LayerDeleted,
  LayerDryRun,
  LayerMergeSheet,
  Promotion,
  PromotionDetails,
  PromotionSheet,
  Promotions,
  RemovedCaseLayers,
  SheetItem,
} from "../../../../packages/schemas/generated";

export type { LayerDeleted, LayerDryRun, LayerMergeSheet, Promotion, PromotionDetails, PromotionSheet, Promotions, RemovedCaseLayers, SheetItem };

// Above every export, so it is this file's own (the Glass's) and no importer's: the Studio imports
// `send` and `answered` from here (`test_place_routes.py`'s scan reads an export's text to the next).
const board = (api: string, caseId: string, boardId: string, tail: string) =>
  `${api}/v1/investigations/${encodeURIComponent(caseId)}/boards/${encodeURIComponent(boardId)}/${tail}`;

export type Answer<T> = { ok: true; value: T } | { ok: false; message: string; code?: string };

export async function send(url: string, token: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, { ...init, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } });
}

export async function answered<T>(promise: Promise<Response>, fallback: string, empty = false): Promise<Answer<T>> {
  let response: Response;
  try {
    response = await promise;
  } catch (err) {
    return { ok: false, message: `The server could not be reached: ${err instanceof Error ? err.message : String(err)}` };
  }
  if (!response.ok) {
    const body = ((await response.json().catch(() => ({}))) ?? {}) as Record<string, unknown>;
    const code = typeof body.error === "string" ? body.error : undefined;
    if (typeof body.detail === "string") return { ok: false, message: body.detail, code };
    if (response.status === 404) return { ok: false, message: "That is not found.", code: code ?? "not_found" };
    if (response.status === 403) return { ok: false, message: "You do not have the right to do that here.", code: code ?? "forbidden" };
    return { ok: false, message: `${fallback} (${response.status}).`, code };
  }
  return { ok: true, value: (empty ? null : await response.json()) as T };
}


// --- the board ---------------------------------------------------------------------------------

export const promotionSheet = (api: string, token: string, caseId: string, boardId: string) =>
  answered<PromotionSheet>(send(board(api, caseId, boardId, "promotion-sheet"), token), "The promotion sheet could not be read");

export const promote = (api: string, token: string, caseId: string, boardId: string, itemIds: string[]) =>
  answered<Promotion>(
    send(board(api, caseId, boardId, "promotions"), token, { method: "POST", body: JSON.stringify({ item_ids: itemIds }) }),
    "The promotion could not be sent",
  );

export const boardPromotions = (api: string, token: string, caseId: string, boardId: string) =>
  answered<Promotions>(send(board(api, caseId, boardId, "promotions"), token), "This board's promotions could not be read");

// --- words ---------------------------------------------------------------------------------------

export const STATUS_WORDS: Record<Promotion["status"], string> = {
  awaiting_review: "Waiting for review",
  committed: "Committed",
  rejected: "Rejected",
  reverted: "Reverted",
};

/** The items ticked when the sheet opens: every one that may go. A link, picture or match decision
 * follows its items; a link is ticked when both its ends are ticked or already in the dataset. */
export function startingTicks(items: readonly SheetItem[]): Set<string> {
  return new Set(items.filter((i) => (i.problems ?? []).length === 0).map((i) => i.item_id));
}

/** What a promotion adds, in words: "2 items and 1 link". */
export function addsInWords(p: Pick<Promotion, "nodes" | "links">): string {
  const items = `${p.nodes} item${p.nodes === 1 ? "" : "s"}`;
  return p.links ? `${items} and ${p.links} link${p.links === 1 ? "" : "s"}` : items;
}
