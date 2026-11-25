/**
 * A fixture Conduit for the cases page (slice GR1a): a real HTTP server on a free port that RECORDS every call and REFUSES what the real
 * routes refuse (rule 15: a fixture that only grants proves the page agrees with our hopes). Synthetic throughout (rule 9).
 *
 * What it refuses, in the real routes' order (`services/api/app.py`):
 *  - the router first, for anyone: a path it has not is 404 `{"detail": "Not Found"}`, a method the path does not serve is 405
 *    `{"detail": "Method Not Allowed"}`. The methods are the real routes': `/v1/investigations` GET and POST (a new case);
 *    `/v1/investigations/{id}` GET, PATCH (a rename) and DELETE (a removal); `/v1/investigations/{id}/brief` GET. Every other path under
 *    a case (`/views`, `/datasets`, `/tab`, `/access` and the rest the real Conduit serves) is NOT modelled: 500, recorded, never a 404
 *    the real router would not give;
 *  - then who the bearer is: none is 401 `{"detail": "Not authenticated"}` (FastAPI's `HTTPBearer`; a token in the query is ignored, so
 *    refused as none); one it does not know is 401 with the resolver's own reason as the detail (`get_principal`: `detail=str(exc)`,
 *    whose words vary with the reason; the page draws none of them);
 *  - then a route-level right (`dependencies=[Depends(require_right(...))]`, run before the case's gate): the brief needs `investigate`,
 *    a rename `share_case`, a removal `remove_case` and a new case `create_case`; without it, 403
 *    `{"detail": {"error": "right_required", "right": <right>}}`;
 *  - then the case's gate (`_authorized_at`): a case that does not exist, one of another unit and one the reader holds no level on are
 *    the same 404 `{"error": "investigation_not_found"}`; a level too low for the route is 403 (a rename and a removal need Author);
 *  - a write that passes all of these is NOT modelled (this slice's page never writes): 500, recorded, so a later write slice has to
 *    teach it the real answers and cannot lean on a made-up one.
 * What it sends, as the route's models do: `InvestigationListing` rows for the list, in the store's order (the fixture's own order of
 * cases), and only the reader's unit's cases they hold a level on (`list_for`); `Investigation` for a case (no `domains_chosen`: it is
 * `exclude=True`); `CaseBrief` for the brief, with **every attachment this reader may not read left out** (`case_brief.py`, rule 3), as
 * the store's title resolver does. A test can make each route fail (`list_answer`, `case_answer`, `brief_answer`, `*_no_answer`).
 */
