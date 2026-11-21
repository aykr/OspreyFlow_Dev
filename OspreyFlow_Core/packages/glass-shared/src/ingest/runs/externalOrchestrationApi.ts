// The Runs tab's four requests for external orchestration (`06_DECISIONS.md` ADR-141 decisions 6, 9 and 11): a
// deployed pipeline's quota use, and *Owned externally* (who the one service identity is that an orchestrator
// triggers it as): read, marked, taken back. Plain TypeScript: each takes the bearer token as an argument and
// touches nothing but the Conduit, so the screen (`ExternalOrchestration.tsx`, in the workspace) and a
// server-rendered page call the same four. The Conduit decides who may; these only ask.
import type { ExternallyOwnedInput, RunQuotaUse } from "../../../../schemas/generated";

export function recipeUrl(apiBaseUrl: string, investigationId: string, recipeId: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/ingest/recipes/${encodeURIComponent(recipeId)}`;
}

async function words(response: Response, what: string): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
  return typeof body.detail === "string" ? body.detail : `${what} was refused (${response.status}).`;
}

/** Today's runs into the pipeline's dataset against the dataset's quota; `null` when the Conduit gives none. */
export function readQuota(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
): Promise<RunQuotaUse | null> {
  const url = recipeUrl(apiBaseUrl, investigationId, recipeId);
  return fetch(`${url}/quota`, { headers: { Authorization: `Bearer ${bearerToken}` } }).then((r) =>
    r.ok ? (r.json() as Promise<RunQuotaUse>) : null,
  );
}

/** Who the pipeline is owned externally by; `null` when nobody, or when the Conduit gives none. */
export function readOwnedExternally(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
): Promise<ExternallyOwnedInput | null> {
  const url = recipeUrl(apiBaseUrl, investigationId, recipeId);
  return fetch(`${url}/owned-externally`, { headers: { Authorization: `Bearer ${bearerToken}` } }).then((r) =>
    r.ok ? (r.json() as Promise<ExternallyOwnedInput | null>) : null,
  );
}

/** Marks the pipeline owned externally by the service identity `clientId`. */
export async function markOwnedExternally(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
  clientId: string,
): Promise<ExternallyOwnedInput> {
  const url = recipeUrl(apiBaseUrl, investigationId, recipeId);
  const r = await fetch(`${url}/owned-externally`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: clientId.trim() }),
  });
  if (!r.ok) throw new Error(await words(r, "Marking it owned externally"));
  return (await r.json()) as ExternallyOwnedInput;
}

/** Takes the pipeline back from the orchestrator. */
export async function clearOwnedExternally(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  recipeId: string,
): Promise<void> {
  const url = recipeUrl(apiBaseUrl, investigationId, recipeId);
  const r = await fetch(`${url}/owned-externally`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!r.ok) throw new Error(await words(r, "Taking it back"));
}
