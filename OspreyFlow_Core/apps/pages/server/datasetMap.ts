/**
 * The Ingest Studio's dataset map, as a server-rendered page of the Default tree (slice IS3; ADR-140 Amendment 22 items 1 and 8;
 * ADR-152 decisions 6, 7 and 12), and the place the order pipelines run in is set (slice IS6a; ADR-141 Amendment 2 point 6; the
 * owner's rulings of 24 November 2026). The route, and the view model its template draws:
 *
 *   GET  /studio/dataset-map?case=<case>[&dataset=<dataset>]   the table of the pipelines that load the dataset, and the order form
 *   POST /studio/dataset-map                                    the form: the order as ticked, with the number of the order read
 *
 * The path is under `/studio` because decision 7 sends the Studio's paths (`/studio/…`) to this service on the default theme.
 * It takes the Studio frame's own parameters, so the frame's dataset switch works from it: `case` is the case the Studio works
 * through, and `dataset` (optional) one of the datasets the person's cases load into.
 *
 * Every read and write is made as the person (`conduit.ts`) and the Conduit authorises each (rules 3 and 4): the pipelines come from
 * the case's recipe registry, which the Conduit reads through the case's datasets and refuses to anyone without Edit pipelines, and
 * the stored order from the dataset's own route, which asks the same right and answers a dataset that is not the person's as one that
 * does not exist. This page adds no access rule of its own; it says the same words for every reason it cannot draw the table (a right
 * not held, a case the Conduit no longer opens, a dataset no case of the person's loads into, a dataset that does not exist), and it
 * draws only the rows of the dataset it is open on, with no count of any other and none of what the Conduit left out of the order.
 *
 * The order is "runs after" links, stored and versioned by the Conduit. The "Runs after" column is drawn only when an order is stored
 * (never an empty column); the form carries the number of the order the page read (`expected_version`, 0 when none) and the
 * anti-forgery token, and a save made over an order that has moved on is refused by the Conduit, said, and shown again with what was
 * ticked. A cycle among the pipelines the person can see is refused there, in the Conduit's own words naming the pipelines in it. No script is needed. No suggestion of an
 * order is made or drawn (rule 5).
 */
import type { Request, Response } from "express";

import { ConduitUnreachable, v1 } from "./conduit.js";
import type { Conduit, Reply } from "./conduit.js";
import { context, loadFrame, one } from "./studio.js";
import type { Frame } from "./studio.js";
import type { PageModule } from "./pages.js";
import { DATASET_MAP_WORDS, drawsOrder, fieldsets, mapRows, orderLine, parseLink, readOrder, withOrder } from "./views/datasetMapWords.js";
import type { Fieldset, MapRow, StoredOrder } from "./views/datasetMapWords.js";
import { refusalWords } from "./views/studioWords.js";

/** The form that sets the order: drawn when there is more than one pipeline to put in order and the stored order was read. */
export interface OrderForm {
  /** The number of the stored order the page read (0 when none): sent back, so a save over a later order is refused. */
  expected: number;
  fieldsets: Fieldset[];
}

export type MapView =
  /** Nothing of the map is drawn: the frame has already said why (the cases could not be read). */
  | { kind: "none" }
  | { kind: "refused" }
  | { kind: "unreadable" }
  | { kind: "empty" }
  | {
      kind: "table";
      caption: string;
      rows: MapRow[];
      columns: readonly string[];
      /** Whether the "Runs after" column is drawn: an order is stored and says something about these pipelines. */
      drawsOrder: boolean;
      /** Which version of the order is shown, by whom and when; empty when none is stored. */
      orderLine: string;
      /** The stored order could not be read: said, and no column and no form (it is never drawn as none stored). */
      orderProblem: string | null;
      form: OrderForm | null;
    };

/** What the Conduit answered for the dataset's stored order: its status (0 when unreachable) and the order when it was read. */
export interface OrderRead {
  status: number;
  order: StoredOrder | undefined;
}

