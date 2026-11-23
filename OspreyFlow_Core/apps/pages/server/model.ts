/**
 * The Ingest Studio's Model step, as a server-rendered page of the Default tree (slice IS2a; ADR-140 Amendment 22 items 1, 3
 * and 4; ADR-152 decisions 5, 6, 7 and 12; FUNCTIONS rows `studio-model-text` and `studio-model-proposals`). The route, and the
 * view model its template draws:
 *
 *   GET  /studio/model?case=<case>[&dataset=<dataset>]   the dataset's domain model: the draft's types and the live version's
 *   POST /studio/model                                    one form each: `open` a draft, `save` it, `discard` it
 *
 * The path is under `/studio` because decision 7 sends the Studio's paths to this service on the default theme. It takes the
 * frame's own parameters, so the frame's dataset switch works from it.
 *
 * Every read and write is made as the person (`conduit.ts`: their bearer and nothing of the browser's), and the Conduit
 * authorises each (rules 3 and 4): this page adds no access rule of its own. It says the same words for every reason it cannot
 * draw the model (a right not held, a dataset the Conduit no longer opens, one no case of the person's loads into, one that does
 * not exist), draws no row or count it was not sent, and never echoes a dataset's id.
 *
 * A save and a discard carry the version the person's copy was read at, in a hidden field, and the page hands the Conduit that
 * very number: the Conduit's store refuses a draft that is no longer that version, and the page says the copy was out of date,
 * shows the draft as it now is and keeps what the person typed. The page does not decide for the Conduit: a stale request is
 * sent and refused there. Only the draft's creator is offered the forms (the page compares the draft's creator with the person's
 * own id, as words about who may act), and the Conduit refuses anyone else's request all the same.
 *
 * A read or a write that failed is said in an alert and never drawn as an empty model (rule 2).
 */
import type { Request, Response } from "express";

import { ConduitUnreachable, v1 } from "./conduit.js";
import type { Call, Conduit, Reply } from "./conduit.js";
import type { PageModule } from "./pages.js";
import { context, loadFrame, one } from "./studio.js";
import type { Frame } from "./studio.js";
import { refusalWords } from "./views/studioWords.js";
import { MODEL_WORDS, PACK_FIELDS, packsFrom, pinsOf, readModel, storeWords, typeRows, versionOf, whenWords } from "./views/modelWords.js";
import type { ModelRead, ModelVersion, TypeRow } from "./views/modelWords.js";

interface DraftView {
  version: number;
  held: string;
  builtOn: string;
  caption: string;
  rows: TypeRow[];
  /** The forms are the person's to use: they hold the draft (or the page cannot tell, and the Conduit decides). */
  mine: boolean;
  notYours: string;
  packs: { id: string; field: string; text: string; value: string }[];
}

interface LiveView {
  version: string;
  builtOn: string;
  caption: string;
  rows: TypeRow[];
}

export type ModelView =
  /** Nothing of the model is drawn: the frame has already said why (no case, or the cases could not be read). */
  | { kind: "none" }
  | { kind: "refused" }
  | { kind: "unreadable" }
  | { kind: "model"; draft: DraftView | null; live: LiveView | null };

interface Shown {
  view: ModelView;
  status: number;
  /** What the Conduit answered, when it was a model. */
  read: ModelRead | undefined;
}

// --------------------------------------------------------------------------------------------------------------- reading

/** A call to the Conduit as the person, or `undefined` when it could not be reached: a failure is never an answer. */
async function ask(conduit: Conduit, call: Call): Promise<Reply | undefined> {
  try {
    return await conduit(call);
  } catch (error) {
    if (error instanceof ConduitUnreachable) return undefined;
    throw error;
  }
}

const modelPath = (datasetId: string): string => v1("datasets", datasetId, "model");
const draftPath = (datasetId: string): string => v1("datasets", datasetId, "model", "draft");

