// An expansion promoted to a batch job at the working-set cap (ADR-151; spec/00 §4's third choice):
// the Conduit's worker runs the whole expansion under the requester's own access and saves its
// result as a private view of the case (ADR-144), which the reader's *Open the view* opens as the lens. Nothing
// joins the case's working set and no delta arrives: the result is the view only.
//
// The routes are rules-b's (ADR-151; `services/api/app.py`'s batch expansions, on main at 354c707):
//   POST /v1/investigations/{case}/batch-expansions   {request: ExpandRequest}
//        202 BatchExpansion (queued)   403 below Editor, or without the right   404 the case not opened
//        409 {error: "batch_expansion_running", detail, id}: the reader already has one here; follow it
//   GET  /v1/investigations/{case}/batch-expansions/{job}   200 BatchExpansion   404 not this reader's
//   BatchExpansion = {id, state: queued|running|done|refused|failed, words, view: CaseView | null,
//                     nodes, links, refusal: {code, cap_kind?, cap?, would_be?} | null}
// It decides nothing: `words` is always a whole sentence and is shown as given; the Glass adds only
// what it itself did (opened the view, or could not).
import type {
  BatchExpansion,
  BatchExpansionInput,
  BatchRefusal,
} from "../../../../packages/schemas/generated";
import type { CaseView } from "../views/viewsApi";
import type { LimitExceeded } from "./models";

/** What the canvas hands over when the reader chooses "Run as a batch job" on an expansion the cap
 * refused (case's `onRunExpansionAsBatch`). */
export interface BatchExpansionRequest {
  nodeId: string;
  edgeType: string | null;
  depth: number;
  refused: LimitExceeded;
}

export type RefusalCode = BatchRefusal["code"];

/** The Conduit's `BatchExpansion` (packages/schemas/batch_expansion.py, generated), its optional
 * fields made present: a field the server left out is read as null. */
export type BatchExpansionJob = Required<Omit<BatchExpansion, "view" | "refusal" | "nodes" | "links">> & {
  view: CaseView | null;
  nodes: number | null;
  links: number | null;
  refusal: BatchRefusal | null;
};

export type Started =
  | { ok: true; job: BatchExpansionJob }
  /** The reader already has a batch job on this case: the one to follow, and the server's words. */
  | { ok: true; running: { id: string; words: string } }
  /** The case level is too low: a batch job needs Editor, as `/expand` does. `words` is the
   * Conduit's own sentence (`_authorized_at`'s `detail`), shown as given, when it sent one. */
  | { ok: false; kind: "forbidden"; words: string | null }
  /** The account lacks the right the route names (`require_right`'s `right_required`). */
  | { ok: false; kind: "right_required" }
  | { ok: false; kind: "not_found" }
  | { ok: false; kind: "failed"; message: string };

export type Read =
  | { ok: true; job: BatchExpansionJob }
  | { ok: false; kind: "not_found" }
  | { ok: false; kind: "unreachable"; message: string }
  /** The reading itself refused (401 the sign-in ended, 403): asking again changes nothing. */
  | { ok: false; kind: "refused"; message: string }
  | { ok: false; kind: "unknown"; message: string };

// Every state the schema names, and only those: a state added to it fails to compile here.
const STATE_LIST = ["queued", "running", "done", "refused", "failed"] as const satisfies readonly BatchExpansion["state"][];
type MissingState = Exclude<BatchExpansion["state"], (typeof STATE_LIST)[number]>;
const EVERY_STATE: [MissingState] extends [never] ? true : MissingState = true;
void EVERY_STATE;
const STATES = new Set<string>(STATE_LIST);