/** What the page draws, and the status it is sent with, from what the frame read and the order's read. */
export function viewOf(frame: Frame, read?: OrderRead, typed?: ReadonlySet<string>): { view: MapView; status: number } {
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
  if (rows.length === 0) return { view: { kind: "empty" }, status: 200 };
  // The order's own route refuses as the registry does (a right not held, a dataset that is not the person's): one answer.
  if (read !== undefined && read.status >= 400 && read.status < 500) return { view: { kind: "refused" }, status: 403 };
  const order = read?.order;
  const readable = order !== undefined;
  const shown = readable && drawsOrder(rows, order);
  return {
    view: {
      kind: "table",
      caption: DATASET_MAP_WORDS.caption(frame.datasetName),
      rows: shown ? withOrder(rows, order) : rows,
      columns: shown ? DATASET_MAP_WORDS.columnsWithOrder : DATASET_MAP_WORDS.columns,
      drawsOrder: shown,
      orderLine: readable ? orderLine(order) : "",
      orderProblem: readable ? null : DATASET_MAP_WORDS.orderUnreadable,
      // Nothing to put in order with fewer than two pipelines; and no form over an order that could not be read.
      form: readable && rows.length > 1 ? { expected: order.version, fieldsets: fieldsets(rows, order, typed) } : null,
    },
    status: readable ? 200 : 502,
  };
}

// ------------------------------------------------------------------------------------------------------------- reading

const orderPath = (datasetId: string): string => v1("datasets", datasetId, "run-order");

/** A call to the Conduit as the person, or `undefined` when it could not be reached: a failure is never an answer. */
async function ask(conduit: Conduit, call: Parameters<Conduit>[0]): Promise<Reply | undefined> {
  try {
    return await conduit(call);
  } catch (error) {
    if (error instanceof ConduitUnreachable) return undefined;
    throw error;
  }
}

/** The stored order, read once, for a dataset whose pipelines were read. Only a 200 that is an order is one. */
async function readStoredOrder(frame: Frame): Promise<OrderRead | undefined> {
  const registry = frame.registry;
  if (frame.conduit === undefined || frame.datasetId === null || frame.switchProblem !== null || registry?.list === undefined) return undefined;
  if (mapRows(registry.list, frame.datasetId).length === 0) return undefined;
  const reply = await ask(frame.conduit, { path: orderPath(frame.datasetId) });
  if (reply === undefined) return { status: 0, order: undefined };
  return { status: reply.status, order: reply.status === 200 ? readOrder(reply.json) : undefined };
}

interface Finish {
  status?: number;
  problem?: string;
  notice?: string;
  typed?: ReadonlySet<string>;
}

/** Draws the page: the table and the form as the Conduit has them now, with what was said and, when kept, what was ticked. */
async function draw(req: Request, res: Response, frame: Frame, over: Finish = {}): Promise<void> {
  // The frame's own note about a pipelines read that did not work is this page's table's to say, once.
  frame.pipelinesProblem = null;
  const read = await readStoredOrder(frame);
  const { view, status } = viewOf(frame, read, over.typed);
  res.status(view.kind === "table" && over.status !== undefined ? over.status : status).render(
    "studio/dataset-map",
    context(req, frame, { title: DATASET_MAP_WORDS.title, dm: view, mapWords: DATASET_MAP_WORDS, problem: over.problem ?? null, notice: over.notice ?? null }),
  );
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
  await draw(req, res, frame);
}

// ------------------------------------------------------------------------------------------------------------- writing

/** The form's fields that are one string each, and the tick boxes (`link`, one or many): anything else is not what the page sends. */
function fieldsOf(req: Request): { fields: Record<string, string>; links: string[] | undefined } {
  const fields: Record<string, string> = {};
  let links: string[] | undefined = [];
  const body: unknown = req.body;
  if (typeof body === "object" && body !== null) {
    for (const [key, value] of Object.entries(body as Record<string, unknown>)) {
      if (key === "link") {
        if (typeof value === "string") links = [value];
        else if (Array.isArray(value) && value.every((v) => typeof v === "string")) links = value as string[];
        else links = undefined;
      } else if (typeof value === "string") fields[key] = value;
    }
  }
  return { fields, links };
}

/** The Conduit's own words for a refusal of the order, when it gave them (its own codes, a string, not too long); else the page's. */
function orderWords(reply: Reply): string {
  const said = reply.json as { error?: unknown; detail?: unknown } | undefined;
  const mine = said?.error === "run_order_refused" || said?.error === "run_order_cycle";
  if (mine && typeof said?.detail === "string" && said.detail.trim() !== "" && said.detail.length <= 1000) return said.detail;
  return DATASET_MAP_WORDS.refusedOrder(reply.status);
}

