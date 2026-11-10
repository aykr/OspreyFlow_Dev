// The Ingest Studio's calls for a drawn dataset merged into another (ADR-143 Amendment 2 decision 6;
// Amendment 3 decision 2; `spec/03_CONDUIT_MIDDLEWARE.md` §3.1d, *Merging a drawn dataset*). It decides
// nothing: who may merge, what may go and what matches are offered are the Conduit's answers, and each
// refusal comes back in words, shown as given. Built in `ingest/runs/` by agreement with the Studio lane.
import type {
  DrawnMergeDryRun,
  DrawnMergeInput,
  DrawnMergeSheet,
  MergeTargets,
  Promotion,
  TypeChoice,
} from "../../../../../packages/schemas/generated";
import { answered, send } from "../../boards/promotionsApi";

export type { DrawnMergeDryRun, DrawnMergeInput, DrawnMergeSheet, MergeTargets, TypeChoice };

/** What is sent: `DrawnMergeInput`, with its items as a plain list (the generated type's is a
 * non-empty tuple; the Conduit checks it, and the screen sends none until one is ticked). */
export type MergeBody = Omit<DrawnMergeInput, "item_ids"> & { item_ids: string[] };

const drawn = (api: string, datasetId: string, tail: string) => `${api}/v1/datasets/${encodeURIComponent(datasetId)}/${tail}`;

export const mergeTargets = (api: string, token: string, datasetId: string) =>
  answered<MergeTargets>(send(drawn(api, datasetId, "merge-targets"), token), "The datasets it may go into could not be read");

export const drawnMergeSheet = (api: string, token: string, datasetId: string, target: string) =>
  answered<DrawnMergeSheet>(
    send(drawn(api, datasetId, `merge-sheet?target=${encodeURIComponent(target)}`), token),
    "The merge could not be read",
  );

export const dryRunDrawnMerge = (api: string, token: string, datasetId: string, body: MergeBody) =>
  answered<DrawnMergeDryRun>(
    send(drawn(api, datasetId, "merges/dry-run"), token, { method: "POST", body: JSON.stringify(body) }),
    "The dry run could not be made",
  );

export const mergeDrawn = (api: string, token: string, datasetId: string, body: MergeBody) =>
  answered<Promotion>(
    send(drawn(api, datasetId, "merges"), token, { method: "POST", body: JSON.stringify(body) }),
    "The merge could not be sent",
  );
