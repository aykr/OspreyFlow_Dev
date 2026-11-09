// Admin › Maps' calls (`06_DECISIONS.md` ADR-147), each behind `manage_geospatial` in the Conduit
// (Build and Verify also the administrator's role). A provider's key is sent once, in the body of
// its own PUT, and never comes back: no response carries one, and a refusal is the Conduit's words.
import type {
  AdminMapProvider,
  MapAdminHistory,
  MapsAdminView,
  PrefetchArea,
  PrefetchRun,
  PrefetchSchedule,
} from "../../../../../packages/schemas/generated";

export type MapProvider = AdminMapProvider["provider"];

export interface MapsApi {
  apiBaseUrl: string;
  bearerToken: string;
}

function refusal(status: number, body: { detail?: unknown }): Error {
  const detail = body.detail as { detail?: string } | string | undefined;
  if (typeof detail === "string") return new Error(detail);
  if (typeof detail?.detail === "string") return new Error(detail.detail);
  if (status === 403) return new Error("Your account does not hold the right to manage geospatial settings.");
  return new Error(`Maps could not complete that (${status}).`);
}

/** One call to the Conduit; `path` is written out whole at each call site (`/v1/admin/maps…`), so
 * the place and section scans read every route this screen uses. */
async function ask<T>(api: MapsApi, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${api.apiBaseUrl}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${api.bearerToken}`, "Content-Type": "application/json" },
  });
  if (!response.ok) throw refusal(response.status, (await response.json().catch(() => ({}))) as { detail?: unknown });
  return (await response.json()) as T;
}

const n = encodeURIComponent;

export const readMaps = (api: MapsApi) => ask<MapsAdminView>(api, "/v1/admin/maps");
export const readMapHistory = (api: MapsApi) => ask<MapAdminHistory>(api, "/v1/admin/maps/history");
export const addProvider = (api: MapsApi, provider: MapProvider) =>
  ask<MapsAdminView>(api, "/v1/admin/maps/providers", { method: "POST", body: JSON.stringify({ provider }) });
export const editProvider = (api: MapsApi, provider: MapProvider) =>
  ask<MapsAdminView>(api, `/v1/admin/maps/providers/${n(provider.id)}`, {
    method: "PUT",
    body: JSON.stringify({ provider }),
  });
export const removeProvider = (api: MapsApi, id: string) =>
  ask<MapsAdminView>(api, `/v1/admin/maps/providers/${n(id)}`, { method: "DELETE" });
export const setMapDefault = (api: MapsApi, id: string) =>
  ask<MapsAdminView>(api, "/v1/admin/maps/default", { method: "PUT", body: JSON.stringify({ default: id }) });
/** Write-only: the key is in this request's body and nowhere else; the answer is the view. */
export const setMapKey = (api: MapsApi, id: string, key: string) =>
  ask<MapsAdminView>(api, `/v1/admin/maps/providers/${n(id)}/key`, { method: "PUT", body: JSON.stringify({ key }) });
export const removeMapKey = (api: MapsApi, id: string) =>
  ask<MapsAdminView>(api, `/v1/admin/maps/providers/${n(id)}/key`, { method: "DELETE" });
export const setAreas = (api: MapsApi, areas: PrefetchArea[]) =>
  ask<MapsAdminView>(api, "/v1/admin/maps/areas", { method: "PUT", body: JSON.stringify({ areas }) });
export const setSchedule = (api: MapsApi, schedule: PrefetchSchedule) =>
  ask<MapsAdminView>(api, "/v1/admin/maps/schedule", { method: "PUT", body: JSON.stringify({ schedule }) });
export const runPrefetch = (api: MapsApi) => ask<PrefetchRun[]>(api, "/v1/admin/maps/prefetch", { method: "POST" });
export const verifyMaps = (api: MapsApi) =>
  ask<{ passed: boolean; issues: { provider_id: string; check: string; detail: string }[] }>(
    api,
    "/v1/admin/geospatial/verify",
    { method: "POST" },
  );

export interface BuildOutcome {
  ok: boolean;
  lines: string[];
  /** The file built, or the reason it was not, in the Conduit's words. */
  said: string;
}

/** The build streams its progress (one `data:` line each) and ends with `event: complete`. Read
 * whole, then split, so every line the Conduit said is shown. */
export async function buildBasemap(api: MapsApi, region: string): Promise<BuildOutcome> {
  const response = await fetch(`${api.apiBaseUrl}/v1/admin/geospatial/build-basemap`, {
    method: "POST",
    headers: { Authorization: `Bearer ${api.bearerToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ region }),
  });
  if (!response.ok) throw refusal(response.status, (await response.json().catch(() => ({}))) as { detail?: unknown });
  const lines: string[] = [];
  let outcome: { returncode?: number; error?: string; result?: { pmtiles_file?: string } } = {};
  for (const block of (await response.text()).split("\n\n")) {
    const data = block.split("\n").find((l) => l.startsWith("data: "));
    if (!data) continue;
    const parsed = JSON.parse(data.slice(6)) as { line?: string } & typeof outcome;
    if (block.startsWith("event: complete")) outcome = parsed;
    else if (typeof parsed.line === "string") lines.push(parsed.line);
  }
  const ok = outcome.returncode === 0;
  return {
    ok,
    lines,
    said: ok ? `Built ${outcome.result?.pmtiles_file ?? "the basemap"}.` : `The build did not finish: ${outcome.error ?? "no answer"}`,
  };
}
