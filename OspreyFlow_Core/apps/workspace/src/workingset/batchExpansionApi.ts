// An expansion promoted to a batch job at the working-set cap (ADR-151; spec/00 §4's third choice):
// the Conduit's worker runs the whole expansion under the requester's own access and saves its
// result as a view of the case, which the Glass then opens as the lens.
//
// STAND-IN SHAPE. rules-b owns the routes (Conduit and worker) and has not yet sent them; until it
// does, this module is written against the shape below, and it is the one place that changes when
// the real shape arrives:
//   POST /v1/investigations/{case}/expand/batch   {request: {node_ids, depth, edge_types}}
//        202 {job_id}            403 no right to edit the case     404 the case cannot be opened
//        409 limit_exceeded      (the batch job's own limit, a figure of the reader's own)
//   GET  /v1/investigations/{case}/expand/batch/{job_id}
//        200 {state: "queued" | "running" | "done" | "failed" | "refused", done?, total?,
//             view_id?, refused?: LimitExceeded, message?}
//        404 the job (or case) cannot be opened
// It decides nothing: every refusal is the Conduit's, said here in words, and none is guessed at
// from another (rule 15: the stand-in refuses what the real route will).
import type { LimitExceeded } from "./models";

/** What the canvas hands over when the reader chooses "Run as a batch job" on an expansion the cap
 * refused (case's `onRunExpansionAsBatch`). */
export interface BatchExpansionRequest {
  nodeId: string;
  edgeType: string | null;
  depth: number;
  refused: LimitExceeded;
}

export type Started =
  | { ok: true; jobId: string }
  | { ok: false; kind: "forbidden" | "not_found" }
  | { ok: false; kind: "limit_exceeded"; wouldBe: LimitExceeded }
  | { ok: false; kind: "failed"; message: string };

export type JobState =
  | { state: "queued" }
  | { state: "running"; done: number | null; total: number | null }
  | { state: "done"; viewId: string }
  | { state: "refused"; wouldBe: LimitExceeded }
  | { state: "failed"; message: string | null }
  | { state: "not_found" }
  | { state: "unreachable"; message: string };

function batchUrl(apiBaseUrl: string, caseId: string, tail = ""): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(caseId)}/expand/batch${tail}`;
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

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

/** Asks the Conduit to run the refused expansion as a batch job. */
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
    if (response.status === 202 || response.ok) {
      if (typeof body.job_id === "string" && body.job_id) return { ok: true, jobId: body.job_id };
      return { ok: false, kind: "failed", message: "The server accepted the job but did not say which it was. Try again." };
    }
    if (response.status === 403) return { ok: false, kind: "forbidden" };
    if (response.status === 404) return { ok: false, kind: "not_found" };
    if (response.status === 409 && body.error === "limit_exceeded") {
      return { ok: false, kind: "limit_exceeded", wouldBe: body as unknown as LimitExceeded };
    }
    return { ok: false, kind: "failed", message: `The batch job could not be started (${response.status}). Try again.` };
  } catch (err) {
    return { ok: false, kind: "failed", message: unreachable(err) };
  }
}

/** Where the job is now, as the Conduit says it. An answer it does not recognise is a failure said
 * as such, never read as progress. */
export async function readBatchExpansion(
  apiBaseUrl: string,
  bearerToken: string,
  caseId: string,
  jobId: string,
): Promise<JobState> {
  try {
    const response = await fetch(batchUrl(apiBaseUrl, caseId, `/${encodeURIComponent(jobId)}`), {
      headers: headers(bearerToken),
    });
    if (response.status === 404) return { state: "not_found" };
    if (!response.ok) {
      return { state: "unreachable", message: `The job's progress could not be read (${response.status}).` };
    }
    const body = await bodyOf(response);
    switch (body.state) {
      case "queued":
        return { state: "queued" };
      case "running":
        return { state: "running", done: count(body.done), total: count(body.total) };
      case "done":
        if (typeof body.view_id === "string" && body.view_id) return { state: "done", viewId: body.view_id };
        return { state: "failed", message: "The job finished but did not say which view holds its result." };
      case "refused": {
        const refused = body.refused as LimitExceeded | undefined;
        if (refused && refused.error === "limit_exceeded") return { state: "refused", wouldBe: refused };
        return { state: "failed", message: null };
      }
      case "failed":
        return { state: "failed", message: typeof body.message === "string" ? body.message : null };
      default:
        return { state: "failed", message: "The server answered with a state the Glass does not know." };
    }
  } catch (err) {
    return { state: "unreachable", message: unreachable(err) };
  }
}
