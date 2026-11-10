// The Alerts place's calls (`06_DECISIONS.md` ADR-109 phases A and B; `03_CONDUIT_MIDDLEWARE.md`
// §3.8a): the case team's alert queue and an alert's explanation, the triage actions, the case's
// typology rules, their audit, and the rows a failing pre-commit rule held. Every shape is the
// generated one, so a change on the server is a type error here, never a silent drift.
import type {
  Alert,
  AlertAssignee,
  AlertAtAddress,
  AlertDispositionInput,
  AlertExplanation,
  AlertSources,
  AlertSuppressInput,
  AlertTeam,
  CompiledSentence,
  HeldRow,
  ListSchedule,
  OntologySchema,
  PatternQuery,
  RulePreview,
  RuleSentence,
  QueuedAlert,
  RaiseAlertInput,
  RuleAuditPage,
  RuleScheduleView,
  RuleVersion,
  ScreeningLists,
  ScreeningListsOverview,
  ScreeningListStatus,
  ScreeningListUpdate,
  ScreeningSubscriptionInput,
  TypologyRule,
  TypologyRuleInput,
} from "../../../../packages/schemas/generated";
import type { WorkingSetDelta } from "../workingset/models";

export type QueueFilter = "active" | "closed" | "all";
export type KindFilter = "all" | "typology" | "hotlist" | "monitor" | "analyst";
/** ADR-146 decision 2: the queue's filters; *All* holds the suppressed alerts too (Amendment 1). */
export type QueueShow = "mine" | "team" | "unassigned" | "all";
export type SeverityFilter = "all" | "high" | "medium" | "low";

/** ADR-133 stage (a): what the queue is asked for. The server filters; the Glass never hides a row
 * it was sent. */
export interface QueueQuery {
  status: QueueFilter;
  kind?: KindFilter;
  severity?: SeverityFilter;
  show?: QueueShow;
  /** *Older than N days*: only those raised more than this many days ago. */
  olderThanDays?: number | null;
}

export function queueSearch(query: QueueQuery): string {
  const params = new URLSearchParams({ status: query.status });
  if (query.kind && query.kind !== "all") params.append("kind", query.kind);
  if (query.severity && query.severity !== "all") params.append("severity", query.severity);
  // *All* is the server's default, suppressed alerts included (ADR-146 Amendment 1).
  if (query.show && query.show !== "all") params.append("show", query.show);
  if (query.olderThanDays) params.append("older_than_days", String(query.olderThanDays));
  return params.toString();
}

export interface CanvasOutcome {
  delta: WorkingSetDelta;
  added_nodes: number;
  added_links: number;
}

function caseUrl(apiBaseUrl: string, investigationId: string, path: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/${path}`;
}

/** Says, in words, why a call was refused — never a bare status. */
async function failure(response: Response, what: string): Promise<Error> {
  const body = (await response.json().catch(() => ({}))) as {
    error?: string;
    detail?: unknown;
    would_be?: number;
    cap?: number;
    cap_kind?: string;
  };
  const fmt = new Intl.NumberFormat("en-GB");
  if (body.error === "alert_moved_on") {
    return new Error("Someone else has already claimed or closed this alert.");
  }
  if (body.error === "limit_exceeded" && what !== "Previewing the rule") {
    return new Error(
      `Too many for the canvas: ${fmt.format(body.would_be ?? 0)} ${body.cap_kind ?? "nodes"} against a limit of ${fmt.format(body.cap ?? 0)}.`,
    );
  }
  if (body.error === "sentence_refused" && typeof body.detail === "string") {
    // ADR-133 decision 1: the server names the blank and says why, in words.
    return new Error(`${body.detail[0]?.toUpperCase() ?? ""}${body.detail.slice(1)}.`);
  }
  if (body.error === "limit_exceeded" && what === "Previewing the rule") {
    return new Error(
      `Too many to preview: the rule's subjects number ${fmt.format(body.would_be ?? 0)}, past the limit of ${fmt.format(body.cap ?? 0)}. Nothing was counted; narrow the sentence and preview again.`,
    );
  }
  // ADR-133 decision 7: the server says, in words, why a second person is needed.
  const own = body.detail as { error?: unknown; message?: unknown } | undefined;
  if (own && typeof own === "object" && own.error === "own_change" && typeof own.message === "string") {
    return new Error(own.message);
  }
  const refusal = body as { error?: string; message?: unknown };
  if (refusal.error === "rule_change_refused" && typeof refusal.message === "string") {
    return new Error(refusal.message);
  }
  if ((body.error === "assignment_refused" || body.error === "suppress_refused") && typeof body.detail === "string") {
    return new Error(body.detail);
  }
  // ADR-146 decision 7: *Raise an alert…* refused in words, naming only what was asked for.
  const raised = body.detail as { code?: unknown; message?: unknown } | undefined;
  if (raised && typeof raised === "object" && typeof raised.code === "string" && typeof raised.message === "string") {
    return new Error(raised.message);
  }
  if (body.error === "release_refused" && typeof body.detail === "string") {
    return new Error(`${body.detail[0]?.toUpperCase() ?? ""}${body.detail.slice(1)}.`);
  }
  // ADR-133 stage (c): a screening list refused or not found, in the server's own words.
  const said = body.detail as { message?: unknown; right?: unknown } | undefined;
  if (said && typeof said === "object" && typeof said.message === "string") {
    return new Error(`${said.message[0]?.toUpperCase() ?? ""}${said.message.slice(1)}.`);
  }
  if (response.status === 403 && said?.right === "load_screening_lists") {
    return new Error(`${what} needs the right to load screening lists.`);
  }
  if (response.status === 403) return new Error(`${what} needs a higher level in this case.`);
  if (response.status === 404) return new Error(`${what}: not found, or not yours to see.`);
  if (response.status === 422) return new Error(`${what}: some of what was entered was refused.`);
  return new Error(`${what} failed (${response.status}).`);
}

