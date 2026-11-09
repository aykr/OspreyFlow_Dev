// The Ingest Studio's calls for promotion (ADR-143 decisions 8 and 10; Amendment 2 decision 1;
// `spec/03_CONDUIT_MIDDLEWARE.md` §3.1c, *Promotion*): its *Analyst promotions* and a removed case's
// layer merged or deleted. The board's own calls, and the words both share, are in
// `boards/promotionsApi.ts`. It decides nothing: each refusal comes back in words, shown as given.
import {
  answered,
  send,
  type LayerDeleted,
  type LayerDryRun,
  type LayerMergeSheet,
  type Promotion,
  type PromotionDetails,
  type Promotions,
  type RemovedCaseLayers,
} from "../../boards/promotionsApi";

const dataset = (api: string, datasetId: string, tail: string) => `${api}/v1/datasets/${encodeURIComponent(datasetId)}/${tail}`;

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
