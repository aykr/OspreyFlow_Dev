// An expansion promoted to a batch job at the working-set cap (ADR-151; spec/00 §4's third choice):
// the Conduit's worker runs the whole expansion under the requester's own access and saves its
// result as a private view of the case (ADR-144), which the Glass then opens as the lens. Nothing
// joins the case's working set and no delta arrives: the result is the view only.
//
// The routes are rules-b's (ADR-151's draft, lane/rules-b-v052batch 208c397):
//   POST /v1/investigations/{case}/batch-expansions   {request: ExpandRequest}
//        202 BatchExpansion (queued)   403 below Editor, or without the right   404 the case not opened
//        409 {error: "batch_expansion_running", detail, id}: the reader already has one here; follow it
//   GET  /v1/investigations/{case}/batch-expansions/{job}   200 BatchExpansion   404 not this reader's
//   BatchExpansion = {id, state: queued|running|done|refused|failed, words, view: CaseView | null,
//                     nodes, links, refusal: {code, cap_kind?, cap?, would_be?} | null}
// It decides nothing: `words` is always a whole sentence and is shown as given; the Glass adds only
// what it itself did (opened the view, or could not).
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

export type RefusalCode = "too_many_nodes" | "too_many_links" | "found_nothing" | "no_longer_an_editor" | "took_too_long";

export interface BatchExpansionJob {
  id: string;
  state: "queued" | "running" | "done" | "refused" | "failed";
  words: string;
  view: CaseView | null;
  nodes: number | null;
  links: number | null;
  refusal: { code: RefusalCode; cap_kind?: "nodes" | "edges"; cap?: number; would_be?: number } | null;
}

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

const STATES = new Set(["queued", "running", "done", "refused", "failed"]);

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

/** A job as the Conduit sent it, or null when it is not one: a state the Glass does not know, or
 * no id, is never read as progress. */
function asJob(body: Record<string, unknown>): BatchExpansionJob | null {
  if (typeof body.id !== "string" || !body.id || typeof body.state !== "string" || !STATES.has(body.state)) return null;
  return {
    id: body.id,
    state: body.state as BatchExpansionJob["state"],
    words: typeof body.words === "string" ? body.words : "",
    view: (body.view as CaseView | null | undefined) ?? null,
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
  try {
    const response = await fetch(batchUrl(apiBaseUrl, caseId), {
      method: "POST",
      headers: headers(bearerToken),
      body: JSON.stringify({
        request: {
          node_ids: [request.nodeId],
          depth: request.depth,
          edge_types: request.edgeType ? [request.edgeType] : null,
        },
      }),
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