import { createServer } from "node:http";
import type { IncomingHttpHeaders, IncomingMessage, Server, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export type Level = "viewer" | "editor" | "author";
export type Kind = "trend" | "pattern" | "assessment" | "view";

export interface Reader {
  token: string;
  unit: string;
  rights: string[];
  /** The reader's level on each case, by id: a case not named is one they hold no level on. */
  levels: Record<string, Level>;
  /** The cases whose tab this reader closed (ADR-084, a flag per account). */
  hidden?: string[];
}

export interface Attachment {
  kind: Kind;
  id: string;
  title: string;
  /** The bearers of the readers who may read what it points to; absent, every reader of the case may. */
  readers?: string[];
}

export interface Requirement {
  id: string;
  text: string;
  status: "open" | "answered";
  answered_at: string | null;
  attachments: Attachment[];
}

export interface Case {
  id: string;
  name: string;
  created_at: string;
  created_by: string;
  owning_unit: string;
  domains: ("fibo" | "niem" | "stix")[];
  datasets: { id: string; name: string }[];
  brief: { priority: string; requirements: Requirement[] };
}

export interface Call {
  method: string;
  url: string;
  headers: IncomingHttpHeaders;
}

export interface Canned {
  status: number;
  body: unknown;
}

export interface CasesConduitOptions {
  readers: Reader[];
  cases: Case[];
  list_answer?: Canned;
  case_answer?: Canned;
  brief_answer?: Canned;
  list_no_answer?: boolean;
  case_no_answer?: boolean;
  brief_no_answer?: boolean;
}

export interface CasesConduit {
  url: string;
  calls: Call[];
  stop(): Promise<void>;
}

export const NOT_FOUND_CASE = { error: "investigation_not_found" };
/** The resolver's reason for a bearer it does not know: one of its own sentences (`packages/principal_auth`), standing for all. */
export const UNKNOWN_BEARER = "token is missing required claim: subject ('sub')";
export const rightRefusal = (right: string): unknown => ({ detail: { error: "right_required", right } });

/** What the Conduit sends for a case read (`Investigation`, without its excluded field). */
export const investigationOf = (c: Case): Record<string, unknown> => ({
  id: c.id,
  name: c.name,
  created_at: c.created_at,
  created_by: c.created_by,
  owning_unit: c.owning_unit,
  domains: c.domains,
});

/** What the Conduit sends for one row of the list (`InvestigationListing`). */
export const listingOf = (c: Case, reader: Reader): Record<string, unknown> => ({
  id: c.id,
  name: c.name,
  level: reader.levels[c.id],
  created_at: c.created_at,
  created_by: c.created_by,
  domains: c.domains,
  tab_hidden: (reader.hidden ?? []).includes(c.id),
  // `datasets.of_case` reads no dataset for a reader holding no right (`reads_dataset_names`, ADR-099 Amendment 11): the same empty
  // list whatever the case reads.
  datasets: reader.rights.length > 0 ? c.datasets.map((d) => d.name) : [],
  dataset_ids: reader.rights.length > 0 ? c.datasets.map((d) => d.id) : [],
});

/** What the Conduit sends for a brief (`CaseBrief`) to this reader: attachments they may not read are left out entirely. */
export const briefOf = (c: Case, reader: Reader): Record<string, unknown> => ({
  priority: c.brief.priority,
  requirements: c.brief.requirements.map((r) => ({
    id: r.id,
    text: r.text,
    status: r.status,
    answered_at: r.answered_at,
    attachments: r.attachments
      .filter((a) => a.readers === undefined || a.readers.includes(reader.token))
      .map((a) => ({ kind: a.kind, id: a.id, title: a.title })),
  })),
});

const RANK: Record<Level, number> = { viewer: 1, editor: 2, author: 3 };

export async function casesConduit(options: CasesConduitOptions): Promise<CasesConduit> {
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
    const canned = (c: Canned | undefined, cut: boolean | undefined, otherwise: () => void): void => {
      if (cut === true) return void req.socket.destroy();
      if (c) return send(c.status, c.body);
      otherwise();
    };
    // The path as the router sees it: decoded first (a `%2F` is a slash), as uvicorn gives it to Starlette (slice GG4a's review).
    const path = decodeURIComponent(url.split("?")[0] ?? "");
    const method = req.method ?? "";
    // The router answers first, as FastAPI's does.
    if (/^\/v1\/investigations\/[^/]+\/.+$/.test(path) && !/^\/v1\/investigations\/[^/]+\/brief$/.test(path)) {
      return send(500, { detail: "the fixture Conduit does not model this route of a case" });
    }
    const match = /^\/v1\/investigations(?:\/([^/]+)(\/brief)?)?$/.exec(path);
    if (!match) return send(404, { detail: "Not Found" });
    const id = match[1];
    const route = id === undefined ? "list" : match[2] === undefined ? "case" : "brief";
    const methods: Record<string, string[]> = { list: ["GET", "POST"], case: ["GET", "PATCH", "DELETE"], brief: ["GET"] };
    if (!(methods[route] as string[]).includes(method)) return send(405, { detail: "Method Not Allowed" });
    const header = req.headers["authorization"];
    const token = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
    if (token === undefined) return send(401, { detail: "Not authenticated" });
    const reader = options.readers.find((r) => r.token === token);
    if (!reader) return send(401, { detail: UNKNOWN_BEARER });
    // A route-level right, before the case's gate.
    const right = route === "brief" ? "investigate" : route === "list" && method === "POST" ? "create_case" : method === "PATCH" ? "share_case" : method === "DELETE" ? "remove_case" : undefined;
    if (right !== undefined && !reader.rights.includes(right)) return send(403, rightRefusal(right));
    if (route === "list") {
      if (method === "POST") return send(500, { detail: "the fixture Conduit does not model a successful write" });
      return canned(options.list_answer, options.list_no_answer, () =>
        send(200, options.cases.filter((c) => c.owning_unit === reader.unit && reader.levels[c.id] !== undefined).map((c) => listingOf(c, reader))),
      );
    }
    // The case's gate: no such case, another unit, no level: one 404.
    const found = options.cases.find((c) => c.id === id);
    const level = found ? reader.levels[found.id] : undefined;
    if (!found || found.owning_unit !== reader.unit || level === undefined) return send(404, NOT_FOUND_CASE);
    const needed: Level = method === "GET" ? "viewer" : "author";
    if (RANK[level] < RANK[needed]) return send(403, { detail: `this needs the ${needed} level on the case` });
    if (method !== "GET") return send(500, { detail: "the fixture Conduit does not model a successful write" });
    if (route === "case") return canned(options.case_answer, options.case_no_answer, () => send(200, investigationOf(found)));
    return canned(options.brief_answer, options.brief_no_answer, () => send(200, briefOf(found, reader)));
  };
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    url: `http://127.0.0.1:${port}`,
    calls,
    stop: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}
