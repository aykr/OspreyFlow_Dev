// The Admin area's calls (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): people's roles,
// dashboard identities and the system's health, all through the Conduit — never the identity
// provider directly. Shapes are the generated ones.
import { rightName, rolesHolding, whyNotByRole, type Right } from "../help/roles";
import type {
  PersonAccessInput,
  AdminPeopleRows,
  AuditSectionPage,
  ConnectionTest,
  OperationsAgeing,
  PromotionAlertSetting,
  CustomRole,
  CustomRoleVersion,
  DisablePlan,
  OwnedTransfer,
  RolesCatalogue,
  Team,
  AdminDataset,
  AdminDatasetAuthors,
  AdminDatasetCases,
  AdminSchedule,
  DashboardIdentity,
  DatasetOwnerSetting,
  DemoPackStatus,
  InviteInput,
  LayerDeleted,
  LayerDryRun,
  OrganisationArrival,
  PersonAccount,
  PersonOwnership,
  RegisteredDashboard,
  ScheduleRunView,
  SignInDelivery,
  SignInKind,
  GuestSignIn,
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
  // ADR-148 Amendment 15: the people store's own refusal of a setter it holds nothing for, or disabled.
  if (typeof detail === "object" && detail?.error === "setter_cannot_set") {
    return new Error("You cannot set anyone's access until your own is set here, and while your account is enabled.");
  }
  // ADR-148 Amendment 15: a person no longer recorded here (removed since People was read).
  if (body.error === "no_such_person") return new Error("That person is no longer in People here: refresh the list.");
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
  // ADR-145 decision 10: Audit's filters refused in the Conduit's words.
  if (body.error === "audit_filters" && typeof detail === "string") return new Error(`Not read: ${detail}.`);
  // ADR-143 Amendment 2 decision 1, ADR-145 Amendment 4: a dry run or a change of owner, refused in
  // the Conduit's words, which say why and who can.
  if (
    typeof detail === "string" &&
    ["not_an_author", "case_open", "case_not_linked", "composite_read_only", "owner_needed", "no_layer"].includes(
      body.error ?? "",
    )
  ) {
    // ADR-145 Amendment 4 decision 12 (L2.5c): a refusal carrying a right says the roles that
    // hold it, never the people; the block is the Author level, so it is not told to ask for it.
    const right = (body as { right?: unknown }).right;
    return new Error(typeof right === "string" ? `${detail} ${authorAlsoNeeds(right as Right)}` : detail);
  }
  if (response.status === 409 && typeof body.error === "string" && typeof detail === "string") return new Error(detail);
  // ADR-145 Amendment 5: roles, teams, case levels and Disable…, refused in the Conduit's words.
  if (typeof detail === "object" && detail !== null && typeof (detail as { message?: unknown }).message === "string")
    return new Error((detail as { message: string }).message);
  // ADR-145 Amendment 4 decision 12 (L2.7): a right refused says which roles hold it, never who.
  if (typeof detail === "object" && detail !== null && (detail as { error?: string }).error === "right_required") {
    const right = (detail as { right?: unknown }).right;
    if (typeof right === "string") return new Error(`Not done. ${whyNotByRole(right as Right)}`);
  }
  if (response.status === 403) return new Error("Your account does not hold the right for this.");
  return new Error(`The Admin area could not complete that (${response.status}).`);
}

