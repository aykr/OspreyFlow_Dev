// Admin › Models' calls (`06_DECISIONS.md` ADR-135 Amendment 2, ADR-112 Amendment 7), each behind
// `manage_models` in the Conduit. A key is sent once, in the body of its own PUT, and never comes
// back: no response carries one, and a refusal is the Conduit's own words.
import type {
  AdminEngine,
  ConnectionTestResult,
  EngineCheckResult,
  EngineLimits,
  ModelAdminHistory,
  ModelsAdminView,
  ModelUsageView,
} from "../../../../../packages/schemas/generated";

type ModelProviderConfig = AdminEngine["provider"];

export interface ModelsApi {
  apiBaseUrl: string;
  bearerToken: string;
}

/** A field the Conduit's rules refused (ADR-135 Amendment 14): `provider.api_base`,
 * `provider.roles.<job>`, `provider.label`, `provider.contract_reference` or `key`, in its words. */
export interface RefusedField {
  field: string;
  words: string;
}

/** The Conduit's refusal in its own words, with each refused field named where it names one. */
export class ModelsRefused extends Error {
  constructor(
    message: string,
    readonly fields: RefusedField[] = [],
  ) {
    super(message);
  }
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
    const detail = body.detail as { detail?: string; fields?: RefusedField[] } | undefined;
    if (typeof detail?.detail === "string") throw new ModelsRefused(detail.detail, detail.fields ?? []);
    if (response.status === 403) throw new Error("Your account does not hold the right to manage models.");
    throw new Error(`Models could not complete that (${response.status}).`);
  }
  return (await response.json()) as T;
}

const n = encodeURIComponent;

export const readModels = (api: ModelsApi) => ask<ModelsAdminView>(api, "/v1/admin/models");
export const readHistory = (api: ModelsApi) => ask<ModelAdminHistory>(api, "/v1/admin/models/history");
/** The owner's ruling 19: a changed model name, address or key is checked before it is saved; a
 * changed address takes its key with it, in this request's body and nowhere else. */
export const editEngine = (api: ModelsApi, provider: ModelProviderConfig, key?: string) =>
  ask<ModelsAdminView>(api, `/v1/admin/models/engines/${n(provider.name)}`, {
    method: "PUT",
    body: JSON.stringify(key ? { provider, key } : { provider }),
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
/** ADR-135 Amendment 3: an engine's limits, applied by the gateway to the engine's own key. */
export const setLimits = (api: ModelsApi, name: string, limits: EngineLimits) =>
  ask<ModelsAdminView>(api, `/v1/admin/models/engines/${n(name)}/limits`, { method: "PUT", body: JSON.stringify({ limits }) });
/** ADR-135 Amendment 3: the gateway's own records over whole UTC days, as counts only. */
export const readUsage = (api: ModelsApi, start: string, end: string) =>
  ask<ModelUsageView>(api, `/v1/admin/models/usage?start=${n(start)}&end=${n(end)}`);
/** ADR-135 Amendment 14: the key and each typed model proved by one call in the gateway before the
 * engine exists. The key is in this request's body alone, where the engine has one; the answer is
 * the outcome in fixed words, never the key. */
export const checkEngine = (api: ModelsApi, provider: ModelProviderConfig, key: string | null) =>
  ask<EngineCheckResult>(api, "/v1/admin/models/checks", {
    method: "POST",
    body: JSON.stringify(key === null ? { provider } : { provider, key }),
  });
/** **Add** names the passed check, never the key. */
export const addChecked = (api: ModelsApi, check: string) =>
  ask<ModelsAdminView>(api, `/v1/admin/models/checks/${n(check)}/add`, { method: "POST" });
export const cancelCheck = (api: ModelsApi, check: string) =>
  ask<ModelsAdminView>(api, `/v1/admin/models/checks/${n(check)}`, { method: "DELETE" });
