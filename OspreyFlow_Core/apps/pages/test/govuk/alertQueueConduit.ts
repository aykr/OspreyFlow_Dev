/**
 * A fixture Conduit for the alert queue page (slice RM1a): a real HTTP server on a free port that RECORDS every call and REFUSES what the
 * real route refuses (rule 15: a fixture that only grants proves the page agrees with our hopes). Written from `services/api/app.py`'s
 * `read_alert_queue` and the dependencies its decorator and parameters name, in the order the real ones run:
 *
 *  1. no `Authorization: Bearer`, or a bearer it does not know, is 401 `{"detail": "Not authenticated"}` (a token in the query is ignored);
 *  2. `require_right(READ_ALERT_QUEUE)`: 403 `{"detail": {"error": "right_required", "right": "read_alert_queue"}}`;
 *  3. `require_queue_rows` (ADR-146 Amendment 2 point 3): the rows only to a reader the Rules and Monitoring place is offered to (the right
 *     to triage alerts or to author rules, with the queue's read) and to the Reports Viewer; anyone else holding the queue's read is 403
 *     `{"detail": {"error": "queue_rows_not_offered", "place": "rules", "counts": "alert-queue/counts"}}`;
 *  4. the case (`InvestigationViewerDep`): a case the reader does not hold is 404 `{"error": "investigation_not_found"}`, and one they hold
 *     below Viewer is 403 with a string `detail` (`InsufficientAccessError`), whatever the alerts in it;
 *  5. the query's own checks (FastAPI's 422, `detail` a list): `status` one of open, claimed, closing, closed, active, all; `kind` and
 *     `severity` each one of the route's values; `show` one of mine, team, unassigned, all; `older_than_days` a whole number from 1 to 3650;
 *  6. the rows: the case's alerts in the status asked for (`active`, the default, is open, claimed and closing), **an alert any of whose
 *     evidence the reader is not cleared for is left out, and not counted** (rule 3; `monitoring_queue`), each row a `QueuedAlert` whose
 *     `alert` is the whole persisted row (its entities, citations and evidence ids included: the page must not draw them).
 *
 * It also answers `GET /v1/investigations` (the cases the caller holds a level on, as `CaseRow`s). `reach: false` models a Conduit that did
 * not leave the hidden alerts out, to show the page keeps no filter of its own to hide them; `fault` makes the next reads fail in the ways a
 * Conduit can (5xx, a body that is not what the route sends).
 *
 * Synthetic throughout (rule 9): every name, case and summary is invented here.
 */