function draftView(frame: Frame, draft: ModelVersion, typed: Record<string, string> | undefined): DraftView {
  const pins = pinsOf(draft.packs);
  return {
    version: draft.version,
    held: MODEL_WORDS.held(draft.version, draft.created_by, whenWords(draft.created_at)),
    builtOn: MODEL_WORDS.builtOn(draft.packs),
    caption: MODEL_WORDS.draftCaption(frame.datasetName),
    rows: typeRows(draft.extensions),
    mine: frame.meId === null || draft.created_by === frame.meId,
    notYours: MODEL_WORDS.notYours(draft.created_by),
    packs: PACK_FIELDS.map((pack) => ({
      id: pack.id,
      field: pack.field,
      text: MODEL_WORDS.packLabel(pack.label),
      value: typed?.[pack.field] ?? pins[pack.field] ?? "",
    })),
  };
}

function liveView(frame: Frame, live: ModelVersion): LiveView {
  return {
    version: MODEL_WORDS.liveVersion(live.version, live.made_live_by ?? null, live.made_live_at ? whenWords(live.made_live_at) : null),
    builtOn: MODEL_WORDS.builtOn(live.packs),
    caption: MODEL_WORDS.liveCaption(frame.datasetName),
    rows: typeRows(live.extensions),
  };
}

/**
 * What the page draws for the dataset the frame is open on, and the status it is sent with. A 4xx is the Conduit saying no (a
 * right not held, a dataset it no longer opens): one sentence for every such reason. Anything else that is not a model is a
 * failing service, which says to try again and never draws an empty model.
 */
async function showModel(frame: Frame, typed?: Record<string, string>): Promise<Shown> {
  if (frame.caseId === null || frame.casesProblem !== null) return { view: { kind: "none" }, status: 200, read: undefined };
  // A dataset asked for that no case of the person's loads into, a case that is not theirs or loads into none: one answer.
  if (frame.switchProblem !== null || frame.datasetId === null || frame.conduit === undefined) {
    return { view: { kind: "refused" }, status: 200, read: undefined };
  }
  const reply = await ask(frame.conduit, { path: modelPath(frame.datasetId) });
  if (reply !== undefined && reply.status >= 400 && reply.status < 500) return { view: { kind: "refused" }, status: 403, read: undefined };
  const read = reply?.status === 200 ? readModel(reply.json) : undefined;
  if (read === undefined) return { view: { kind: "unreadable" }, status: 502, read: undefined };
  return {
    view: {
      kind: "model",
      draft: read.draft === null ? null : draftView(frame, read.draft, typed),
      live: read.live === null ? null : liveView(frame, read.live),
    },
    status: 200,
    read,
  };
}

function render(req: Request, res: Response, frame: Frame, shown: Shown, extra: { problem?: string | null; notice?: string | null; status?: number }): void {
  // The frame's own note about a pipelines read that did not work belongs to the pipelines' pages; this page says what it read.
  frame.pipelinesProblem = null;
  res.status(shown.view.kind === "model" ? (extra.status ?? shown.status) : shown.status).render(
    "studio/model",
    context(req, frame, { title: MODEL_WORDS.title, mv: shown.view, modelWords: MODEL_WORDS, problem: extra.problem ?? null, notice: extra.notice ?? null }),
  );
}

async function modelGet(req: Request, res: Response): Promise<void> {
  const wanted = one(req.query["dataset"]);
  const frame = await loadFrame(req, res, {
    path: "/studio/model",
    place: "model",
    caseId: one(req.query["case"]),
    ...(wanted === undefined ? {} : { wantsDataset: wanted }),
  });
  if (frame === "sent") return;
  render(req, res, frame, await showModel(frame), {});
}

// -------------------------------------------------------------------------------------------------------------- writing

type Outcome = "ok" | "ended" | "refused" | "conflict" | "other" | "failed";

/** What a write's answer means to the page: it carried out, the session ended, the Conduit said no, there is a conflict, another refusal, or a failure. */
function outcomeOf(reply: Reply | undefined): Outcome {
  if (reply === undefined) return "failed";
  if (reply.status >= 200 && reply.status < 300) return "ok";
  if (reply.status === 401) return "ended";
  if (reply.status === 403 || reply.status === 404) return "refused";
  if (reply.status === 409) return "conflict";
  if (reply.status >= 400 && reply.status < 500) return "other";
  return "failed";
}

