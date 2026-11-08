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

async function call<T>(api: ModelsApi, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${api.apiBaseUrl}/v1/admin/models${path}`, {
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

const engine = (name: string) => `/engines/${encodeURIComponent(name)}`;

export const readModels = (api: ModelsApi) => call<ModelsAdminView>(api, "");
export const readHistory = (api: ModelsApi) => call<ModelAdminHistory>(api, "/history");
export const addEngine = (api: ModelsApi, provider: ModelProviderConfig) =>
  call<ModelsAdminView>(api, "/engines", { method: "POST", body: JSON.stringify({ provider }) });
export const editEngine = (api: ModelsApi, provider: ModelProviderConfig) =>
  call<ModelsAdminView>(api, engine(provider.name), { method: "PUT", body: JSON.stringify({ provider }) });
export const removeEngine = (api: ModelsApi, name: string) =>
  call<ModelsAdminView>(api, engine(name), { method: "DELETE" });
export const setDefaults = (api: ModelsApi, defaults: Record<string, string>) =>
  call<ModelsAdminView>(api, "/defaults", { method: "PUT", body: JSON.stringify({ defaults }) });
/** Write-only: the key is in this request's body and nowhere else; the answer is the view. */
export const setKey = (api: ModelsApi, name: string, key: string) =>
  call<ModelsAdminView>(api, `${engine(name)}/key`, { method: "PUT", body: JSON.stringify({ key }) });
export const removeKey = (api: ModelsApi, name: string) =>
  call<ModelsAdminView>(api, `${engine(name)}/key`, { method: "DELETE" });
export const testConnection = (api: ModelsApi, name: string) =>
  call<ConnectionTestResult>(api, `${engine(name)}/test`, { method: "POST" });
