/**
 * A fixture Conduit for the cases page (slices GR1a, GR1e and GR1b): a real HTTP server on a free port that RECORDS every call and REFUSES what the real
 * routes refuse (rule 15: a fixture that only grants proves the page agrees with our hopes). Synthetic throughout (rule 9).
 *
 * What it refuses, in the real routes' order (`services/api/app.py`):
 *  - the router first, for anyone, on the DECODED path, as the real server's router sees it (an encoded slash is a slash): a path it has not is 404 `{"detail": "Not Found"}`, a method the path does not serve is 405
 *    `{"detail": "Method Not Allowed"}`. The methods are the real routes': `/v1/investigations` GET and POST (a new case);
 *    `/v1/investigations/{id}` GET, PATCH (a rename) and DELETE (a removal); `/v1/investigations/{id}/brief` GET;
 *    `/v1/investigations/{id}/history` GET and `/v1/investigations/{id}/history/{step_id}` POST (a restore). Every other path under
 *    a case (`/views`, `/datasets`, `/tab`, `/access` and the rest the real Conduit serves) is NOT modelled: 500, recorded, never a 404
 *    the real router would not give;
 *  - then who the bearer is: none is 401 `{"detail": "Not authenticated"}` (FastAPI's `HTTPBearer`; a token in the query is ignored, so
 *    refused as none); one it does not know is 401 with the resolver's own reason as the detail (`get_principal`: `detail=str(exc)`,
 *    whose words vary with the reason; the page draws none of them);
 *  - then a route-level right (`dependencies=[Depends(require_right(...))]`, run before the case's gate): the brief, the history and a
 *    restore need `investigate`,
 *    a rename `share_case`, a removal `remove_case` and a new case `create_case`; without it, 403
 *    `{"detail": {"error": "right_required", "right": <right>}}`;
 *  - then the case's gate (`_authorized_at`): a case that does not exist, one of another unit and one the reader holds no level on are
 *    the same 404 `{"error": "investigation_not_found"}`; a level too low for the route is 403 (a rename and a removal need Author, a
 *    restore Editor; every read Viewer);
 *  - a rename, a removal or a restore that passes all of these is NOT modelled (no page makes one yet): 500, recorded, so a later write
 *    slice has to teach it the real answers and cannot lean on a made-up one.
 * What it sends, as the route's models do: `InvestigationListing` rows for the list, in the store's order (the fixture's own order of
 * cases), and only the reader's unit's cases they hold a level on (`list_for`); `Investigation` for a case (no `domains_chosen`: it is
 * `exclude=True`); `CaseBrief` for the brief, with **every attachment this reader may not read left out** (`case_brief.py`, rule 3), as
 * the store's title resolver does; `HistoryStepSummary` rows for the history, in the case's own order (`list_steps`: `ORDER BY seq ASC`), each
 * stored label that is not one the route shows sent as `Changed` (`history.py`), and `restorable` false for a brief edit and true
 * otherwise (`NOT_RESTORABLE`, read from the label sent), with no size, count or body. A test can make each route fail (`list_answer`,
 * `case_answer`, `brief_answer`, `history_answer`, `*_no_answer`).
 *
 * **A new case** (slice GR1b; `create_investigation`, `POST /v1/investigations`), refused in the real route's order:
 *  1. who the bearer is (401), then the right to make a case (403 `right_required`, `create_case`);
 *  2. the body against `CreateInvestigationInput`, as FastAPI refuses it (422 with a `detail` list): `name` a string or null,
 *     `dataset_ids` a list of strings or null, `new_dataset_name` a string of at most 200 characters or null, `domains` a list of the
 *     three packs or null. A field the model does not have is ignored, as pydantic ignores it;
 *  3. then the handler's three dataset rules, each the very same `422 {"error": "dataset_refused"}` with no detail: not exactly one of
 *     `dataset_ids` (one id) and `new_dataset_name` (stripped, not empty); a named dataset that is not one the creator's unit offers;
 *     a new name the unit already has (case and spacing aside). **The new dataset is made before the case**, so a refusal leaves neither.
 * A case it makes is kept: `name` as sent, or `Untitled case`; the creator is its Author; it reads the one dataset; its packs are those
 * sent, unless its dataset has a live model (`live_packs`), whose packs it then shows. `201` with the `Investigation`.
 *
 * **The new case's reads:** `GET /v1/me/rights` (`RightsResponse`, the reader's rights sorted) and `GET /v1/datasets` (the `Dataset`
 * rows the reader's unit offers, by name: never an analyst layer or a drawn dataset, and none to a reader holding no right).
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

/** One stored step of a case's history: its label as the store holds it (which may be an old numbered one the route rewrites). */
export interface Step {
  id: string;
  label: string;
  created_at: string;
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
  /** The case's steps, in the store's order (`seq`); absent, none. */
  history?: Step[];
}

