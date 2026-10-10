// The Alerts place's calls (`06_DECISIONS.md` ADR-109 phases A and B; `03_CONDUIT_MIDDLEWARE.md`
// §3.8a): the case team's alert queue and an alert's explanation, the triage actions, the case's
// typology rules, their audit, and the rows a failing pre-commit rule held. Every shape is the
// generated one, so a change on the server is a type error here, never a silent drift.
import type {
  Alert,
  AlertDispositionInput,
  AlertExplanation,
  HeldRow,
  QueuedAlert,
  RuleAuditPage,
  TypologyRule,
  TypologyRuleInput,
} from "../../../../packages/schemas/generated";
import type { WorkingSetDelta } from "../workingset/models";

export type QueueFilter = "active" | "closed" | "all";

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
  if (body.error === "limit_exceeded") {
    return new Error(
      `Too many for the canvas: ${fmt.format(body.would_be ?? 0)} ${body.cap_kind ?? "nodes"} against a limit of ${fmt.format(body.cap ?? 0)}.`,
    );
  }
  if (body.error === "release_refused" && typeof body.detail === "string") {
    return new Error(`${body.detail[0]?.toUpperCase() ?? ""}${body.detail.slice(1)}.`);
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

export const listQueue = (a: AlertsApi, filter: QueueFilter) =>
  call<QueuedAlert[]>(caseUrl(a.apiBaseUrl, a.investigationId, `alert-queue?status=${filter}`), a.bearerToken, "Reading the alert queue");

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
  call<{ edges_created: number; nodes_created: number; rule_notes: string[] }>(
    caseUrl(a.apiBaseUrl, a.investigationId, `ingest/recipes/${encodeURIComponent(recipeId)}/held-rows/release`),
    a.bearerToken,
    "Releasing the rows",
    { method: "POST", body: { ids, reason } },
  );
