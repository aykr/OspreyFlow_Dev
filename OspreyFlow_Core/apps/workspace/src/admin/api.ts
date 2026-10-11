// The Admin area's calls (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): people's roles,
// dashboard identities and the system's health, all through the Conduit — never the identity
// provider directly. Shapes are the generated ones.
import type {
  DashboardIdentity,
  PersonAccount,
  RegisteredDashboard,
  SystemStatus,
} from "../../../../packages/schemas/generated";

export interface AdminApi {
  apiBaseUrl: string;
  bearerToken: string;
}

async function failure(response: Response): Promise<Error> {
  const body = (await response.json().catch(() => ({}))) as { error?: string; detail?: unknown };
  const detail = body.detail as { error?: string; clearance?: string } | string | undefined;
  if (typeof detail === "object" && detail?.error === "dashboard_above_your_clearance") {
    return new Error(`A dashboard cannot read above your own clearance (${detail.clearance} asked).`);
  }
  if (body.error === "dashboard_exists") return new Error("A dashboard of that name is already registered.");
  if (body.error === "not_allowed" && typeof detail === "string") return new Error(detail);
  if (body.error === "identity_provider_refused" && typeof detail === "string") return new Error(detail);
  if (response.status === 403) return new Error("Your account does not hold the right for this.");
  return new Error(`The Admin area could not complete that (${response.status}).`);
}

async function call<T>(api: AdminApi, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${api.apiBaseUrl}/v1/admin/${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${api.bearerToken}`, "Content-Type": "application/json" },
  });
  if (!response.ok) throw await failure(response);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const listPeople = (api: AdminApi) => call<PersonAccount[]>(api, "people");
export const setRoles = (api: AdminApi, userId: string, roles: string[]) =>
  call<PersonAccount>(api, `people/${encodeURIComponent(userId)}/roles`, { method: "PUT", body: JSON.stringify({ roles }) });
export const listDashboards = (api: AdminApi) => call<DashboardIdentity[]>(api, "dashboards");
export const registerDashboard = (api: AdminApi, name: string, clearance: string, orgUnit: string) =>
  call<RegisteredDashboard>(api, "dashboards", {
    method: "POST",
    body: JSON.stringify({ name, clearance, org_unit: orgUnit }),
  });
export const removeDashboard = (api: AdminApi, clientId: string) =>
  call<void>(api, `dashboards/${encodeURIComponent(clientId)}`, { method: "DELETE" });
export const systemStatus = (api: AdminApi) => call<SystemStatus>(api, "system");
