// The Admin area's calls (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): people's roles,
// dashboard identities and the system's health, all through the Conduit — never the identity
// provider directly. Shapes are the generated ones.
import type {
  AccessInput,
  AdminSchedule,
  DashboardIdentity,
  DemoPackStatus,
  InviteInput,
  PersonAccount,
  RegisteredDashboard,
  ScheduleRunView,
  SignInDelivery,
  SystemStatus,
} from "../../../../packages/schemas/generated";

export interface AdminApi {
  apiBaseUrl: string;
  bearerToken: string;
}

async function failure(response: Response): Promise<Error> {
  const body = (await response.json().catch(() => ({}))) as { error?: string; detail?: unknown };
  const detail = body.detail as { error?: string; clearance?: string; codes?: string[] } | string | undefined;
  if (typeof detail === "object" && detail?.error === "dashboard_above_your_clearance") {
    return new Error(`A dashboard cannot read above your own clearance (${detail.clearance} asked).`);
  }
  // ADR-114 Amendment 5: nobody is given more than the administrator holds.
  if (typeof detail === "object" && detail?.error === "above_your_clearance") {
    return new Error(`You cannot give a clearance above your own (${detail.clearance} asked).`);
  }
  if (typeof detail === "object" && detail?.error === "handling_code_you_do_not_hold") {
    return new Error(`You cannot give a handling code you do not hold yourself (${(detail.codes ?? []).join(", ")}).`);
  }
  if (typeof detail === "object" && detail?.error === "cannot_disable_yourself") {
    return new Error("You cannot disable your own account.");
  }
  if (body.error === "person_exists") return new Error("That sign-in name or email address is already held.");
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
// ADR-114 Amendment 5: invite, access, disable, enable, reset sign-in.
const person = (userId: string, what: string) => `people/${encodeURIComponent(userId)}/${what}`;
export const invitePerson = (api: AdminApi, invite: InviteInput) =>
  call<SignInDelivery>(api, "people", { method: "POST", body: JSON.stringify(invite) });
export const setAccess = (api: AdminApi, userId: string, access: AccessInput) =>
  call<PersonAccount>(api, person(userId, "access"), { method: "PUT", body: JSON.stringify(access) });
export const disablePerson = (api: AdminApi, userId: string) =>
  call<PersonAccount>(api, person(userId, "disable"), { method: "POST" });
export const enablePerson = (api: AdminApi, userId: string) =>
  call<PersonAccount>(api, person(userId, "enable"), { method: "POST" });
export const resetSignIn = (api: AdminApi, userId: string) =>
  call<SignInDelivery>(api, person(userId, "reset-sign-in"), { method: "POST" });
export const listDashboards = (api: AdminApi) => call<DashboardIdentity[]>(api, "dashboards");
export const registerDashboard = (api: AdminApi, name: string, clearance: string, orgUnit: string) =>
  call<RegisteredDashboard>(api, "dashboards", {
    method: "POST",
    body: JSON.stringify({ name, clearance, org_unit: orgUnit }),
  });
export const removeDashboard = (api: AdminApi, clientId: string) =>
  call<void>(api, `dashboards/${encodeURIComponent(clientId)}`, { method: "DELETE" });
export const listDemoPacks = (api: AdminApi) => call<DemoPackStatus[]>(api, "demo-packs");
export const systemStatus = (api: AdminApi) => call<SystemStatus>(api, "system");
// ADR-110 decision 8: Schedules and runs.
const schedule = (recipeId: string, what: string) => `schedules/${encodeURIComponent(recipeId)}/${what}`;
export const listSchedules = (api: AdminApi) => call<AdminSchedule[]>(api, "schedules");
export const scheduleRuns = (api: AdminApi, recipeId: string) => call<ScheduleRunView[]>(api, schedule(recipeId, "runs"));
export const pauseSchedule = (api: AdminApi, recipeId: string) =>
  call<AdminSchedule>(api, schedule(recipeId, "pause"), { method: "POST", body: JSON.stringify({}) });
export const resumeSchedule = (api: AdminApi, recipeId: string) =>
  call<AdminSchedule>(api, schedule(recipeId, "resume"), { method: "POST" });