async function call<T>(
  url: string,
  bearerToken: string,
  what: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: init.method ?? "GET",
      headers: {
        Authorization: `Bearer ${bearerToken}`,
        ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    throw new Error("The server could not be reached.");
  }
  if (!response.ok) throw await failure(response, what);
  return (await response.json()) as T;
}

export interface AlertsApi {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
}

export const listQueue = (a: AlertsApi, query: QueueFilter | QueueQuery) => {
  // The search on its own line keeps the path one plain template, which the Conduit's place test
  // reads as Rules and Monitoring's entry read (`test_place_routes.py`).
  const search = queueSearch(typeof query === "string" ? { status: query } : query);
  return call<QueuedAlert[]>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue?${search}`), a.bearerToken, "Reading the alert queue");
};

export const listAssignees = (a: AlertsApi) =>
  call<AlertAssignee[]>(caseUrl(a.apiBaseUrl, a.investigationId, "alert-assignees"), a.bearerToken, "Reading who alerts may be given to");

export const assignAlert = (a: AlertsApi, alertId: string, assignee: string) =>
  call<Alert>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue/${encodeURIComponent(alertId)}/assign`), a.bearerToken, "Giving the alert", { method: "POST", body: { assignee } });

export const explainAlert = (a: AlertsApi, alertId: string) =>
  call<AlertExplanation>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue/${encodeURIComponent(alertId)}`), a.bearerToken, "Opening the alert");

export const claimAlert = (a: AlertsApi, alertId: string) =>
  call<Alert>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue/${encodeURIComponent(alertId)}/claim`), a.bearerToken, "Claiming the alert", { method: "POST" });

export const releaseAlert = (a: AlertsApi, alertId: string) =>
  call<Alert>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue/${encodeURIComponent(alertId)}/release`), a.bearerToken, "Releasing the alert", { method: "POST" });

export const disposeAlert = (a: AlertsApi, alertId: string, body: AlertDispositionInput) =>
  call<Alert>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue/${encodeURIComponent(alertId)}/disposition`), a.bearerToken, "Closing the alert", { method: "POST", body });