function batchUrl(apiBaseUrl: string, caseId: string, tail = ""): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(caseId)}/batch-expansions${tail}`;
}

function headers(bearerToken: string): Record<string, string> {
  return { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" };
}

async function bodyOf(response: Response): Promise<Record<string, unknown>> {
  return ((await response.json().catch(() => ({}))) ?? {}) as Record<string, unknown>;
}

function unreachable(err: unknown): string {
  return `The server could not be reached: ${err instanceof Error ? err.message : String(err)}`;
}

/** A saved view, checked as far as the panel reads it: its id to open and its name to say. */
function isView(view: unknown): view is CaseView {
  const v = view as { id?: unknown; name?: unknown } | null | undefined;
  return typeof v === "object" && v !== null && typeof v.id === "string" && v.id !== "" && typeof v.name === "string";
}

/** A job as the Conduit sent it, or null when it is not one: a state the Glass does not know, or
 * no id, is never read as progress. */
function asJob(body: Record<string, unknown>): BatchExpansionJob | null {
  if (typeof body.id !== "string" || !body.id || typeof body.state !== "string" || !STATES.has(body.state)) return null;
  return {
    id: body.id,
    state: body.state as BatchExpansionJob["state"],
    words: typeof body.words === "string" ? body.words : "",
    view: isView(body.view) ? body.view : null,
    nodes: typeof body.nodes === "number" ? body.nodes : null,
    links: typeof body.links === "number" ? body.links : null,
    refusal: (body.refusal as BatchExpansionJob["refusal"] | undefined) ?? null,
  };
}

/** Asks the Conduit to run the refused expansion, exactly as it was asked for, as a batch job. */
export async function startBatchExpansion(
  apiBaseUrl: string,
  bearerToken: string,
  caseId: string,
  request: BatchExpansionRequest,
): Promise<Started> {
  // The canvas's own `/expand` body (`canvas/GlassCanvas.tsx`), the schema's fields by name: the generated
  // `ExpandRequest` takes any key, and the Conduit drops one it does not know, so a misspelt field would run the
  // expansion over every type. Picked, the literal below is checked key by key.
  const sent: { request: Required<Pick<BatchExpansionInput["request"], "node_ids" | "depth" | "edge_types">> } = {
    request: {
      node_ids: [request.nodeId],
      depth: request.depth,
      edge_types: request.edgeType ? [request.edgeType] : null,
    },
  };
  try {
    const response = await fetch(batchUrl(apiBaseUrl, caseId), {
      method: "POST",
      headers: headers(bearerToken),
      body: JSON.stringify(sent satisfies BatchExpansionInput),
    });
    const body = await bodyOf(response);
    if (response.ok) {
      const job = asJob(body);
      if (job) return { ok: true, job };
      return { ok: false, kind: "failed", message: "The server accepted the batch job but did not say which it was." };
    }
    if (response.status === 409 && body.error === "batch_expansion_running" && typeof body.id === "string" && body.id) {
      return { ok: true, running: { id: body.id, words: typeof body.detail === "string" ? body.detail : "" } };
    }
    if (response.status === 403) {
      const detail = (typeof body.detail === "object" ? body.detail : undefined) as Record<string, unknown> | undefined;
      if (detail?.error === "right_required") return { ok: false, kind: "right_required" };
      return { ok: false, kind: "forbidden", words: typeof body.detail === "string" && body.detail ? body.detail : null };
    }
    if (response.status === 404) return { ok: false, kind: "not_found" };
    return { ok: false, kind: "failed", message: `The batch job could not be started (${response.status}).` };
  } catch (err) {
    return { ok: false, kind: "failed", message: unreachable(err) };
  }
}

/** Where the job is now, as the Conduit says it. */
export async function readBatchExpansion(apiBaseUrl: string, bearerToken: string, caseId: string, jobId: string): Promise<Read> {
  try {
    const response = await fetch(batchUrl(apiBaseUrl, caseId, `/${encodeURIComponent(jobId)}`), {
      headers: headers(bearerToken),
    });
    if (response.status === 404) return { ok: false, kind: "not_found" };
    if (response.status === 401) {
      return { ok: false, kind: "refused", message: "The job's progress could not be read: your sign-in has ended. Sign in again." };
    }
    if (response.status === 403) {
      return { ok: false, kind: "refused", message: "The job's progress could not be read: you can no longer read this case's batch expansions." };
    }
    if (!response.ok) return { ok: false, kind: "unreachable", message: `The job's progress could not be read (${response.status}).` };
    const job = asJob(await bodyOf(response));
    if (job) return { ok: true, job };
    return { ok: false, kind: "unknown", message: "The server answered with a state the Glass does not know." };
  } catch (err) {
    return { ok: false, kind: "unreachable", message: unreachable(err) };
  }
}
