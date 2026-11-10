// Fetch wrappers for `POST`/`GET .../hotlists` and `POST`/`GET .../monitors` (the inbox's `GET .../alerts` went in L2.10: one queue, ADR-146 decision 1)
// (`services/api/watch_routes.py`) — mirrors `patterns/api.ts`'s own conventions (Bearer auth, throw
// on a non-`ok` response). The jump's case of its own went in L2.9 (ADR-146 decision 6).
//
// `Hotlist`, `Monitor` and the schedule's input are the generated shapes.
import type { Hotlist, Monitor, MonitorScheduleInput } from "../../../../packages/schemas/generated";

/** ADR-133 ruling 3: whom a hotlist's alerts reach. */
export type HotlistAudience = NonNullable<Hotlist["audience"]>;




/** ADR-099 Amendment 3: watches and their alerts are the dataset's, asked of the case. */
function caseUrl(apiBaseUrl: string, investigationId: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}`;
}

function authHeaders(bearerToken: string): Record<string, string> {
  return { Authorization: `Bearer ${bearerToken}` };
}

/** A refusal in the server's own words where it gave some (ADR-133 ruling 3's
 * `hotlist_audience_fixed`), else the status. */
async function refusal(response: Response, what: string): Promise<Error> {
  const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
  return new Error(typeof body.detail === "string" ? body.detail : `${what} failed: ${response.status}`);
}

export async function createHotlist(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  request: { identifier: string; review_date: string; audience?: HotlistAudience },
): Promise<Hotlist> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/hotlists`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw await refusal(response, "POST .../hotlists");
  }
  return (await response.json()) as Hotlist;
}

/** ADR-133 ruling 3: the owner's hotlists, and the deployment's audience setting. */
export interface HotlistsWithSettings {
  hotlists: Hotlist[];
  audienceDefault: HotlistAudience;
  audienceEditable: boolean;
}

export async function readHotlists(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<HotlistsWithSettings> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/hotlists`, { headers: authHeaders(bearerToken) });
  if (!response.ok) {
    throw new Error(`GET .../hotlists failed: ${response.status}`);
  }
  const body = (await response.json()) as {
    hotlists: Hotlist[];
    audience_default?: HotlistAudience;
    audience_editable?: boolean;
  };
  return {
    hotlists: body.hotlists,
    audienceDefault: body.audience_default ?? "only_me",
    audienceEditable: body.audience_editable ?? true,
  };
}

export async function setHotlistAudience(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  hotlistId: string,
  audience: HotlistAudience,
): Promise<Hotlist> {
  const response = await fetch(
    `${caseUrl(apiBaseUrl, investigationId)}/hotlists/${encodeURIComponent(hotlistId)}/audience`,
    {
      method: "PUT",
      headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
      body: JSON.stringify({ audience }),
    },
  );
  if (!response.ok) {
    throw await refusal(response, "Changing who its alerts reach");
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



/** ADR-146 decision 4 (G16): a watched pattern's own schedule, set by its owner. */
export async function setMonitorSchedule(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  monitorId: string,
  schedule: MonitorScheduleInput,
): Promise<Monitor> {
  const response = await fetch(`${caseUrl(apiBaseUrl, investigationId)}/monitors/${encodeURIComponent(monitorId)}/schedule`, {
    method: "PUT",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(schedule),
  });
  if (!response.ok) throw await refusal(response, "Setting the watch's schedule");
  return (await response.json()) as Monitor;
}