import { createServer } from "node:http";
import type { IncomingHttpHeaders, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

import type { Alert } from "../../../../packages/schemas/generated/Alert.js";
import type { QueuedAlert } from "../../../../packages/schemas/generated/QueuedAlert.js";

export type { Alert, QueuedAlert };

export interface Case {
  id: string;
  name: string;
  level: "viewer" | "editor" | "author";
  created_at: string;
  created_by: string;
  domains: string[];
  datasets: string[];
  dataset_ids: string[];
}

export interface Reader {
  /** The bearer this person's sessions carry. */
  token: string;
  /** What the right table gives their roles: `read_alert_queue` and, to open the place, `triage_alerts` or `author_rules`. */
  rights: string[];
  roles: string[];
  /** The markings this reader is cleared for: an alert whose evidence carries another is left out of their queue. */
  cleared: string[];
  cases: Case[];
}

/** One alert the Conduit holds, and the marking its evidence carries (none: anyone who reads the case may see it). */
export interface Held {
  caseId: string;
  row: QueuedAlert;
  needs?: string;
}

export interface Seen {
  method: string;
  url: string;
  path: string;
  query: URLSearchParams;
  headers: IncomingHttpHeaders;
  rawHeaders: string[];
}

/** How the next reads of the queue (or of the case list) go wrong, until it is cleared. */
export interface Fault {
  on: "queue" | "cases";
  /** An answer of this status with no body worth reading (5xx), or `body` as it is. */
  status?: number;
  body?: unknown;
}

export interface QueueConduit {
  url: string;
  calls: Seen[];
  readers: Reader[];
  alerts: Held[];
  reach: boolean;
  fault: Fault | undefined;
  stop(): Promise<void>;
}

export const QUEUE_RIGHTS = ["read_alert_queue", "triage_alerts"];
const STATUSES = ["open", "claimed", "closing", "closed", "active", "all"];
const KINDS = ["typology", "hotlist", "monitor", "analyst", "drawn_watch"];
const SEVERITIES = ["low", "medium", "high"];
const SHOWS = ["mine", "team", "unassigned", "all"];

let counter = 0;
const next = (): number => ++counter;

/** Made at run time and held in memory: a bearer for the fixture to know. */
export function token(): string {
  return `tok-${next()}-${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
}

export function aCase(over: Partial<Case> = {}): Case {
  const n = next();
  return {
    id: `case-${n}`,
    name: `Wing review ${n}`,
    level: "viewer",
    created_at: "2026-11-01T09:00:00Z",
    created_by: "analyst-1",
    domains: ["niem"],
    datasets: ["Harbour prison extract (synthetic)"],
    dataset_ids: ["harbour-extract"],
    ...over,
  };
}

export function aReader(over: Partial<Reader> = {}): Reader {
  return { token: token(), rights: QUEUE_RIGHTS, roles: ["analyst"], cleared: [], cases: [aCase()], ...over };
}

/**
 * A whole persisted alert and its queue row, as the route serialises them (every field of the generated types, defaults included): the
 * words of `summary` are the finding, and each other field is a marker the page must not draw.
 */
export function aRow(over: { summary?: string; alert?: Partial<Alert>; row?: Partial<QueuedAlert> } = {}): QueuedAlert {
  const n = next();
  const alert: Alert = {
    id: `alert-id-${n}`,
    rule_id: `rule-id-${n}`,
    owner_id: `owner-id-${n}`,
    mode: "full",
    referent_node_ids: [`node-id-${n}-a`, `node-id-${n}-b`],
    investigation_id: null,
    created_at: "2026-11-24T09:15:00Z",
    dataset_id: `dataset-id-${n}`,
    typology: "structuring",
    words: `alert-words-${n}`,
    edge_ids: [`edge-id-${n}`],
    event_ids: [`event-id-${n}`],
    window: null,
    trigger: "post_commit",
    alert_node_id: `alert-node-id-${n}`,
    status: "open",
    assignee: null,
    disposition: null,
    disposition_reason: null,
    decided_by: null,
    decided_at: null,
    close_proposed_by: null,
    close_proposed_at: null,
    severity: "medium",
    team: null,
    routed_team: null,
    suppressed_until: null,
    suppress_reason: null,
    suppressed_by: null,
    citations: [{ words: `citation-words-${n}`, node_ids: [`citation-node-${n}`], edge_ids: [] }],
    ...over.alert,
  };
  return {
    alert,
    summary: over.summary ?? `Payments just under the limit from account ${n}`,
    kind: "typology",
    severity: "medium",
    audience: "case",
    team: null,
    assignee_name: null,
    team_name: null,
    suppressed: false,
    lead: false,
    ...over.row,
  };
}

function json(res: ServerResponse, status: number, body: unknown): void {
  const text = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(text) });
  res.end(text);
}

const ACTIVE = ["open", "claimed", "closing"];

/** The route's own query checks: the first parameter FastAPI would refuse, or none. */
export function queryRefusal(query: URLSearchParams): string | undefined {
  const status = query.get("status");
  if (status !== null && !STATUSES.includes(status)) return "status";
  for (const kind of query.getAll("kind")) if (!KINDS.includes(kind)) return "kind";
  for (const severity of query.getAll("severity")) if (!SEVERITIES.includes(severity)) return "severity";
  const show = query.get("show");
  if (show !== null && !SHOWS.includes(show)) return "show";
  const older = query.get("older_than_days");
  if (older !== null && !(/^\d+$/.test(older) && Number(older) >= 1 && Number(older) <= 3650)) return "older_than_days";
  return undefined;
}

export async function queueConduit(world: { readers: Reader[]; alerts: Held[]; reach?: boolean }): Promise<QueueConduit> {
  const server = createServer((req, res) => {
    const target = new URL(req.url ?? "/", "http://conduit.test");
    // The sign-in's own report (SE8c) is the page service's and not a read of the page: kept apart, as the Studio's fake keeps it.
    const reported = req.method === "POST" && target.pathname === "/v1/session-events";
    (reported ? events : calls).push({
      method: req.method ?? "GET",
      url: req.url ?? "",
      path: target.pathname,
      query: target.searchParams,
      headers: req.headers,
      rawHeaders: req.rawHeaders,
    });
    if (reported) {
      res.writeHead(204);
      res.end();
      return;
    }
    const header = req.headers["authorization"];
    const bearer = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
    const reader = bearer === undefined ? undefined : fake.readers.find((r) => r.token === bearer);
    if (!reader) return json(res, 401, { detail: "Not authenticated" });
    const failing = fake.fault;
    if (req.method === "GET" && target.pathname === "/v1/investigations") {
      if (failing?.on === "cases") return json(res, failing.status ?? 200, failing.body ?? { detail: "Internal Server Error" });
      return json(res, 200, reader.cases);
    }
    // The real Conduit decodes the path (`%2F` becomes `/`) BEFORE it routes (the server hands the app a decoded path), so the route is
    // found on the decoded path: an id holding a slash lands on the route the decoded address names, not always on the queue (rule 15).
    const decoded = decodeURIComponent(target.pathname);
    // Two of the routes such an address reaches (app.py): a node's ownership read, and `explain_alert` (which writes an audit row).
    // Each answers a body that is not a queue, as the real ones do, so a page that reached one would be seen to.
    const other = /^\/v1\/investigations\/[^/]+\/(ownership|alert-queue)\/[^/]+$/.exec(decoded);
    if (req.method === "GET" && other) return json(res, 200, { served: other[1], note: "not the alert queue" });
    const found = /^\/v1\/investigations\/([^/]+)\/alert-queue$/.exec(decoded);
    if (req.method !== "GET" || !found) return json(res, 404, { detail: "Not Found" });
    if (!reader.rights.includes("read_alert_queue")) {
      return json(res, 403, { detail: { error: "right_required", right: "read_alert_queue" } });
    }
    const opensPlace = reader.rights.includes("triage_alerts") || reader.rights.includes("author_rules");
    if (!opensPlace && !reader.roles.includes("reports_viewer")) {
      return json(res, 403, { detail: { error: "queue_rows_not_offered", place: "rules", counts: "alert-queue/counts" } });
    }
    const caseId = found[1] as string;
    const held = reader.cases.find((c) => c.id === caseId);
    if (!held) return json(res, 404, { error: "investigation_not_found" });
    if ((held.level as string) === "none") return json(res, 403, { detail: "You need at least Viewer access to this case." });
    const refused = queryRefusal(target.searchParams);
    if (refused !== undefined) {
      return json(res, 422, { detail: [{ type: "enum", loc: ["query", refused], msg: "Input should be a permitted value" }] });
    }
    if (failing?.on === "queue") return json(res, failing.status ?? 200, failing.body ?? { detail: "Internal Server Error" });
    const asked = target.searchParams.get("status") ?? "active";
    const statuses = asked === "all" ? undefined : asked === "active" ? ACTIVE : [asked];
    const rows = fake.alerts
      .filter((a) => a.caseId === caseId)
      .filter((a) => statuses === undefined || statuses.includes(a.row.alert.status ?? "open"))
      // Rule 3: an alert any of whose evidence the reader is not cleared for is left out, and not counted.
      .filter((a) => !fake.reach || a.needs === undefined || reader.cleared.includes(a.needs))
      .map((a) => a.row);
    return json(res, 200, rows);
  });
  const calls: Seen[] = [];
  const events: Seen[] = [];
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
  const fake: QueueConduit = {
    url: `http://127.0.0.1:${(server.address() as AddressInfo).port}`,
    calls,
    readers: world.readers,
    alerts: world.alerts,
    reach: world.reach ?? true,
    fault: undefined,
    stop: () => new Promise((resolve) => server.close(() => resolve())),
  };
  return fake;
}
