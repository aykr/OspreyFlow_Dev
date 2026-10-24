// Fetch wrappers for `POST`/`GET .../hotlists`, `POST`/`GET .../monitors`, `GET /v1/alerts` and
// `POST /v1/alerts/{alert_id}/jump` (`services/api/watch_routes.py`) — mirrors `patterns/api.ts`'s
// own conventions (Bearer auth, throw on a non-`ok` response).
//
// **`AlertView`/`AlertJumpResult`/`Investigation` are hand-mirrored here, not imported from
// `packages/schemas/generated/`.** Checked directly against `packages/schemas/generate_ts.py`
// before writing this: its own model list is `schemas.{analytics,compute,domain,ingest,model,
// profile,provider_profile}` only — `services/api/watch_routes.py` (where `AlertView`/
// `AlertJumpResult` live) and `services/api/investigations.py` (where `Investigation` lives) are
// both outside that scope, by construction, since neither is a `packages/schemas` module at all.
// `Hotlist`/`Monitor` *are* generated (`schemas.domain.ALL_MODELS`) and imported below rather than
// redeclared — a disclosed gap, rather than left
// silently hand-mirrored with no note — a future edit to either Python shape has nothing to make
// this file's own copy drift-check the way `Hotlist`/`Monitor` already do.
import type { Hotlist, Monitor } from "../../../../packages/schemas/generated";

export type AlertMode = "full" | "notify_stub";

/** Mirrors `services/api/watch_routes.py::AlertView` field-for-field. */
export interface AlertView {
  id: string;
  rule_id: string;
  owner_id: string;
  mode: AlertMode;
  referent_node_ids: string[];
  evidence_available: boolean;
  investigation_id: string | null;
  created_at: string;
  /** ADR-110 Amendment 3: the alert in words; a scheduled run's notice is nothing else. */
  words?: string | null;
}

/** ADR-110 decision 10: a notice that a scheduled run failed or was refused, not a match. */
export const isScheduleNotice = (alert: AlertView) => alert.rule_id.startsWith("schedule:");

/** Mirrors `services/api/investigations.py::Investigation` field-for-field. */
export interface InvestigationSummary {
  id: string;
  created_at: string;
  created_by: string;
  owning_unit: string;
  branched_from: string | null;
}

/** Mirrors `services/api/watch_routes.py::AlertJumpResult` field-for-field. */
export interface AlertJumpResult {
  investigation: InvestigationSummary;
  seeded_count: number;
}

/** ADR-099 Amendment 3: watches and their alerts are the dataset's, asked of the case. */
function caseUrl(apiBaseUrl: string, investigationId: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}`;
}

function authHeaders(bearerToken: string): Record<string, string> {
  return { Authorization: `Bearer ${bearerToken}` };
}

export async function createHotlist(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  request: { identifier: string; review_date: string },
): Promise<Hotlist> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/hotlists`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`POST .../hotlists failed: ${response.status}`);
  }
  return (await response.json()) as Hotlist;
}

export async function listHotlists(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<Hotlist[]> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/hotlists`, { headers: authHeaders(bearerToken) });
  if (!response.ok) {
    throw new Error(`GET .../hotlists failed: ${response.status}`);
  }
  const body = (await response.json()) as { hotlists: Hotlist[] };
  return body.hotlists;
}

export async function createMonitor(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  request: { pattern_id: string },
): Promise<Monitor> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/monitors`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`POST .../monitors failed: ${response.status}`);
  }
  return (await response.json()) as Monitor;
}

export async function listMonitors(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<Monitor[]> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/monitors`, { headers: authHeaders(bearerToken) });
  if (!response.ok) {
    throw new Error(`GET .../monitors failed: ${response.status}`);
  }
  const body = (await response.json()) as { monitors: Monitor[] };
  return body.monitors;
}

export async function listAlerts(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<AlertView[]> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/alerts`, { headers: authHeaders(bearerToken) });
  if (!response.ok) {
    throw new Error(`GET .../alerts failed: ${response.status}`);
  }
  const body = (await response.json()) as { alerts: AlertView[] };
  return body.alerts;
}

export async function jumpAlert(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  alertId: string,
): Promise<AlertJumpResult> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/alerts/${encodeURIComponent(alertId)}/jump`, {
    method: "POST",
    headers: authHeaders(bearerToken),
  });
  if (!response.ok) {
    throw new Error(`POST .../alerts/${alertId}/jump failed: ${response.status}`);
  }
  return (await response.json()) as AlertJumpResult;
}