/** What an Author also needs, by the roles that hold it, never the people (decision 12). */
export function authorAlsoNeeds(right: Right): string {
  const roles = rolesHolding(right);
  if (roles.length === 0) return `An Author also needs ${rightName(right)}, which no built-in role has.`;
  const named = roles.length === 1 ? `the ${roles[0]!} role has` : `the ${roles.slice(0, -1).join(", ")} and ${roles.at(-1)!} roles have`;
  return `An Author also needs ${rightName(right)}, which ${named}.`;
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
// ADR-148 Amendment 8: on Entra ID sign-in, Entra holds the accounts; a person is added by object id.
export const signInKind = (api: AdminApi) => call<SignInKind>(api, "sign-in");
// ADR-148 Amendment 17: whether guest (B2B) accounts are admitted, and switching it (manage_people).
export const guestSignIn = (api: AdminApi) => call<GuestSignIn>(api, "sign-in/guests");
export const setGuestSignIn = (api: AdminApi, admitted: boolean) =>
  call<GuestSignIn>(api, "sign-in/guests", { method: "PUT", body: JSON.stringify({ admitted }) });
// ADR-148 Amendment 10: Admin › Dashboards' own copy, behind manage_dashboards.
export const dashboardsSignInKind = (api: AdminApi) => call<SignInKind>(api, "dashboards/sign-in");
export const addPersonByObjectId = (api: AdminApi, objectId: string) =>
  call<PersonAccount>(api, "people/by-object-id", { method: "POST", body: JSON.stringify({ object_id: objectId }) });
export const setAccess = (api: AdminApi, userId: string, access: PersonAccessInput) =>
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
export const registerDashboard = (api: AdminApi, name: string, clearance: string, orgUnit: string, applicationId?: string) =>
  call<RegisteredDashboard>(api, "dashboards", {
    method: "POST",
    // ADR-148 Amendment 10: on Entra ID, the dashboard's own app registration's application id.
    body: JSON.stringify({ name, clearance, org_unit: orgUnit, ...(applicationId ? { application_id: applicationId } : {}) }),
  });
export const removeDashboard = (api: AdminApi, clientId: string) =>
  call<void>(api, `dashboards/${encodeURIComponent(clientId)}`, { method: "DELETE" });
export const listDemoPacks = (api: AdminApi) => call<DemoPackStatus[]>(api, "demo-packs");
export const systemStatus = (api: AdminApi) => call<SystemStatus>(api, "system");
// ADR-136 decision 2: each dataset's egress, set by an administrator, audited by the Conduit.
export const listDatasets = (api: AdminApi) => call<AdminDataset[]>(api, "datasets");
// ADR-140 Amendment 13 (L2.7): *Test connection*, in words; nothing read is answered.
export const testConnection = (api: AdminApi, connectionId: string) =>
  call<ConnectionTest>(api, `connections/${encodeURIComponent(connectionId)}/test`, { method: "POST" });
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
// ADR-143 Amendment 5 (L2.5c): Admin's own Delete of a removed case's layer, after its dry run; for
// a dataset of the administrator's own unit, any other answered as no dataset.
export const deleteRemovedLayer = (api: AdminApi, datasetId: string, caseId: string) =>
  call<LayerDeleted>(api, `datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}/delete`, {
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

// ADR-145 decisions 6 and 7 and Amendment 5: roles, teams, the People rows and Disable….
export const listRoles = (api: AdminApi) => call<RolesCatalogue>(api, "roles");
export const createRole = (api: AdminApi, name: string, rights: string[]) =>
  call<CustomRole>(api, "roles", { method: "POST", body: JSON.stringify({ name, rights }) });
export const changeRole = (api: AdminApi, roleId: string, name: string, rights: string[]) =>
  call<CustomRole>(api, `roles/${encodeURIComponent(roleId)}`, { method: "PUT", body: JSON.stringify({ name, rights }) });
export const makeTeam = (api: AdminApi, roleId: string, displayName: string, mailbox: string) =>
  call<Team>(api, `roles/${encodeURIComponent(roleId)}/team`, {
    method: "PUT",
    body: JSON.stringify({ display_name: displayName, mailbox }),
  });
export const setTeamLead = (api: AdminApi, roleId: string, lead: string) =>
  call<Team>(api, `teams/${encodeURIComponent(roleId)}/lead`, { method: "PUT", body: JSON.stringify({ lead }) });
export const setTeamCover = (api: AdminApi, roleId: string, cover: string | null, until: string | null) =>
  call<Team>(api, `teams/${encodeURIComponent(roleId)}/cover`, { method: "PUT", body: JSON.stringify({ cover, until }) });
export const peopleRows = (api: AdminApi) => call<AdminPeopleRows>(api, "people/rows");
export const disablePlan = (api: AdminApi, userId: string) => call<DisablePlan>(api, person(userId, "disable-plan"));
// ADR-145 Amendment 8 (L3.8, read by L2.5b): whether the person owns items this administrator may
// not see, said and never named; the items themselves come in the plan.
export const personOwnership = (api: AdminApi, userId: string) =>
  call<PersonOwnership>(api, person(userId, "ownership"));
export const transferAndDisable = (api: AdminApi, userId: string, transfers: OwnedTransfer[]) =>
  call<PersonAccount>(api, person(userId, "disable"), { method: "POST", body: JSON.stringify({ transfers }) });

/** *Name an Author* (R1): a case of your unit with no Author is given one (ADR-145 Amendment 5). */
export const nameAnAuthor = (api: AdminApi, caseId: string, account: string) =>
  call<void>(api, `cases/${encodeURIComponent(caseId)}/authors/${encodeURIComponent(account)}`, { method: "PUT" });
export const roleVersions = (api: AdminApi, roleId: string) =>
  call<CustomRoleVersion[]>(api, `roles/${encodeURIComponent(roleId)}/versions`);

/** Admin › Audit's filters (ADR-145 decision 10): each narrows what the Conduit reads as you. */
export interface AuditQuery {
  held_in: "case_and_admin" | "rules" | "models";
  kind?: string;
  who?: string;
  case?: string;
  dataset?: string;
  since?: string;
  until?: string;
  offset?: number;
  limit?: number;
}
/** Each record its own route, each declaring its rights: the stream (`read_audit`), a case's rule
 * audit (and `read_rule_audit`, for the Administrator), the engines' history (and `manage_models`). */
export const readAudit = (api: AdminApi, query: AuditQuery) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query))
    if (key !== "held_in" && value !== undefined && value !== "") params.set(key, String(value));
  const q = params.toString();
  if (query.held_in === "rules") return call<AuditSectionPage>(api, `audit/rules?${q}`);
  if (query.held_in === "models") return call<AuditSectionPage>(api, `audit/models?${q}`);
  return call<AuditSectionPage>(api, `audit?${q}`);
};
/** Operations' ageing (ADR-145 decision 9): what ages and when, and the promotions waiting. */
export const operationsAgeing = (api: AdminApi) => call<OperationsAgeing>(api, "operations/ageing");
export const setPromotionAlertDays = (api: AdminApi, days: number) =>
  call<PromotionAlertSetting>(api, "settings/promotion-alert-days", {
    method: "PUT",
    body: JSON.stringify({ alert_after_days: days }),
  });