export const alertToCanvas = (a: AlertsApi, alertId: string) =>
  call<CanvasOutcome>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue/${encodeURIComponent(alertId)}/canvas`), a.bearerToken, "Opening the alert on the canvas", { method: "POST" });

export const listRules = (a: AlertsApi) =>
  call<TypologyRule[]>(caseUrl(a.apiBaseUrl, a.investigationId, "rules"), a.bearerToken, "Reading the rules");

export const deployRule = (a: AlertsApi, body: TypologyRuleInput) =>
  call<TypologyRule>(caseUrl(a.apiBaseUrl, a.investigationId, "rules"), a.bearerToken, "Deploying the rule", { method: "POST", body });

export const retireRule = (a: AlertsApi, ruleId: string) =>
  call<TypologyRule>(caseUrl(a.apiBaseUrl, a.investigationId, `rules/${encodeURIComponent(ruleId)}/retire`), a.bearerToken, "Retiring the rule", { method: "POST" });

export const readRuleAudit = (a: AlertsApi, offset: number, limit = 50) =>
  call<RuleAuditPage>(caseUrl(a.apiBaseUrl, a.investigationId, `rules/audit?offset=${offset}&limit=${limit}`), a.bearerToken, "Reading the rule audit");

export const listHeldRows = (a: AlertsApi) =>
  call<HeldRow[]>(caseUrl(a.apiBaseUrl, a.investigationId, "held-rows"), a.bearerToken, "Reading the held rows");

export const rejectHeldRows = (a: AlertsApi, ids: string[], reason: string) =>
  call<HeldRow[]>(caseUrl(a.apiBaseUrl, a.investigationId, "held-rows/reject"), a.bearerToken, "Rejecting the rows", { method: "POST", body: { ids, reason } });

export const releaseHeldRows = (a: AlertsApi, recipeId: string, ids: string[], reason: string | null) =>
  call<{ edges_created: number; nodes_created: number; rule_notes: string[]; withheld?: boolean }>(
    caseUrl(a.apiBaseUrl, a.investigationId, `ingest/recipes/${encodeURIComponent(recipeId)}/held-rows/release`),
    a.bearerToken,
    "Releasing the rows",
    { method: "POST", body: { ids, reason } },
  );

// --- rules written as sentences (ADR-133 decisions 1 and 3, stage (b)) ---------------------------

export const readOntology = (a: AlertsApi) =>
  call<OntologySchema>(`${a.apiBaseUrl}/v1/ontology`, a.bearerToken, "Reading the ontology");

export const compileSentence = (a: AlertsApi, sentence: RuleSentence) =>
  call<CompiledSentence>(caseUrl(a.apiBaseUrl, a.investigationId, "rules/sentence/compile"), a.bearerToken, "Checking the sentence", { method: "POST", body: sentence });

export const readSentence = (a: AlertsApi, pattern: PatternQuery, sentence: RuleSentence) =>
  call<RuleSentence>(caseUrl(a.apiBaseUrl, a.investigationId, "rules/sentence/read"), a.bearerToken, "Reading the pattern as a sentence", { method: "POST", body: { pattern, sentence } });

export const previewRule = (a: AlertsApi, sentence: RuleSentence) =>
  call<RulePreview>(caseUrl(a.apiBaseUrl, a.investigationId, "rules/preview"), a.bearerToken, "Previewing the rule", { method: "POST", body: { sentence } });

export const deploySentence = (a: AlertsApi, name: string, sentence: RuleSentence) =>
  call<TypologyRule>(caseUrl(a.apiBaseUrl, a.investigationId, "rules/sentence"), a.bearerToken, "Deploying the rule", { method: "POST", body: { name, sentence } });

// --- screening lists as managed sources (ADR-133 decision 4, stage (c)) ---------------------------

export interface ListsApi {
  apiBaseUrl: string;
  bearerToken: string;
}

/** The Lists screen: whoever may load lists reads the refreshes too; anyone else the lists alone. */
/** The lists alone, for a reader of the alert queue: no refreshes (rule 7). */
export const listScreeningLists = (a: ListsApi) =>
  call<ScreeningListsOverview>(`${a.apiBaseUrl}/v1/screening-lists`, a.bearerToken, "Reading the screening lists");

/** The lists and their latest refreshes, for whoever holds `load_screening_lists`. */
export const manageScreeningLists = (a: ListsApi) =>
  call<ScreeningLists>(`${a.apiBaseUrl}/v1/admin/screening-lists`, a.bearerToken, "Reading the screening lists");

export const subscribeScreeningList = (a: ListsApi, body: ScreeningSubscriptionInput) =>
  call<ScreeningListStatus>(`${a.apiBaseUrl}/v1/admin/screening-lists`, a.bearerToken, "Subscribing to the list", {
    method: "POST",
    body,
  });

export const refreshScreeningList = (a: ListsApi, listName: string) =>
  call<ScreeningListUpdate>(
    `${a.apiBaseUrl}/v1/admin/screening-lists/${encodeURIComponent(listName)}/refresh`,
    a.bearerToken,
    "Refreshing the list",
    { method: "POST" },
  );

// --- stage (d): maker–checker and the scheduled trigger (ADR-133 decisions 1 and 7) --------------

export const approveRule = (a: AlertsApi, ruleId: string) =>
  call<TypologyRule>(caseUrl(a.apiBaseUrl, a.investigationId, `rules/${encodeURIComponent(ruleId)}/approve`), a.bearerToken, "Approving the change", { method: "POST" });

export const rejectRule = (a: AlertsApi, ruleId: string, reason: string) =>
  call<TypologyRule>(caseUrl(a.apiBaseUrl, a.investigationId, `rules/${encodeURIComponent(ruleId)}/reject`), a.bearerToken, "Rejecting the change", { method: "POST", body: { reason } });

export const ruleVersions = (a: AlertsApi, ruleId: string) =>
  call<RuleVersion[]>(caseUrl(a.apiBaseUrl, a.investigationId, `rules/${encodeURIComponent(ruleId)}/versions`), a.bearerToken, "Reading the rule's versions");

export const ruleRuns = (a: AlertsApi, ruleId: string) =>
  call<RuleScheduleView>(caseUrl(a.apiBaseUrl, a.investigationId, `rules/${encodeURIComponent(ruleId)}/runs`), a.bearerToken, "Reading the rule's schedule");

export const approveClose = (a: AlertsApi, alertId: string) =>
  call<Alert>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue/${encodeURIComponent(alertId)}/approve-close`), a.bearerToken, "Approving the close", { method: "POST" });

