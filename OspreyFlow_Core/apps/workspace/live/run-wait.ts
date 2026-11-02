// What the capture kit waits on when it runs a pipeline (step 9d finding 7). Not a spec, and free of
// Playwright, so the Glass's own unit tests can hold it to the requests the Publish screen sends
// (`src/ingest/publish/runNowWait.test.tsx`).
//
// The kit used to wait for "Succeeded:", "Failed" or "refused" anywhere on the Publish screen. The
// screen's runs list is read when it opens and already holds earlier runs, so an older run's
// "Succeeded:" ended the wait while the new run was still going (found in the v4 captures,
// 2 November 2026). The run-now request is answered only when that run has finished, with that
// run's own load id and counts, so the kit waits on that answer instead.

/** The Publish screen's run-now request (`POST …/ingest/recipes/{id}/run`, `src/ingest/api.ts`'s
 * `runRecipe`): never the runs list's `GET …/runs`, which holds the older runs. */
export function isRunNowRequest(method: string, url: string): boolean {
  if (method.toUpperCase() !== "POST") return false;
  return /\/v1\/investigations\/[^/]+\/ingest\/recipes\/[^/]+\/run$/.test(new URL(url).pathname);
}

function count(body: Record<string, unknown>, key: string): number {
  const value = body[key];
  return typeof value === "number" ? value : 0;
}

/** The new run's own outcome, in words, from its own answer: its load id and counts, or why it was
 * refused. */
export function runNowOutcome(status: number, body: unknown): string {
  const fields = body !== null && typeof body === "object" ? (body as Record<string, unknown>) : {};
  if (status >= 200 && status < 300) {
    const load = typeof fields.load_id === "string" ? ` (load ${fields.load_id})` : "";
    if (fields.withheld === true) return `Succeeded${load}: counts withheld`;
    const rejected = Array.isArray(fields.rejections) ? fields.rejections.length : 0;
    return (
      `Succeeded${load}: ${count(fields, "rows_read")} rows read, ${count(fields, "nodes_created")} created, ` +
      `${count(fields, "nodes_referenced")} referenced, ${rejected} rejected, ${count(fields, "rows_held")} held`
    );
  }
  const detail = typeof fields.detail === "string" ? `: ${fields.detail}` : "";
  return status >= 400 && status < 500 ? `Refused (${status})${detail}` : `Failed (${status})${detail}`;
}
