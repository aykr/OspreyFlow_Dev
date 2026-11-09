// Promotion into a dataset, and a removed case's layer merged or deleted (ADR-143 decisions 8 and
// 10; Amendment 2 decision 1; `spec/03_CONDUIT_MIDDLEWARE.md` §3.1c, *Promotion*).
//
// It decides nothing. The sheet's checks are the Conduit's, run again when the promotion is sent;
// each refusal comes back in words and is shown as given. A promotion another reader may not see is
// "not found", exactly as one that never existed (rule 3).
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

export type Answer<T> = { ok: true; value: T } | { ok: false; message: string; code?: string };

async function send(url: string, token: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, { ...init, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } });
}

async function answered<T>(promise: Promise<Response>, fallback: string, empty = false): Promise<Answer<T>> {
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

const board = (api: string, caseId: string, boardId: string, tail: string) =>
  `${api}/v1/investigations/${encodeURIComponent(caseId)}/boards/${encodeURIComponent(boardId)}/${tail}`;
const dataset = (api: string, datasetId: string, tail: string) => `${api}/v1/datasets/${encodeURIComponent(datasetId)}/${tail}`;

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

// --- the Studio's Analyst promotions -------------------------------------------------------------

export const datasetPromotions = (api: string, token: string, datasetId: string) =>
  answered<Promotions>(send(dataset(api, datasetId, "promotions"), token), "The analyst promotions could not be read");

export const promotionDetails = (api: string, token: string, datasetId: string, promotionId: string) =>
  answered<PromotionDetails>(send(dataset(api, datasetId, `promotions/${encodeURIComponent(promotionId)}`), token), "Its details could not be read");

export const decidePromotion = (api: string, token: string, datasetId: string, promotionId: string, approve: boolean, reason?: string) =>
  answered<Promotion>(
    send(dataset(api, datasetId, `promotions/${encodeURIComponent(promotionId)}/decision`), token, {
      method: "POST",
      body: JSON.stringify({ approve, ...(reason ? { reason } : {}) }),
    }),
    "The decision could not be recorded",
  );

// --- a removed case's layer ----------------------------------------------------------------------

export const removedCases = (api: string, token: string, datasetId: string) =>
  answered<RemovedCaseLayers>(send(dataset(api, datasetId, "removed-cases"), token), "The removed cases could not be read");

export const openLayerMerge = (api: string, token: string, datasetId: string, caseId: string) =>
  answered<LayerMergeSheet>(
    send(dataset(api, datasetId, `removed-cases/${encodeURIComponent(caseId)}/merge-sheet`), token, { method: "POST" }),
    "The merge sheet could not be opened",
  );

export const mergeLayer = (api: string, token: string, datasetId: string, grantId: string, itemIds: string[]) =>
  answered<Promotion>(
    send(dataset(api, datasetId, `layer-merges/${encodeURIComponent(grantId)}`), token, { method: "POST", body: JSON.stringify({ item_ids: itemIds }) }),
    "The merge could not be sent",
  );

export const cancelLayerMerge = (api: string, token: string, datasetId: string, grantId: string) =>
  answered<null>(send(dataset(api, datasetId, `layer-merges/${encodeURIComponent(grantId)}`), token, { method: "DELETE" }), "The merge could not be cancelled", true);

/** The Author's dry run of *Delete* (Amendment 2 decision 1): what it would touch, in counts as
 * this reader's own handling takes them; nothing written. */
export const dryRunDeleteLayer = (api: string, token: string, datasetId: string, caseId: string) =>
  answered<LayerDryRun>(
    send(dataset(api, datasetId, `removed-cases/${encodeURIComponent(caseId)}/delete/dry-run`), token, { method: "POST" }),
    "The dry run could not be made",
  );

export const deleteLayer = (api: string, token: string, datasetId: string, caseId: string) =>
  answered<LayerDeleted>(
    send(dataset(api, datasetId, `removed-cases/${encodeURIComponent(caseId)}/layer`), token, { method: "DELETE" }),
    "The layer could not be deleted",
  );

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
