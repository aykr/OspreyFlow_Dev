/**
 * A fake Conduit for the alert monitoring page (slice GR3a): a real HTTP server on a free port that RECORDS every call and
 * REFUSES what the real report route refuses (rule 15: a fake that only grants proves the page agrees with our hopes).
 *
 * What it refuses, as `services/api/app.py` (`read_case_report`) and `services/api/reports.py` do, in the order the real ones run:
 *  - every `/v1` route: no `Authorization: Bearer`, or a bearer it does not know, is 401 `{"detail": "Not authenticated"}`;
 *  - any method but GET on the route: 405; any other `/v1` path: 404 `{"detail": "Not Found"}` (and recorded, so a page that asks
 *    for `GET /v1/reports/dashboards`, the Superset list, or anything else, is seen);
 *  - the right `read_reports` is asked first, before the case, for a case that is there or not: 403
 *    `{"detail": {"error": "right_required", "right": "read_reports"}}` (`require_right`, ADR-112);
 *  - the case: a case the person holds no level on, one in another unit, one nobody shared and one that is not there are one
 *    answer, 404 `{"error": "investigation_not_found"}` (`InvestigationStore.get_authorized`, ADR-041);
 *  - `weeks` is a whole number from 1 to 52: another value is FastAPI's own 422 (`detail` a list), after the right and the case;
 *  - every figure is counted as the reader: an alert whose citations name anything above the reader's clearance is in no total,
 *    week, rule, outcome or age (the queue's all-or-nothing check, `alert_queue.monitoring_queue_and_left_out`, ADR-039), and the
 *    bound is counted from what the reader sees; past it, 409 `limit_exceeded` with `would_be` of the visible alerts alone;
 *  - `alerts_total` is the count of TYPOLOGY alerts alone, while `monitoring` counts every kind (`reports.py` lines 278 to 288);
 *  - the held rows' figures are for Editors and above only: a Viewer's report carries `held: null`.
 */