/** A dataset of the fixture's store. `live_packs` set: it has a live domain model, whose packs a case reading it shows. */
export interface UnitDataset {
  id: string;
  name: string;
  owning_unit: string;
  kind?: "source" | "composite" | "drawn" | "analyst_layer";
  members?: string[];
  live_packs?: ("fibo" | "niem" | "stix")[];
}

export interface Call {
  method: string;
  url: string;
  headers: IncomingHttpHeaders;
  /** The body as it arrived, as text: empty for a read. */
  body: string;
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
  history_answer?: Canned;
  list_no_answer?: boolean;
  history_no_answer?: boolean;
  case_no_answer?: boolean;
  brief_no_answer?: boolean;
  /** The store's datasets: those a new case may name, and the names a new dataset may not take. */
  datasets?: UnitDataset[];
  rights_answer?: Canned;
  datasets_answer?: Canned;
  create_answer?: Canned;
  rights_no_answer?: boolean;
  datasets_no_answer?: boolean;
  /** The connection is cut after the create's call has arrived: no answer. */
  create_no_answer?: boolean;
}

export interface CasesConduit {
  url: string;
  calls: Call[];
  /** The store as it stands: what a write made is here, newest first among the cases. */
  cases: Case[];
  datasets: UnitDataset[];
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

/** The labels the route sends as stored (`history_labels.py`'s `FIXED_LABELS` and `CHANGED`; `test_govuk_cases_scenario.py` holds this
 * list to that file): any other stored label is sent as `Changed`. Written out here, not imported from the page, so the page and the
 * fixture cannot agree by construction. */
export const SHOWN_LABELS = ["Seeded", "Expanded", "Showed links among the view", "Removed", "Ran a starter question", "Showed two who share contacts", "Opened from an alert", "Showed an ownership structure", "Opened an alert", "Edited the brief", "Changed"];
/** `NOT_RESTORABLE`: a step that holds no canvas snapshot. */
export const NOT_RESTORABLE = ["Edited the brief"];

/** What the Conduit sends for a case's history (`list[HistoryStepSummary]`): metadata only, a label it does not show as `Changed`. */
export const historyOf = (c: Case): Record<string, unknown>[] =>
  (c.history ?? []).map((s) => {
    const label = SHOWN_LABELS.includes(s.label) ? s.label : "Changed";
    return { id: s.id, label, created_at: s.created_at, restorable: !NOT_RESTORABLE.includes(label) };
  });

/** What `GET /v1/datasets` sends for one dataset (`Dataset`). */
export const datasetOf = (d: UnitDataset): Record<string, unknown> => ({
  id: d.id,
  name: d.name,
  owning_unit: d.owning_unit,
  created_at: "2026-09-01T08:00:00Z",
  created_by: "acct-dataset",
  egress: "none",
  kind: d.kind ?? "source",
  members: d.members ?? [],
  layer_of: null,
  highest_marking: null,
  promotion_policy: "author_promotes",
});

export const DATASET_REFUSED = { error: "dataset_refused" };
const KNOWN_PACKS: readonly unknown[] = ["fibo", "niem", "stix"];
/** `name_key` (`services/api/datasets.py`): what two names must differ in, case and spacing aside. */
const nameKey = (name: string): string => name.trim().split(/\s+/).join(" ").toLowerCase();

interface NewCase {
  name: string | null;
  dataset_ids: string[] | null;
  new_dataset_name: string | null;
  domains: Case["domains"] | null;
}

/** The body against `CreateInvestigationInput`: the model's fields, or FastAPI's list of what is wrong with them. */
function bodyOf(sent: unknown): { body: NewCase } | { wrong: unknown[] } {
  if (typeof sent !== "object" || sent === null || Array.isArray(sent)) return { wrong: [{ type: "model_attributes_type", loc: ["body"] }] };
  const from = sent as Record<string, unknown>;
  const wrong: unknown[] = [];
  const text = (field: string): string | null => {
    const value = from[field] ?? null;
    if (value !== null && typeof value !== "string") wrong.push({ type: "string_type", loc: ["body", field] });
    return typeof value === "string" ? value : null;
  };
  const name = text("name");
  const newName = text("new_dataset_name");
  if (newName !== null && [...newName].length > 200) wrong.push({ type: "string_too_long", loc: ["body", "new_dataset_name"] });
  const ids = from["dataset_ids"] ?? null;
  if (ids !== null && !(Array.isArray(ids) && (ids as unknown[]).every((id) => typeof id === "string"))) wrong.push({ type: "list_type", loc: ["body", "dataset_ids"] });
  const domains = from["domains"] ?? null;
  if (domains !== null && !Array.isArray(domains)) wrong.push({ type: "list_type", loc: ["body", "domains"] });
  if (Array.isArray(domains)) {
    (domains as unknown[]).forEach((pack, i) => {
      if (!KNOWN_PACKS.includes(pack)) wrong.push({ type: "literal_error", loc: ["body", "domains", i] });
    });
  }
  if (wrong.length > 0) return { wrong };
  return { body: { name, dataset_ids: ids as string[] | null, new_dataset_name: newName, domains: domains as Case["domains"] | null } };
}

const RANK: Record<Level, number> = { viewer: 1, editor: 2, author: 3 };

export async function casesConduit(options: CasesConduitOptions): Promise<CasesConduit> {
  const calls: Call[] = [];
  const cases: Case[] = [...options.cases];
  const datasets: UnitDataset[] = [...(options.datasets ?? [])];
  let made = 0;
  const server: Server = createServer((req, res) => {
    const url = req.url ?? "/";
    const call: Call = { method: req.method ?? "", url, headers: req.headers, body: "" };
    calls.push(call);
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      call.body = Buffer.concat(chunks).toString("utf8");
      answer(req, res, url, call.body);
    });
  });
  /** What the creator's unit offers a new case (`list_for`): no drawn dataset and no analyst layer, by name. */
  const offeredTo = (reader: Reader): UnitDataset[] =>
    reader.rights.length === 0
      ? []
      : datasets
          .filter((d) => d.owning_unit === reader.unit && d.kind !== "drawn" && d.kind !== "analyst_layer")
          .sort((a, b) => (a.name < b.name ? -1 : 1));
  /** `create_investigation`'s own handler, after the right and the body: its dataset rules, the dataset made before the case. */
  const create = (reader: Reader, body: NewCase, send: (status: number, answered: unknown) => void): void => {
    const named = [...new Set(body.dataset_ids ?? [])];
    const newName = (body.new_dataset_name ?? "").trim();
    if ((named.length > 0) === (newName !== "") || named.length > 1) return send(422, DATASET_REFUSED);
    let read: UnitDataset;
    if (named.length > 0) {
      const own = offeredTo(reader).find((d) => d.id === named[0]);
      if (!own) return send(422, DATASET_REFUSED);
      read = own;
    } else {
      const taken = datasets.some((d) => d.owning_unit === reader.unit && d.kind !== "analyst_layer" && nameKey(d.name) === nameKey(newName));
      if (taken) return send(422, DATASET_REFUSED);
      read = { id: `ds-made-${datasets.length}`, name: newName, owning_unit: reader.unit };
      datasets.push(read);
    }
    made += 1;
    const found: Case = {
      id: `c-made-${made}`,
      name: body.name || "Untitled case",
      created_at: "2026-11-27T10:00:00Z",
      created_by: "acct-made",
      owning_unit: reader.unit,
      domains: read.live_packs ?? body.domains ?? [],
      datasets: [{ id: read.id, name: read.name }],
      brief: { priority: "", requirements: [] },
    };
    cases.unshift(found);
    reader.levels = { ...reader.levels, [found.id]: "author" };
    send(201, investigationOf(found));
  };
  const answer = (req: IncomingMessage, res: ServerResponse, url: string, sent: string): void => {
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
    // The real server decodes the path before its router sees it (uvicorn's `scope["path"]`), so an encoded slash IS a slash there:
    // `/v1/investigations/<id>%2Fbrief` is the brief's route, not a case whose id holds a slash. The fixture routes on the same path.
    const path = decodeURIComponent(url.split("?")[0] ?? "");
    const method = req.method ?? "";
    /** Who the bearer is, or `undefined` once the 401 has been sent. */
    const bearerOf = (): Reader | undefined => {
      const header = req.headers["authorization"];
      const token = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
      if (token === undefined) {
        send(401, { detail: "Not authenticated" });
        return undefined;
      }
      const reader = options.readers.find((r) => r.token === token);
      if (!reader) send(401, { detail: UNKNOWN_BEARER });
      return reader;
    };
    if (path === "/v1/me/rights") {
      if (method !== "GET") return send(405, { detail: "Method Not Allowed" });
      const reader = bearerOf();
      if (!reader) return;
      return canned(options.rights_answer, options.rights_no_answer, () => send(200, { rights: [...reader.rights].sort() }));
    }
    if (path === "/v1/datasets") {
      // The real route serves GET and POST (a new dataset); no page posts it, so a POST is not modelled.
      if (method === "POST") return send(500, { detail: "the fixture Conduit does not model a successful write" });
      if (method !== "GET") return send(405, { detail: "Method Not Allowed" });
      const reader = bearerOf();
      if (!reader) return;
      return canned(options.datasets_answer, options.datasets_no_answer, () => send(200, offeredTo(reader).map(datasetOf)));
    }
    // The router answers first, as FastAPI's does.
    if (/^\/v1\/investigations\/[^/]+\/.+$/.test(path) && !/^\/v1\/investigations\/[^/]+\/(?:brief|history(?:\/[^/]+)?)$/.test(path)) {
      return send(500, { detail: "the fixture Conduit does not model this route of a case" });
    }
    const match = /^\/v1\/investigations(?:\/([^/]+)(\/brief|\/history(\/[^/]+)?)?)?$/.exec(path);
    if (!match) return send(404, { detail: "Not Found" });
    const id = match[1];
    const route = id === undefined ? "list" : match[2] === undefined ? "case" : match[2] === "/brief" ? "brief" : match[3] === undefined ? "history" : "restore";
    const methods: Record<string, string[]> = { list: ["GET", "POST"], case: ["GET", "PATCH", "DELETE"], brief: ["GET"], history: ["GET"], restore: ["POST"] };
    if (!(methods[route] as string[]).includes(method)) return send(405, { detail: "Method Not Allowed" });
    const reader = bearerOf();
    if (!reader) return;
    // A route-level right, before the case's gate.
    const right = route === "brief" || route === "history" || route === "restore" ? "investigate" : route === "list" && method === "POST" ? "create_case" : method === "PATCH" ? "share_case" : method === "DELETE" ? "remove_case" : undefined;
    if (right !== undefined && !reader.rights.includes(right)) return send(403, rightRefusal(right));
    if (route === "list") {
      if (method === "POST") {
        return canned(options.create_answer, options.create_no_answer, () => {
          let json: unknown;
          try {
            json = JSON.parse(sent);
          } catch {
            return send(422, { detail: [{ type: "json_invalid", loc: ["body", 0] }] });
          }
          if (!/^application\/json\b/.test(String(req.headers["content-type"]))) return send(422, { detail: [{ type: "model_attributes_type", loc: ["body"] }] });
          const read = bodyOf(json);
          if ("wrong" in read) return send(422, { detail: read.wrong });
          create(reader, read.body, send);
        });
      }
      return canned(options.list_answer, options.list_no_answer, () =>
        send(200, cases.filter((c) => c.owning_unit === reader.unit && reader.levels[c.id] !== undefined).map((c) => listingOf(c, reader))),
      );
    }
    // The case's gate: no such case, another unit, no level: one 404.
    const found = cases.find((c) => c.id === id);
    const level = found ? reader.levels[found.id] : undefined;
    if (!found || found.owning_unit !== reader.unit || level === undefined) return send(404, NOT_FOUND_CASE);
    const needed: Level = method === "GET" ? "viewer" : route === "restore" ? "editor" : "author";
    if (RANK[level] < RANK[needed]) return send(403, { detail: `this needs the ${needed} level on the case` });
    if (method !== "GET") return send(500, { detail: "the fixture Conduit does not model a successful write" });
    if (route === "case") return canned(options.case_answer, options.case_no_answer, () => send(200, investigationOf(found)));
    if (route === "history") return canned(options.history_answer, options.history_no_answer, () => send(200, historyOf(found)));
    return canned(options.brief_answer, options.brief_no_answer, () => send(200, briefOf(found, reader)));
  };
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    url: `http://127.0.0.1:${port}`,
    calls,
    cases,
    datasets,
    stop: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}