/** ADR-146 Amendment 1: *Suppress until…*, the team lead's. */
export const suppressAlert = (a: AlertsApi, alertId: string, body: AlertSuppressInput) =>
  call<Alert>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue/${encodeURIComponent(alertId)}/suppress`), a.bearerToken, "Suppressing the alert", {
    method: "POST",
    body,
  });

/** ADR-146 decision 8: the teams a rule's alerts may go to; to a team's lead, its members here. */
export const listAlertTeams = (a: AlertsApi) => call<AlertTeam[]>(caseUrl(a.apiBaseUrl, a.investigationId, "alert-teams"), a.bearerToken, "Listing the teams");

/** ADR-146 decision 5: *What raises alerts*. */
export const listAlertSources = (a: AlertsApi) =>
  call<AlertSources>(caseUrl(a.apiBaseUrl, a.investigationId, "alert-sources"), a.bearerToken, "Listing what raises alerts");

/** ADR-146 decision 7: *Raise an alert…* to the case or its dataset. */
export const raiseAlert = (a: AlertsApi, body: RaiseAlertInput) =>
  call<Alert>(caseUrl(a.apiBaseUrl, a.investigationId, "raised-alerts"), a.bearerToken, "Raising the alert", { method: "POST", body });

export const sendBackClose = (a: AlertsApi, alertId: string, reason: string) =>
  call<Alert>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue/${encodeURIComponent(alertId)}/send-back`), a.bearerToken, "Sending the close back", { method: "POST", body: { reason } });

export const setListSchedule = (a: ListsApi, listName: string, schedule: ListSchedule | null) =>
  call<ScreeningListStatus>(
    `${a.apiBaseUrl}/v1/admin/screening-lists/${encodeURIComponent(listName)}/schedule`,
    a.bearerToken,
    "Setting the refresh schedule",
    { method: "PUT", body: { schedule } },
  );

/** ADR-146 decision 6: an alert at its own address, `GET /v1/alerts/{id}`: its case and its
 * explanation there, or `null` where the Conduit answers that it does not exist, which is also its
 * answer for an alert the reader may not see (rule 3); the two are never told apart here. */
export async function openAlertAtAddress(apiBaseUrl: string, bearerToken: string, alertId: string): Promise<AlertAtAddress | null> {
  const response = await fetch(`${apiBaseUrl}/v1/alerts/${encodeURIComponent(alertId)}`, {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (response.status === 404) return null;
  if (!response.ok) throw await failure(response, "Opening the alert");
  return (await response.json()) as AlertAtAddress;
}
