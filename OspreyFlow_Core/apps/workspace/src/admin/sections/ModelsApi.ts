// Admin › Models' calls (`06_DECISIONS.md` ADR-135 Amendment 2, ADR-112 Amendment 7), each behind
// `manage_models` in the Conduit. A key is sent once, in the body of its own PUT, and never comes
// back: no response carries one, and a refusal is the Conduit's own words.
import type {
  AdminEngine,
  ConnectionTestResult,
  ModelAdminHistory,
  ModelsAdminView,
} from "../../../../../packages/schemas/generated";

type ModelProviderConfig = AdminEngine["provider"];

export interface ModelsApi {
  apiBaseUrl: string;
  bearerToken: string;
}

/** One call to the Conduit; `path` is written out whole at each call site (`/v1/admin/models…`), so
 * the place and section scans read every route this screen uses. */
async function ask<T>(api: ModelsApi, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${api.apiBaseUrl}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${api.bearerToken}`, "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    const detail = body.detail as { detail?: string } | undefined;
    if (typeof detail?.detail === "string") throw new Error(detail.detail);
    if (response.status === 403) throw new Error("Your account does not hold the right to manage models.");
    throw new Error(`Models could not complete that (${response.status}).`);
  }
  return (await response.json()) as T;
}

const n = encodeURIComponent;

export const readModels = (api: ModelsApi) => ask<ModelsAdminView>(api, "/v1/admin/models");
export const readHistory = (api: ModelsApi) => ask<ModelAdminHistory>(api, "/v1/admin/models/history");
export const addEngine = (api: ModelsApi, provider: ModelProviderConfig) =>
  ask<ModelsAdminView>(api, "/v1/admin/models/engines", { method: "POST", body: JSON.stringify({ provider }) });
export const editEngine = (api: ModelsApi, provider: ModelProviderConfig) =>
  ask<ModelsAdminView>(api, `/v1/admin/models/engines/${n(provider.name)}`, {
    method: "PUT",
    body: JSON.stringify({ provider }),
  });
export const removeEngine = (api: ModelsApi, name: string) =>
  ask<ModelsAdminView>(api, `/v1/admin/models/engines/${n(name)}`, { method: "DELETE" });
export const setDefaults = (api: ModelsApi, defaults: Record<string, string>) =>
  ask<ModelsAdminView>(api, "/v1/admin/models/defaults", { method: "PUT", body: JSON.stringify({ defaults }) });
/** Write-only: the key is in this request's body and nowhere else; the answer is the view. */
export const setKey = (api: ModelsApi, name: string, key: string) =>
  ask<ModelsAdminView>(api, `/v1/admin/models/engines/${n(name)}/key`, { method: "PUT", body: JSON.stringify({ key }) });
export const removeKey = (api: ModelsApi, name: string) =>
  ask<ModelsAdminView>(api, `/v1/admin/models/engines/${n(name)}/key`, { method: "DELETE" });
export const testConnection = (api: ModelsApi, name: string) =>
  ask<ConnectionTestResult>(api, `/v1/admin/models/engines/${n(name)}/test`, { method: "POST" });
