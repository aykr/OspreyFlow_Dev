/**
 * A fixture Conduit for the page of trends shown together (slice GR4a): a real HTTP server on a free port that RECORDS every call and
 * REFUSES what the real pack routes refuse (rule 15: a fixture that only grants proves the page agrees with our hopes). Synthetic
 * throughout (rule 9): no case, pack, person or figure here is real.
 *
 * What it refuses, in the order `services/api/app.py` refuses it (the router first, then the route's dependencies in turn):
 *  - a path it has not is 404 `{"detail": "Not Found"}`, and a method a path does not serve is 405 `{"detail": "Method Not Allowed"}`,
 *    for anyone (the router answers before the bearer is looked at). The paths and methods are the real pack routes': the case's packs
 *    (GET, POST), a pack (GET), its items (POST), its order (PUT), its history (GET), its publishing (POST), its newest published
 *    version (GET), and the case's published packs (GET);
 *  - no `Authorization: Bearer`, or a bearer it does not know, is 401 `{"detail": "Not authenticated"}`;
 *  - the route's right, by `require_right`: `record_assessment` for the working pack's routes, `read_reports` for the published ones; a
 *    person without it is 403 `{"detail": {"error": "right_required", "right": ...}}` (the Conduit's words name the right, so the page
 *    must never show them);
 *  - the case, by `_authorized_at`: a case the reader holds no level in, or that does not exist, is the same 404
 *    `{"error": "investigation_not_found"}` (ADR-041's existence-leak rule); a write needs Editor, and a Viewer is 403 in the store's words;
 *  - the pack, by `_pack_or_404`: a pack that is not in this case (another case's included) is 404 `{"detail": "no such pack in this case"}`;
 *  - the published read of a pack never published is 404 `{"detail": "this pack has no publication"}`.
 * What it sends, as the route's models do: `PackDraft` (`pack`, `items`, `withheld`, `marking`) for the working pack and `PublishedPack`
 * for the newest published version, each item a whole `PackItem`. **Which items a reader gets is decided here, from the world, as the
 * real store's query decides it:** an item hidden from the reader is left out, the others keep their stored order, and `withheld` is
 * whether any was left out: a yes or no, never a count or a place (ADR-124 decision 9). A write that would succeed is NOT modelled (the
 * page never writes): it is a 500 and the call is recorded, so that a later slice that writes must teach it the real answer.
 * A test can replace the body or the status of the one read (`draft_answer`, `published_answer`) or cut the connection (`no_answer`).
 */
