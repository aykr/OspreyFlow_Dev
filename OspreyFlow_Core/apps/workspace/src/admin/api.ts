// The Admin area's calls (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): people's roles,
// dashboard identities and the system's health, all through the Conduit — never the identity
// provider directly. Shapes are the generated ones.
import type {
  AccessInput,
  AdminDataset,
  AdminDatasetAuthors,
  AdminDatasetCases,
  AdminSchedule,
  DashboardIdentity,
  DatasetOwnerSetting,
  DemoPackStatus,
  InviteInput,
  LayerDryRun,
  OrganisationArrival,
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
  // ADR-112 Amendment 3: removing and joining people, refused in the Conduit's words.
  if (typeof detail === "object" && detail?.error === "cannot_remove_yourself") {
    return new Error("You cannot remove your own account.");
  }
  // ADR-110 Amendment 3: Run now and Change schedule, refused in the Conduit's words.
  if (body.error === "run_refused" && typeof detail === "string") return new Error(`Not run: ${detail}`);
  if (body.error === "schedule_refused" && typeof detail === "string") return new Error(detail);
  if (body.error === "person_exists") return new Error("That sign-in name or email address is already held.");
  if (body.error === "dashboard_exists") return new Error("A dashboard of that name is already registered.");
  if (body.error === "not_allowed" && typeof detail === "string") return new Error(detail);
  if (body.error === "identity_provider_refused" && typeof detail === "string") return new Error(detail);
  if (body.error === "dataset_not_found") return new Error("That dataset is no longer there.");
  // ADR-143 Amendment 2 decision 1, ADR-145 Amendment 4: a dry run or a change of owner, refused in
  // the Conduit's words, which say why and who can.
  if (
    typeof detail === "string" &&
    ["not_an_author", "case_open", "case_not_linked", "composite_read_only", "owner_needed"].includes(body.error ?? "")
  )
    return new Error(detail);
  if (response.status === 409 && typeof body.error === "string" && typeof detail === "string") return new Error(detail);
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
// ADR-112 Amendment 3: a person's account removed from the identity provider.
export const removePerson = (api: AdminApi, userId: string) =>
  call<PersonAccount>(api, `people/${encodeURIComponent(userId)}`, { method: "DELETE" });
// ADR-112 Amendment 3 (b): the organisation's refused arrivals, and joining one to an account.
export const listArrivals = (api: AdminApi) => call<OrganisationArrival[]>(api, "organisation-arrivals");
export const linkOrganisation = (api: AdminApi, userId: string, subject: string) =>
  call<PersonAccount>(api, person(userId, "organisation-link"), { method: "POST", body: JSON.stringify({ subject }) });
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
// ADR-136 decision 2: each dataset's egress, set by an administrator, audited by the Conduit.
export const listDatasets = (api: AdminApi) => call<AdminDataset[]>(api, "datasets");
export const setDatasetEgress = (api: AdminApi, datasetId: string, egress: AdminDataset["egress"]) =>
  call<AdminDataset>(api, `datasets/${encodeURIComponent(datasetId)}/egress`, {
    method: "PUT",
    body: JSON.stringify({ egress }),
  });
// ADR-145 decision 8 and Amendment 4 decision 6: Admin › Datasets' policy, Authors, linked cases and
// a removed case's dry runs; decision 7: Admin › System's *Dataset owners may be*.
const dataset = (datasetId: string, what: string) => `datasets/${encodeURIComponent(datasetId)}/${what}`;
export const setPromotionPolicy = (api: AdminApi, datasetId: string, policy: AdminDataset["promotion_policy"]) =>
  call<AdminDataset>(api, dataset(datasetId, "promotion-policy"), {
    method: "PUT",
    body: JSON.stringify({ promotion_policy: policy }),
  });
export const datasetAuthors = (api: AdminApi, datasetId: string) =>
  call<AdminDatasetAuthors>(api, dataset(datasetId, "authors"));
export const changeDatasetOwners = (api: AdminApi, datasetId: string, people: string[]) =>
  call<AdminDatasetAuthors>(api, dataset(datasetId, "owners"), { method: "PUT", body: JSON.stringify({ people }) });
export const datasetCases = (api: AdminApi, datasetId: string) =>
  call<AdminDatasetCases>(api, dataset(datasetId, "cases"));
export const layerDryRun = (api: AdminApi, datasetId: string, caseId: string, action: LayerDryRun["action"]) =>
  call<LayerDryRun>(api, `datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}/${action}/dry-run`, {
    method: "POST",
  });
export const datasetOwnerSetting = (api: AdminApi) => call<DatasetOwnerSetting>(api, "settings/dataset-owners");
export const setDatasetOwnerSetting = (api: AdminApi, value: DatasetOwnerSetting["owners_may_be"]) =>
  call<DatasetOwnerSetting>(api, "settings/dataset-owners", {
    method: "PUT",
    body: JSON.stringify({ owners_may_be: value }),
  });
// ADR-110 decision 8: Schedules and runs.
const schedule = (recipeId: string, what: string) => `schedules/${encodeURIComponent(recipeId)}/${what}`;
export const listSchedules = (api: AdminApi) => call<AdminSchedule[]>(api, "schedules");
export const scheduleRuns = (api: AdminApi, recipeId: string) => call<ScheduleRunView[]>(api, schedule(recipeId, "runs"));
export const pauseSchedule = (api: AdminApi, recipeId: string) =>
  call<AdminSchedule>(api, schedule(recipeId, "pause"), { method: "POST", body: JSON.stringify({}) });
export const resumeSchedule = (api: AdminApi, recipeId: string) =>
  call<AdminSchedule>(api, schedule(recipeId, "resume"), { method: "POST" });
export const runScheduleNow = (api: AdminApi, recipeId: string) =>
  call<AdminSchedule>(api, schedule(recipeId, "run"), { method: "POST" });
export const changeSchedule = (api: AdminApi, recipeId: string, cron: string, timezone: string) =>
  call<AdminSchedule>(api, `schedules/${encodeURIComponent(recipeId)}`, {
    method: "PUT",
    body: JSON.stringify({ cron, timezone }),
  });
