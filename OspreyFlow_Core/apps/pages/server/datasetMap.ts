/**
 * The Ingest Studio's dataset map, as a server-rendered page of the Default tree (slice IS3; ADR-140 Amendment 22 items 1 and 8;
 * ADR-152 decisions 6, 7 and 12). The route, and the view model its template draws:
 *
 *   GET  /studio/dataset-map?case=<case>[&dataset=<dataset>]   a read-only table of the pipelines that load the dataset
 *
 * The path is under `/studio` because decision 7 sends the Studio's paths (`/studio/…`) to this service on the default theme.
 * It takes the Studio frame's own parameters, so the frame's dataset switch works from it: `case` is the case the Studio works
 * through, and `dataset` (optional) one of the datasets the person's cases load into.
 *
 * Every read is made as the person (`conduit.ts`) and the Conduit authorises each (rules 3 and 4): the pipelines come from the
 * case's recipe registry, which the Conduit reads through the case's datasets and refuses to anyone without Edit pipelines. This
 * page adds no access rule of its own; it says the same words for every reason it cannot draw the table (a right not held, a
 * case the Conduit no longer opens, a dataset no case of the person's loads into, a dataset that does not exist), and it draws
 * only the rows of the dataset it is open on, with no count of any other.
 *
 * It draws no column for the order pipelines run in, and no line: that is IS6's, shown only once the order is stored.
 */
import type { Request, Response } from "express";

import { context, loadFrame, one } from "./studio.js";
import type { Frame } from "./studio.js";
import type { PageModule } from "./pages.js";
import { DATASET_MAP_WORDS, mapRows } from "./views/datasetMapWords.js";
import type { MapRow } from "./views/datasetMapWords.js";

export type MapView =
  /** Nothing of the map is drawn: the frame has already said why (the cases could not be read). */
  | { kind: "none" }
  | { kind: "refused" }
  | { kind: "unreadable" }
  | { kind: "empty" }
  | { kind: "table"; caption: string; rows: MapRow[] };

/** What the page draws, and the status it is sent with, from what the frame read. */
export function viewOf(frame: Frame): { view: MapView; status: number } {
  if (frame.casesProblem !== null) return { view: { kind: "none" }, status: 200 };
  // A dataset asked for that no case of the person's loads into, a case that is not theirs or loads into none: one answer.
  if (frame.switchProblem !== null || frame.datasetId === null) return { view: { kind: "refused" }, status: 200 };
  const registry = frame.registry;
  if (registry === null || registry.list === undefined) {
    // A 4xx is the Conduit saying no (a right not held, a case it no longer opens): the same words as every other refusal.
    // Anything else is a failing Conduit, which says to try again and never draws an empty table (rule 2).
    return registry !== null && registry.status >= 400 && registry.status < 500
      ? { view: { kind: "refused" }, status: 403 }
      : { view: { kind: "unreadable" }, status: 502 };
  }
  const rows = mapRows(registry.list, frame.datasetId);
  return rows.length === 0
    ? { view: { kind: "empty" }, status: 200 }
    : { view: { kind: "table", caption: DATASET_MAP_WORDS.caption(frame.datasetName), rows }, status: 200 };
}

async function datasetMapGet(req: Request, res: Response): Promise<void> {
  const wanted = one(req.query["dataset"]);
  const frame = await loadFrame(req, res, {
    path: "/studio/dataset-map",
    place: "dataset-map",
    caseId: one(req.query["case"]),
    ...(wanted === undefined ? {} : { wantsDataset: wanted }),
  });
  if (frame === "sent") return;
  // The frame's own note about a pipelines read that did not work is this page's table's to say, once.
  frame.pipelinesProblem = null;
  const { view, status } = viewOf(frame);
  res.status(status).render("studio/dataset-map", context(req, frame, { title: DATASET_MAP_WORDS.title, dm: view, mapWords: DATASET_MAP_WORDS }));
}

export const studioDatasetMap: PageModule = {
  id: "studio-dataset-map",
  path: "/studio/dataset-map",
  methods: ["GET"],
  handler: datasetMapGet,
};