import { createServer } from "node:http";
import type { IncomingMessage, Server, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export type Clearance = "OFFICIAL" | "SECRET";
const RANK: Record<Clearance, number> = { OFFICIAL: 0, SECRET: 1 };

/** One alert of the world: where it stands, and the clearance the nodes it cites need (the leak test's worlds, in miniature). */
export interface WorldAlert {
  /** The Monday of the week it was raised in, as `YYYY-MM-DD`. */
  week: string;
  label: "typology" | "hotlists" | "monitors";
  typology?: string;
  /** What the nodes it cites need to be read. */
  needs: Clearance;
  /** How it was closed (`true_positive`, `false_positive`, ...), or `closed` for none; absent while it is open. */
  closedAs?: string;
  /** The age band it was closed in. */
  tookBand?: "under a day" | "1 to 7 days" | "7 to 30 days" | "over 30 days";
}

export interface Reader {
  token: string;
  id: string;
  clearance: Clearance;
  rights: string[];
  /** The level held on each case; a case not listed is one the person holds no level on. */
  cases: Record<string, "viewer" | "editor" | "author">;
}

export interface Seen {
  method: string;
  path: string;
  query: URLSearchParams;
  authorization: string | undefined;
}

export interface FakeReportConduit {
  url: string;
  calls: Seen[];
  /** A case's alerts, by case id. */
  world: Map<string, WorldAlert[]>;
  /** The bound on visible alerts in a period (the real one is `ALERT_BOUND`); small here so a test can pass it. */
  bound: number;
  /** A path fragment that answers 500, to model a failing Conduit. */
  failing: Set<string>;
  /** The next report answer is this status with this body instead of the real rule's (a body the page must not trust). */
  next: { status: number; body: string } | undefined;
  stop(): Promise<void>;
}

/** The week the fake says it is: periods are counted back from here. */
export const AS_OF = "2026-11-23";
const DAY = 86_400_000;
const AGE_LABELS = ["under a day", "1 to 7 days", "7 to 30 days", "over 30 days"] as const;

const reply = (res: ServerResponse, status: number, body: unknown): void => {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
};

function count<T>(items: T[], key: (item: T) => string): Map<string, number> {
  const out = new Map<string, number>();
  for (const item of items) out.set(key(item), (out.get(key(item)) ?? 0) + 1);
  return out;
}

/** The figures of the real `MonitoringFigures`, counted over the alerts a reader may see. */
function figuresOf(alerts: WorldAlert[], weeks: number, level: "viewer" | "editor" | "author"): Record<string, unknown> {
  const raised = [...count(alerts, (a) => `${a.week}|${a.label}|${a.typology ?? ""}`)].map(([key, n]) => {
    const [week, label, typology] = key.split("|") as [string, string, string];
    return { week_start: week, label, ...(typology ? { typology } : {}), count: n };
  });
  const closedAlerts = alerts.filter((a) => a.closedAs !== undefined);
  const closed = [...count(closedAlerts, (a) => `${a.week}|${a.closedAs as string}`)].map(([key, n]) => {
    const [week, label] = key.split("|") as [string, string];
    return { week_start: week, label, count: n };
  });
  const took = count(closedAlerts, (a) => a.tookBand ?? "under a day");
  const hotlists = [...count(alerts.filter((a) => a.label === "hotlists"), (a) => a.week)].map(([week, n]) => ({ week_start: week, label: "hotlists", count: n }));
  const groups = [...new Set(alerts.map((a) => `${a.label}|${a.typology ?? ""}`))].map((key) => key.split("|") as [string, string]);
  const team = groups.map(([label, typology]) => {
    const mine = alerts.filter((a) => a.label === label && (a.typology ?? "") === typology);
    return {
      label,
      ...(typology ? { typology } : {}),
      unassigned: mine.filter((a) => a.closedAs === undefined).length,
      mine: 0,
      older_than_week: 0,
      closed: mine.filter((a) => a.closedAs !== undefined).length,
      not_of_interest: mine.filter((a) => a.closedAs === "false_positive" || a.closedAs === "no_further_action").length,
    };
  });
  return {
    period_weeks: weeks,
    as_of: `${AS_OF}T09:00:00Z`,
    generated_at: `${AS_OF}T09:00:00Z`,
    // As the real route: `alerts_total` counts typology alerts only (`reports.py` `alert_report_and_left_out`, "as they always have");
    // the monitoring figures below count every kind. A fake that sent the sum of every kind would hide a page that reads this as that.
    alerts_total: alerts.filter((a) => a.label === "typology").length,
    alerts_by_week: [],
    open_by_age: [],
    outcomes: [],
    monitoring: {
      raised_by_rule: raised,
      closed_by_outcome: closed,
      time_to_close: AGE_LABELS.map((label) => ({ label, value: took.get(label) ?? 0 })),
      hotlist_matches: hotlists,
      open_by_source: [],
      team,
    },
    held: level === "viewer" ? null : { held: 2, released: 5, rejected: 1 },
    kyc: null,
    pole: null,
    drawing: null,
  };
}

export async function fakeReportConduit(readers: Reader[]): Promise<FakeReportConduit> {
  const fake: FakeReportConduit = {
    url: "",
    calls: [],
    world: new Map(),
    bound: 1000,
    failing: new Set(),
    next: undefined,
    stop: () => new Promise((resolve) => server.close(() => resolve())),
  };
  const byToken = new Map(readers.map((r) => [r.token, r]));

  const handle = (req: IncomingMessage, res: ServerResponse): void => {
    req.resume();
    const target = new URL(req.url ?? "/", "http://conduit.test");
    const method = req.method ?? "GET";
    const header = req.headers["authorization"];
    const reported = method === "POST" && target.pathname === "/v1/session-events";
    if (!reported) fake.calls.push({ method, path: target.pathname, query: target.searchParams, authorization: header });
    const token = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
    const reader = token === undefined ? undefined : byToken.get(token);
    if (!reader) return reply(res, 401, { detail: "Not authenticated" });
    if (reported) {
      res.writeHead(204);
      res.end();
      return;
    }
    for (const fragment of fake.failing) {
      if (target.pathname.includes(fragment)) return reply(res, 500, { detail: "Internal Server Error" });
    }
    const route = /^\/v1\/investigations\/([^/]+)\/reports$/.exec(target.pathname);
    if (!route) return reply(res, 404, { detail: "Not Found" });
    if (method !== "GET") return reply(res, 405, { detail: "Method Not Allowed" });
    // The right first, before the case: a route's own dependency runs before its handler's.
    if (!reader.rights.includes("read_reports")) {
      return reply(res, 403, { detail: { error: "right_required", right: "read_reports" } });
    }
    const caseId = decodeURIComponent(route[1] as string);
    const level = reader.cases[caseId];
    if (level === undefined) return reply(res, 404, { error: "investigation_not_found" });
    if (fake.next) {
      const planted = fake.next;
      fake.next = undefined;
      res.writeHead(planted.status, { "Content-Type": "application/json" });
      res.end(planted.body);
      return;
    }
    const raw = target.searchParams.get("weeks");
    const weeks = raw === null ? 12 : /^\d+$/.test(raw) ? Number(raw) : Number.NaN;
    if (!Number.isInteger(weeks) || weeks < 1 || weeks > 52) {
      return reply(res, 422, { detail: [{ type: "int_parsing", loc: ["query", "weeks"], msg: "Input should be a valid integer" }] });
    }
    const since = Date.parse(`${AS_OF}T00:00:00Z`) - weeks * 7 * DAY;
    // The all-or-nothing check: an alert citing anything the reader may not read is in nothing, and the bound counts what is left.
    const visible = (fake.world.get(caseId) ?? []).filter((a) => RANK[a.needs] <= RANK[reader.clearance] && Date.parse(`${a.week}T00:00:00Z`) >= since);
    if (visible.length > fake.bound) {
      return reply(res, 409, { error: "limit_exceeded", cap_kind: "alerts", cap: fake.bound, would_be: visible.length, options: ["shorter_period", "fewer_typologies"] });
    }
    return reply(res, 200, figuresOf(visible, weeks, level));
  };

  const server: Server = createServer(handle);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  fake.url = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  return fake;
}