const ACTIONS = ["open", "save", "discard"] as const;
type Action = (typeof ACTIONS)[number];

/** The form's fields that are one string each: an array or an object is not what the page's own form sends. */
function fieldsOf(req: Request): Record<string, string> {
  const fields: Record<string, string> = {};
  const body: unknown = req.body;
  if (typeof body === "object" && body !== null) {
    for (const [key, value] of Object.entries(body as Record<string, unknown>)) if (typeof value === "string") fields[key] = value;
  }
  return fields;
}

/** The pin fields as typed, so a form drawn again holds what the person typed. */
const typedPins = (fields: Record<string, string>): Record<string, string> =>
  Object.fromEntries(PACK_FIELDS.filter((pack) => fields[pack.field] !== undefined).map((pack) => [pack.field, fields[pack.field] as string]));

/**
 * The words for a conflict: the page's own when the copy the person held is not the draft any more (said first, so it is not lost
 * among the store's), then the store's own. The page asked the Conduit with the person's version and it refused there; this only
 * reads the draft as it is now to say what changed.
 */
function conflictWords(did: "saved" | "discarded", expected: number, body: unknown): (fresh: ModelRead | undefined) => string {
  return (fresh) => {
    const store = storeWords(409, body, "The draft");
    if (fresh === undefined) return store;
    const current = fresh.draft;
    if (current === null) return `${MODEL_WORDS.draftGone(did)} ${store}`;
    if (current.version !== expected) return `${MODEL_WORDS.outOfDate(current.version, did)} ${store}`;
    return store;
  };
}

interface Finish {
  status?: number;
  problem?: string | ((fresh: ModelRead | undefined) => string | null);
  notice?: string;
  typed?: Record<string, string>;
}

/** Draws the page after a write: the model as it now is, with what the write said and, when it kept them, what was typed. */
async function finish(req: Request, res: Response, frame: Frame, over: Finish): Promise<void> {
  const shown = await showModel(frame, over.typed);
  const problem = typeof over.problem === "function" ? over.problem(shown.read) : (over.problem ?? null);
  render(req, res, frame, shown, { problem, notice: over.notice ?? null, ...(over.status === undefined ? {} : { status: over.status }) });
}

/** The page for a request the Conduit refused as a right not held or a dataset it does not open: one sentence, no model. */
function refused(req: Request, res: Response, frame: Frame): void {
  render(req, res, frame, { view: { kind: "refused" }, status: 403, read: undefined }, {});
}