import { createServer } from "node:http";
import type { IncomingHttpHeaders, IncomingMessage, Server, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export const RECORD_ASSESSMENT = "record_assessment";
export const READ_REPORTS = "read_reports";

export interface Reader {
  /** The bearer this person's sessions carry. */
  token: string;
  rights: string[];
  /** The cases the person holds a level in, and the level. */
  cases: Record<string, "viewer" | "editor" | "author">;
}

/** One stored item: the whole `PackItem` the route serves, and the readers it is withheld from (who may not view what it rests on). */
export interface StoredItem {
  item: Record<string, unknown>;
  hiddenFrom?: string[];
}

export interface StoredPack {
  id: string;
  case_id: string;
  title: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  /** The working pack's current items, in their stored order. */
  items: StoredItem[];
  /** The newest published version, if the pack was ever published. */
  published?: { version: number; published_at: string; published_by: string; published_by_name?: string | null; items: StoredItem[] };
}

export interface Canned {
  status: number;
  body: unknown;
}

export interface PacksConduitOptions {
  readers: Reader[];
  /** The cases that exist (a case no reader holds a level in still answers the same 404 as one that does not). */
  cases: string[];
  packs: StoredPack[];
  /** A failing or odd answer for the working pack's read, given to a reader who passed every check. */
  draft_answer?: Canned;
  /** The same for the published read. */
  published_answer?: Canned;
  /** Cut the connection of whichever read reaches the pack, after every check passed. */
  no_answer?: boolean;
}

export interface Call {
  method: string;
  /** The path and the query, as received. */
  url: string;
  headers: IncomingHttpHeaders;
}

export interface PacksConduit {
  url: string;
  calls: Call[];
  stop(): Promise<void>;
}

/** The routes, as patterns of segments: `{c}` is the case, `{p}` the pack; each with the methods it serves and the right it asks. */
interface Route {
  pattern: string[];
  methods: string[];
  right: (method: string) => string;
}
const ROUTES: Route[] = [
  { pattern: ["v1", "investigations", "{c}", "packs"], methods: ["GET", "POST"], right: () => RECORD_ASSESSMENT },
  { pattern: ["v1", "investigations", "{c}", "packs", "{p}"], methods: ["GET"], right: () => RECORD_ASSESSMENT },
  { pattern: ["v1", "investigations", "{c}", "packs", "{p}", "items"], methods: ["POST"], right: () => RECORD_ASSESSMENT },
  { pattern: ["v1", "investigations", "{c}", "packs", "{p}", "order"], methods: ["PUT"], right: () => RECORD_ASSESSMENT },
  { pattern: ["v1", "investigations", "{c}", "packs", "{p}", "history"], methods: ["GET"], right: () => RECORD_ASSESSMENT },
  { pattern: ["v1", "investigations", "{c}", "packs", "{p}", "publish"], methods: ["POST"], right: () => RECORD_ASSESSMENT },
  { pattern: ["v1", "investigations", "{c}", "packs", "{p}", "published"], methods: ["GET"], right: () => READ_REPORTS },
  { pattern: ["v1", "investigations", "{c}", "published"], methods: ["GET"], right: () => READ_REPORTS },
];

function match(segments: string[]): { route: Route; params: Record<string, string> } | undefined {
  for (const route of ROUTES) {
    if (route.pattern.length !== segments.length) continue;
    const params: Record<string, string> = {};
    let ok = true;
    route.pattern.forEach((part, i) => {
      const seg = segments[i] as string;
      if (part.startsWith("{")) params[part.slice(1, -1)] = seg;
      else if (part !== seg) ok = false;
    });
    if (ok) return { route, params };
  }
  return undefined;
}

/** The items a reader gets, in stored order, and whether any were left out: the store's own query, as the reader. */
export function readableFor(items: StoredItem[], token: string): { items: Record<string, unknown>[]; withheld: boolean } {
  const shown = items.filter((s) => !(s.hiddenFrom ?? []).includes(token)).map((s) => s.item);
  return { items: shown, withheld: shown.length !== items.length };
}

const RANK = ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET", "TOP SECRET"];
/** The highest marking among the items shown, or null when none is (`highest_marking`). */
function highest(items: Record<string, unknown>[]): string | null {
  const marks = items.map((i) => String(i["marking"]));
  if (marks.length === 0) return null;
  return marks.reduce((a, b) => (RANK.indexOf(b) > RANK.indexOf(a) ? b : a));
}

/** `PackDraft`, as `read_pack` builds it for this reader: every field of the model. */
export function draftBody(pack: StoredPack, token: string): Record<string, unknown> {
  const { items, withheld } = readableFor(pack.items, token);
  return {
    pack: { id: pack.id, investigation_id: pack.case_id, title: pack.title, created_by: pack.created_by, created_at: pack.created_at, updated_at: pack.updated_at, versions: [] },
    items,
    withheld,
    marking: highest(items),
  };
}

/** `PublishedPack`, as `read_published_pack` builds it for this reader: every field of the model. */
export function publishedBody(pack: StoredPack, token: string): Record<string, unknown> {
  const published = pack.published;
  if (!published) throw new Error("the pack was never published");
  const { items, withheld } = readableFor(published.items, token);
  return {
    pack_id: pack.id,
    investigation_id: pack.case_id,
    title: pack.title,
    version: published.version,
    published_at: published.published_at,
    published_by: published.published_by,
    published_by_name: published.published_by_name ?? null,
    items,
    withheld,
    marking: highest(items),
  };
}

export async function packsConduit(options: PacksConduitOptions): Promise<PacksConduit> {
  const calls: Call[] = [];
  const server: Server = createServer((req, res) => {
    const url = req.url ?? "/";
    calls.push({ method: req.method ?? "", url, headers: req.headers });
    req.on("data", () => undefined);
    req.on("end", () => answer(req, res, url));
  });
  const answer = (req: IncomingMessage, res: ServerResponse, url: string): void => {
    const send = (status: number, body: unknown): void => {
      res.statusCode = status;
      if (typeof body === "string") {
        res.setHeader("Content-Type", "text/plain");
        res.end(body);
        return;
      }
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(body));
    };
    const method = req.method ?? "";
    const segments = (url.split("?")[0] ?? "").split("/").filter((s) => s !== "").map((s) => decodeURIComponent(s));
    const found = match(segments);
    // The router: a path it has not, then a method the path does not serve, for anyone.
    if (!found) return send(404, { detail: "Not Found" });
    if (!found.route.methods.includes(method)) return send(405, { detail: "Method Not Allowed" });
    // The bearer, then the route's right.
    const header = req.headers["authorization"];
    const token = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
    const reader = options.readers.find((r) => r.token === token);
    if (!reader) return send(401, { detail: "Not authenticated" });
    const right = found.route.right(method);
    if (!reader.rights.includes(right)) return send(403, { detail: { error: "right_required", right } });
    // The case: no level, or no such case, is the same 404; a write needs Editor.
    const caseId = found.params["c"] as string;
    const level = options.cases.includes(caseId) ? reader.cases[caseId] : undefined;
    if (level === undefined) return send(404, { error: "investigation_not_found" });
    if (method !== "GET" && level === "viewer") return send(403, { detail: "Editor access to this investigation is required" });
    // The pack, when the route names one: it must be in this case.
    const packId = found.params["p"];
    const pack = packId === undefined ? undefined : options.packs.find((p) => p.id === packId && p.case_id === caseId);
    if (packId !== undefined && pack === undefined) return send(404, { detail: "no such pack in this case" });
    if (method !== "GET") return send(500, { detail: "the fixture Conduit does not model a successful write" });
    const last = segments[segments.length - 1];
    if (pack !== undefined && segments.length === 5) {
      if (options.no_answer === true) return void req.socket.destroy();
      if (options.draft_answer) return send(options.draft_answer.status, options.draft_answer.body);
      return send(200, draftBody(pack, reader.token));
    }
    if (pack !== undefined && last === "published") {
      if (!pack.published) return send(404, { detail: "this pack has no publication" });
      if (options.no_answer === true) return void req.socket.destroy();
      if (options.published_answer) return send(options.published_answer.status, options.published_answer.body);
      return send(200, publishedBody(pack, reader.token));
    }
    // The other reads (the case's packs, a pack's history, the case's published packs) are not the page's: not modelled.
    return send(500, { detail: "the fixture Conduit does not model this read" });
  };
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    url: `http://127.0.0.1:${port}`,
    calls,
    stop: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

// ------------------------------------------------------------------------------------------------ a synthetic world's parts

/** A trend's figures, as `TrendFigures` has them (every field of the model): a weekly count, unless `over` says otherwise. */
export function figures(over: {
  title: string;
  points: { period_start: string; value: number; series?: string | null }[];
  window_start?: string;
  as_of?: string;
  definition?: Record<string, unknown>;
  result?: Record<string, unknown>;
}): Record<string, unknown> {
  const total = over.points.reduce((sum, p) => sum + p.value, 0);
  return {
    definition: { title: over.title, source: "events", event_types: ["meeting"], measure: "count", measure_field: null, interval: "week", weeks: 4, group_by: null, filters: [], ...(over.definition ?? {}) },
    result: {
      interval: "week",
      measure: "count",
      points: over.points.map((p) => ({ period_start: p.period_start, series: p.series ?? null, value: p.value })),
      series: [],
      total,
      events: total,
      unvalued: 0,
      classifications: ["OFFICIAL"],
      handlings: [{ classification: "OFFICIAL", handling_code: "OPEN", owning_unit: "unit-north", originator: "synthetic-source" }],
      ...(over.result ?? {}),
    },
    as_of: over.as_of ?? "2026-11-01T09:00:00Z",
    window_start: over.window_start ?? "2026-10-05T00:00:00Z",
    marking: "OFFICIAL",
  };
}

/** A whole `PackItem` (every field of the model): a trend item when `trend` is given. */
export function packItem(over: Partial<Record<string, unknown>> & { id: string; kind: string }): Record<string, unknown> {
  return {
    marking: "OFFICIAL",
    added_by: "someone-synthetic",
    added_at: "2026-11-02T10:00:00Z",
    trend_id: null,
    trend: null,
    assessment: null,
    entity: null,
    note: null,
    alert: null,
    replaced_at: null,
    replaced_by: null,
    ...over,
  };
}