async function datasetMapPost(req: Request, res: Response): Promise<void> {
  const { fields, links } = fieldsOf(req);
  const frame = await loadFrame(req, res, { path: "/studio/dataset-map", place: "dataset-map", caseId: fields["case"] });
  if (frame === "sent") return;
  frame.pipelinesProblem = null;
  if (frame.caseId === null) {
    res.status(422).render("studio/dataset-map", context(req, frame, { title: DATASET_MAP_WORDS.title, dm: { kind: "none" }, mapWords: DATASET_MAP_WORDS, problem: null, notice: null }));
    return;
  }
  if (frame.casesProblem !== null) {
    res.status(502).render("studio/dataset-map", context(req, frame, { title: DATASET_MAP_WORDS.title, dm: { kind: "none" }, mapWords: DATASET_MAP_WORDS, problem: null, notice: null }));
    return;
  }
  const conduit = frame.conduit;
  const datasetId = frame.datasetId;
  if (frame.switchProblem !== null || datasetId === null || conduit === undefined || frame.registry?.list === undefined) {
    // No such dataset, one that is not the person's, a right not held, a failing read: the page as a GET draws it, the same words.
    await draw(req, res, frame);
    return;
  }
  // The form was for the dataset the person read; a page open on another is refused before anything is sent.
  if (fields["dataset"] !== datasetId) {
    await draw(req, res, frame, { status: 409, problem: DATASET_MAP_WORDS.otherDataset });
    return;
  }
  const expected = /^\d{1,9}$/.test(fields["expected_version"] ?? "") ? Number(fields["expected_version"]) : undefined;
  const pairs = links?.map(parseLink);
  if (expected === undefined || pairs === undefined || pairs.some((pair) => pair === undefined)) {
    await draw(req, res, frame, { status: 400, problem: DATASET_MAP_WORDS.notUnderstood });
    return;
  }
  const after = new Map<string, string[]>();
  for (const [pipeline, earlier] of pairs as [string, string][]) after.set(pipeline, [...new Set([...(after.get(pipeline) ?? []), earlier])]);
  const typed = new Set((links ?? []).filter((value) => parseLink(value) !== undefined));
  const reply = await ask(conduit, {
    method: "PUT",
    path: orderPath(datasetId),
    json: { expected_version: expected, entries: [...after].map(([pipeline_id, runs_after]) => ({ pipeline_id, runs_after })) },
  });
  if (reply === undefined || reply.status >= 500) {
    await draw(req, res, frame, { status: 502, problem: DATASET_MAP_WORDS.saveFailed, typed });
    return;
  }
  if (reply.status >= 200 && reply.status < 300) {
    const saved = (reply.json as { version?: unknown } | undefined)?.version;
    await draw(req, res, frame, { notice: typeof saved === "number" ? DATASET_MAP_WORDS.saved(saved) : DATASET_MAP_WORDS.saved(expected + 1) });
    return;
  }
  if (reply.status === 401) {
    await draw(req, res, frame, { status: 401, problem: refusalWords(401, undefined, ""), typed });
    return;
  }
  // A right not held, or a dataset the Conduit does not open: one sentence, nothing of the order.
  if (reply.status === 403 || reply.status === 404) {
    res.status(403).render("studio/dataset-map", context(req, frame, { title: DATASET_MAP_WORDS.title, dm: { kind: "refused" }, mapWords: DATASET_MAP_WORDS, problem: null, notice: null }));
    return;
  }
  const words = orderWords(reply);
  const moved = reply.status === 409 ? `${DATASET_MAP_WORDS.movedOn} ${words}` : words;
  await draw(req, res, frame, { status: reply.status === 409 ? 409 : reply.status === 422 ? 422 : 400, problem: moved, typed });
}

export const studioDatasetMap: PageModule = {
  id: "studio-dataset-map",
  path: "/studio/dataset-map",
  methods: ["GET", "POST"],
  handler: async (req, res) => {
    if (req.method === "POST") await datasetMapPost(req, res);
    else await datasetMapGet(req, res);
  },
};