async function modelPost(req: Request, res: Response): Promise<void> {
  const fields = fieldsOf(req);
  const frame = await loadFrame(req, res, { path: "/studio/model", place: "model", caseId: fields["case"] });
  if (frame === "sent") return;
  if (frame.caseId === null) {
    res.status(422).render("studio/model", context(req, frame, { title: MODEL_WORDS.title, mv: { kind: "none" }, modelWords: MODEL_WORDS, problem: null, notice: null, refusal: MODEL_WORDS.notUnderstood }));
    return;
  }
  if (frame.casesProblem !== null) {
    render(req, res, frame, { view: { kind: "none" }, status: 502, read: undefined }, {});
    return;
  }
  const conduit = frame.conduit;
  const datasetId = frame.datasetId;
  if (frame.switchProblem !== null || datasetId === null || conduit === undefined) {
    refused(req, res, frame);
    return;
  }
  const action = ACTIONS.find((a) => a === fields["action"]) as Action | undefined;
  if (action === undefined) {
    await finish(req, res, frame, { status: 400, problem: MODEL_WORDS.notUnderstood });
    return;
  }

  if (action === "open") {
    const reply = await ask(conduit, { method: "POST", path: draftPath(datasetId) });
    const outcome = outcomeOf(reply);
    if (outcome === "ok") {
      const made = (reply?.json as { version?: unknown } | undefined)?.version;
      await finish(req, res, frame, { notice: typeof made === "number" ? MODEL_WORDS.opened(made) : "" });
    } else if (outcome === "refused") refused(req, res, frame);
    else if (outcome === "ended") await finish(req, res, frame, { status: 401, problem: refusalWords(401, undefined, "") });
    else if (outcome === "conflict") await finish(req, res, frame, { status: 409, problem: storeWords(409, reply?.json, "The draft") });
    else if (outcome === "other") await finish(req, res, frame, { status: reply?.status ?? 400, problem: MODEL_WORDS.refusedWith("The draft", reply?.status ?? 400) });
    else await finish(req, res, frame, { status: 502, problem: MODEL_WORDS.openFailed });
    return;
  }

  // Both the others carry the version the person's copy was read at: a form that does not is not one the page made.
  const expected = versionOf(fields["expected_version"]);
  if (expected === undefined) {
    await finish(req, res, frame, { status: 400, problem: MODEL_WORDS.notUnderstood });
    return;
  }

  if (action === "discard") {
    const reply = await ask(conduit, { method: "DELETE", path: draftPath(datasetId), query: { expected_version: expected } });
    const outcome = outcomeOf(reply);
    if (outcome === "ok") await finish(req, res, frame, { notice: MODEL_WORDS.discarded });
    else if (outcome === "refused") refused(req, res, frame);
    else if (outcome === "ended") await finish(req, res, frame, { status: 401, problem: refusalWords(401, undefined, "") });
    else if (outcome === "conflict") await finish(req, res, frame, { status: 409, problem: conflictWords("discarded", expected, reply?.json) });
    else if (outcome === "other") await finish(req, res, frame, { status: reply?.status ?? 400, problem: MODEL_WORDS.refusedWith("The draft", reply?.status ?? 400) });
    else await finish(req, res, frame, { status: 502, problem: MODEL_WORDS.discardFailed });
    return;
  }

  // ---- save: the packs as typed, the draft's own types and lists as the Conduit has them, and the person's version
  const typed = typedPins(fields);
  const given = packsFrom(typed);
  if ("problem" in given) {
    await finish(req, res, frame, { status: 422, problem: given.problem, typed });
    return;
  }
  const current = await ask(conduit, { path: modelPath(datasetId) });
  const before = outcomeOf(current);
  if (before === "refused") {
    refused(req, res, frame);
    return;
  }
  const read = before === "ok" ? readModel(current?.json) : undefined;
  if (read === undefined) {
    await finish(req, res, frame, { status: 502, problem: MODEL_WORDS.saveFailed, typed });
    return;
  }
  if (read.draft === null) {
    await finish(req, res, frame, { status: 409, problem: MODEL_WORDS.noDraftToSave });
    return;
  }
  const reply = await ask(conduit, {
    method: "PUT",
    path: draftPath(datasetId),
    json: { packs: given.packs, extensions: read.draft.extensions, reference_lists: read.draft.reference_lists, expected_version: expected },
  });
  const outcome = outcomeOf(reply);
  if (outcome === "ok") {
    const saved = (reply?.json as { version?: unknown } | undefined)?.version;
    await finish(req, res, frame, { notice: MODEL_WORDS.saved(typeof saved === "number" ? saved : expected) });
  } else if (outcome === "refused") refused(req, res, frame);
  else if (outcome === "ended") await finish(req, res, frame, { status: 401, problem: refusalWords(401, undefined, ""), typed });
  else if (outcome === "conflict") await finish(req, res, frame, { status: 409, problem: conflictWords("saved", expected, reply?.json), typed });
  else if (outcome === "other") await finish(req, res, frame, { status: reply?.status ?? 400, problem: MODEL_WORDS.refusedWith("The draft", reply?.status ?? 400), typed });
  else await finish(req, res, frame, { status: 502, problem: MODEL_WORDS.saveFailed, typed });
}

export const studioModel: PageModule = {
  id: "studio-model-text",
  path: "/studio/model",
  methods: ["GET", "POST"],
  handler: async (req, res) => {
    if (req.method === "POST") await modelPost(req, res);
    else await modelGet(req, res);
  },
};
