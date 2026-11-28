/**
 * A fixture Conduit for the boards page (slice GG4a): a real HTTP server on a free port that RECORDS every call and REFUSES what the real
 * routes refuse (rule 15: a fixture that only grants proves the page agrees with our hopes). Synthetic throughout (rule 9).
 *
 * What it refuses, in the real routes' order (`services/api/app.py`, `services/api/boards.py`):
 *  - the router first, for anyone, on the path as the Conduit's server gives it to the router: decoded first, so a `%2F` in a segment is
 *    a slash and the path another route (uvicorn decodes the path before Starlette matches it). A path it has not is 404 `{"detail": "Not Found"}`, a method the path does not serve is 405
 *    `{"detail": "Method Not Allowed"}`. The methods are the real routes': `.../boards` GET and POST (a new board), `.../boards/{id}` GET
 *    and DELETE, `.../boards/{id}/share` POST, and `/v1/me/rights` GET (any signed-in person: the rights they hold, sorted). Every other
 *    path under a case or a board (`/views`, `/brief`, `/drawn-watches`, `/boards/{id}/items`, `/layout`, `/pictures`, `/matches` and the
 *    rest the real Conduit serves) is NOT modelled: 500, recorded, never a 404 the real router would not give;
 *  - then who the bearer is: none is 401 `{"detail": "Not authenticated"}`; one it does not know is 401 with the resolver's own reason;
 *  - then the route-level rights (`_READS_BOARDS`, `_DRAWS`, run before the case's gate): reading needs `investigate`; a new board and a
 *    removal need `draw_on_boards` and `investigate`; without one, 403 `{"detail": {"error": "right_required", "right": <right>}}`;
 *  - then the case's gate (`InvestigationViewerDep`): a case that does not exist, one of another unit and one the reader holds no level
 *    on are the same 404 `{"error": "investigation_not_found"}`; a write's gate is Editor (`InvestigationEditorDep`), and a Viewer
 *    (`viewerCases`) is 403 with the gate's own sentence;
 *  - then a new board's body, as FastAPI refuses it after the dependencies (`BoardInput`, `extra="forbid"`): a body that is not JSON, a
 *    field the model has not (`_csrf` among them), a name that is missing, not text, empty or over 200 characters (code points), a start
 *    that is none, or one that disagrees with its fields: 422, FastAPI's shape, `loc` naming the field (FastAPI refuses bytes that are not JSON before it asks any dependency; the
 *    page sends only JSON, so that order is not modelled);
 *  - then the board (`Boards.board`): someone else's private board, another case's, and none at all are the same 404
 *    `{"error": "board_not_found"}`; then, for a share and a removal, its creator (`Boards.own_board`): anyone else is 403
 *    `not_the_boards_creator`;
 *  - past the working-set cap (`cap` on the nodes, `capEdges` on the links, when given), the open is the typed 409 `limit_exceeded`
 *    (`LimitExceeded`), never a part of the board;
 *  - a write that passes all of these is carried out in the fixture's own world and recorded as one audit row, as the route writes one
 *    (`_audit_board`): a blank board (201, `Board`), a share (200, `Board`), a removal (204, no body; the drawn items stay in `items`).
 *    A board made from a view or a selection is NOT modelled: 500, recorded.
 * What it sends, as the routes do: the list is the case's boards the reader may see (their own, and the shared), in the fixture's own
 * order (`boards` as given: the real store sends oldest first, and a page that sorted would show), each wired as `Boards.wire` wires it:
 * `drawn` the count of the live drawn nodes the reader may see, `start` "selection" when a reference the reader may see is on it and
 * "blank" otherwise. One board is `BoardOpened` with every field: its live drawn items and references **the reader may see by their
 * marking** (the adapter's filter, modelled by the reader's clearance), the links among them the reader may see, `drawn`, `items`, the
 * layout of what is shown, and `missing`, **told to the board's creator alone and counting only references since withdrawn, never what
 * the reader may not see** (`boards.py`, rule 3). A drawn element's `board_id` is given empty to anyone but its author
 * (`packages/ontology/handling.py`, `_board_as_known`). A test can make each route fail (`list_answer`, `board_answer`,
 * `rights_answer`, `write_answer`, `*_no_answer`).
 */
import { createServer } from "node:http";
import type { IncomingHttpHeaders, IncomingMessage, Server, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

/** The markings of the fixture's scheme, lowest first: a reader sees what is at or below their clearance. */
export const MARKINGS = ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"] as const;
export type Marking = (typeof MARKINGS)[number];

export interface Reader {
  token: string;
  /** The reader's principal id: a board's `created_by` and a drawn item's `asserted_by`. */
  id: string;
  unit: string;
  rights: string[];
  /** The cases the reader holds a level on, by id (Editor or above, unless named in `viewerCases`). */
  cases: string[];
  /** Of `cases`, those the reader holds only the Viewer level on: reading, never a write. */
  viewerCases?: string[];
  clearance: Marking;
}

export interface Case {
  id: string;
  owning_unit: string;
}

export interface Assertion {
  label: string;
  grading: { scheme: string; source: string; intelligence: string; handling: string };
  source_note: string | null;
  source_document: string | null;
  asserted_by: string;
  item_id: string;
  board_id: string;
}

export interface Item {
  id: string;
  type: string;
  properties: Record<string, unknown>;
  marking: Marking;
  /** Set on a drawn item; absent on a loaded one. */
  drawn?: Assertion;
  /** A drawn item withdrawn by its author: never sent again (kept in the audit). Only a drawn item is withdrawn: `boardsConduit` refuses
   * to start with a loaded item marked so, since the real route has no such state. */
  withdrawn?: boolean;
}

export interface Link {
  id: string;
  type: string;
  source: string;
  target: string;
  marking: Marking;
  drawn?: Assertion;
  withdrawn?: boolean;
}

export interface Board {
  id: string;
  case_id: string;
  name: string;
  created_by: string;
  created_at: string;
  shared: boolean;
  /** Its references: loaded items, or drawn items of another board, placed on it when it was made. */
  references: string[];
  /** The drawn items drawn on it, by element id. */
  drawn: string[];
}

export interface Call {
  method: string;
  url: string;
  headers: IncomingHttpHeaders;
  /** What was sent, as sent. */
  body: string;
}

/** One audit row of a write the fixture carried out, as the route records one. */
export interface Audit {
  action: "make_board" | "share_board" | "delete_board";
  board_id: string;
  start?: string;
}

export interface Canned {
  status: number;
  body: unknown;
}

export interface BoardsConduitOptions {
  readers: Reader[];
  cases: Case[];
  boards: Board[];
  items: Item[];
  links: Link[];
  /** The working-set cap on the nodes of an open, when the test wants it reached. */
  cap?: number;
  /** The working-set cap on the links of an open. */
  capEdges?: number;
  list_answer?: Canned;
  board_answer?: Canned;
  rights_answer?: Canned;
  /** What a write that would be carried out answers instead (nothing is carried out and nothing audited). */
  write_answer?: Canned;
  list_no_answer?: boolean;
  board_no_answer?: boolean;
  rights_no_answer?: boolean;
  write_no_answer?: boolean;
}

export interface BoardsConduit {
  url: string;
  calls: Call[];
  audits: Audit[];
  stop(): Promise<void>;
}

export const NOT_FOUND_CASE = { error: "investigation_not_found" };
export const NOT_FOUND_BOARD = { error: "board_not_found" };
/** The resolver's reason for a bearer it does not know: one of its own sentences (`packages/principal_auth`), standing for all. */
export const UNKNOWN_BEARER = "token is missing required claim: subject ('sub')";
export const rightRefusal = (right: string): unknown => ({ detail: { error: "right_required", right } });
/** The case's gate refusing a level too low (`InsufficientAccessError`'s own sentence, as the detail). */
export const LEVEL_REFUSAL = { detail: "editor access is needed on this case; this account has viewer" };
export const NOT_CREATOR = {
  error: "not_the_boards_creator",
  detail: "Only the person who made this board draws on it. Make a board of your own from this one's view to draw.",
};

/** What FastAPI sends for a new board's body `BoardInput` refuses, or `undefined` when it takes it. */
export function boardInputRefusal(contentType: string | undefined, sent: string): { status: 422; body: unknown } | undefined {
  const refuse = (type: string, loc: string[], msg: string) => ({ status: 422 as const, body: { detail: [{ type, loc: ["body", ...loc], msg }] } });
  let body: unknown;
  try {
    body = JSON.parse(sent);
  } catch {
    return refuse("json_invalid", [], "JSON decode error");
  }
  if (!/^application\/json\b/i.test(contentType ?? "") || typeof body !== "object" || body === null || Array.isArray(body)) {
    return refuse("model_attributes_type", [], "Input should be a valid dictionary or object to extract fields from");
  }
  const given = body as Record<string, unknown>;
  const extra = Object.keys(given).find((key) => !["name", "start", "view_id", "node_ids"].includes(key));
  if (extra !== undefined) return refuse("extra_forbidden", [extra], "Extra inputs are not permitted");
  const name = given["name"];
  if (name === undefined) return refuse("missing", ["name"], "Field required");
  if (typeof name !== "string") return refuse("string_type", ["name"], "Input should be a valid string");
  // Pydantic counts characters (code points), not UTF-16 units.
  if ([...name].length < 1) return refuse("string_too_short", ["name"], "String should have at least 1 character");
  if ([...name].length > 200) return refuse("string_too_long", ["name"], "String should have at most 200 characters");
  const start = given["start"] ?? "blank";
  if (start !== "blank" && start !== "view" && start !== "selection") return refuse("literal_error", ["start"], "Input should be 'blank', 'view' or 'selection'");
  const view = given["view_id"] ?? null;
  const nodes = given["node_ids"] ?? null;
  if (start === "blank" && (view !== null || nodes !== null)) return refuse("value_error", [], "Value error, a blank board starts from nothing");
  if (start === "view" && view === null) return refuse("value_error", [], "Value error, a board from a view names the view");
  if (start === "selection" && nodes === null) return refuse("value_error", [], "Value error, a board from a selection names what is selected");
  return undefined;
}

const AT = "2026-11-02T08:00:00Z";
const clears = (reader: Reader, marking: Marking): boolean => MARKINGS.indexOf(marking) <= MARKINGS.indexOf(reader.clearance);

const handlingOf = (marking: Marking, unit: string): Record<string, unknown> => ({
  classification: marking,
  handling_code: "H1",
  action_code: null,
  sanitisation_code: null,
  originator: unit,
  owning_unit: unit,
  review_date: null,
  legal_basis: null,
});

/** A provenance as the store sends it: a drawn one with its assertion (`Boards._provenance`), a loaded one with its source. */
function provenanceOf(drawn: Assertion | undefined, caseId: string, reader: string): Record<string, unknown> {
  const base = {
    state: "asserted",
    sources: [{ document_id: drawn ? (drawn.source_document ?? `drawn:${drawn.item_id}`) : "doc-ledger", locator: drawn ? "a drawing board of the case" : "row 4", excerpt_hash: "" }],
    sources_withheld: false,
    extracted_by: null,
    extraction_confidence: null,
    first_seen: AT,
    last_confirmed: null,
    confirmed_by: null,
  };
  if (!drawn) return base;
  return {
    ...base,
    drawn: {
      provenance_class: "analyst_drawn",
      item_id: drawn.item_id,
      asserted_by: drawn.asserted_by,
      board_id: drawn.asserted_by === reader ? drawn.board_id : "",
      case_id: caseId,
      label: drawn.label,
      grading: drawn.grading,
      original_grading: null,
      source_note: drawn.source_note,
      source_document: drawn.source_document,
      icon: null,
    },
  };
}

/** What the Conduit sends for a node (`Node`). */
export const nodeOf = (item: Item, caseId: string, unit: string, reader: string): Record<string, unknown> => ({
  id: item.id,
  type: item.type,
  properties: item.properties,
  provenance: provenanceOf(item.drawn, caseId, reader),
  handling: handlingOf(item.marking, unit),
  resolution: { cluster_id: null, cluster_score: null, resolution_run: null, manually_linked: [], manually_split: [] },
  audit: { created_at: AT, created_by: item.drawn?.asserted_by ?? "loader", revision: 1, superseded_by: null, load_id: null, recipe_id: null, recipe_version: null, reverted: false, withdrawn_by_load: null },
  datasets: [item.drawn ? "layer-of-the-case" : "ds-ledger"],
});

/** What the Conduit sends for an edge (`Edge`, without its excluded field). */
export const edgeOf = (link: Link, caseId: string, unit: string, reader: string): Record<string, unknown> => ({
  id: link.id,
  type: link.type,
  source: link.source,
  target: link.target,
  properties: {},
  interval: null,
  occurrences: 1,
  weight: 0,
  basis: null,
  provenance: provenanceOf(link.drawn, caseId, reader),
  handling: handlingOf(link.marking, unit),
  audit: { created_at: AT, created_by: link.drawn?.asserted_by ?? "loader", revision: 1, superseded_by: null, load_id: null, recipe_id: null, recipe_version: null, reverted: false, withdrawn_by_load: null },
  datasets: [link.drawn ? "layer-of-the-case" : "ds-ledger"],
});

/** The board as listed (`Board`), as `Boards.wire` wires it for this reader. */
export function boardOf(board: Board, reader: Reader, options: BoardsConduitOptions): Record<string, unknown> {
  const seen = (id: string): boolean => {
    const item = options.items.find((i) => i.id === id);
    return item !== undefined && item.withdrawn !== true && clears(reader, item.marking);
  };
  const liveDrawn = board.drawn.filter((id) => options.items.find((i) => i.id === id)?.withdrawn !== true);
  return {
    id: board.id,
    case_id: board.case_id,
    name: board.name,
    created_by: board.created_by,
    created_at: board.created_at,
    shared: board.shared,
    drawn: liveDrawn.filter(seen).length,
    start: board.references.some(seen) ? "selection" : "blank",
  };
}

/** One board opened (`BoardOpened`), as `Boards.open` and the route answer it to this reader. */
export function openedOf(board: Board, reader: Reader, options: BoardsConduitOptions, unit: string): Record<string, unknown> {
  const wanted = [...new Set([...board.references, ...board.drawn])];
  const nodes = wanted
    .map((id) => options.items.find((i) => i.id === id))
    .filter((i): i is Item => i !== undefined && i.withdrawn !== true && clears(reader, i.marking));
  const shown = new Set(nodes.map((n) => n.id));
  const edges = shown.size > 1 ? options.links.filter((l) => l.withdrawn !== true && clears(reader, l.marking) && shown.has(l.source) && shown.has(l.target)) : [];
  // Only what was lost, never what the reader was never allowed to see: the board's own references whose drawn item has since been
  // withdrawn, told to the board's creator, who placed each of them seeing it.
  const missing = board.created_by === reader.id ? board.references.filter((id) => { const item = options.items.find((i) => i.id === id); return item?.drawn !== undefined && item.withdrawn === true; }).length : 0;
  const drawn = [...nodes.filter((n) => n.drawn).map((n) => n.id), ...edges.filter((e) => e.drawn).map((e) => e.id)];
  const items = Object.fromEntries([...nodes, ...edges].filter((e) => e.drawn).map((e) => [e.id, (e.drawn as Assertion).item_id]));
  return {
    board: boardOf(board, reader, options),
    nodes: nodes.map((n) => nodeOf(n, board.case_id, unit, reader.id)),
    edges: edges.map((e) => edgeOf(e, board.case_id, unit, reader.id)),
    drawn,
    items,
    layout: Object.fromEntries(nodes.map((n, i) => [n.id, { x: 0.1 * (i + 1), y: 0.5 }])),
    missing,
    node_types: ["Person", "Vessel", "Organisation"],
    link_types: ["KNOWS", "OWNS"],
    markings: MARKINGS.filter((m) => clears(reader, m)),
    ceiling: "SECRET",
    grading_scheme: "5x5x5",
    grading_grades: { scheme: "5x5x5", source: ["A", "B", "C", "D", "E"], intelligence: ["1", "2", "3", "4", "5"], handling: ["1", "2", "3", "4", "5"] },
    may_draw: board.created_by === reader.id && reader.rights.includes("draw_on_boards"),
    may_promote: false,
  };
}

export async function boardsConduit(options: BoardsConduitOptions): Promise<BoardsConduit> {
  const loadedWithdrawn = options.items.find((i) => i.withdrawn === true && i.drawn === undefined);
  if (loadedWithdrawn) throw new Error(`the fixture's ${loadedWithdrawn.id} is a loaded item marked withdrawn, which the real route cannot hold`);
  // The fixture's own copy, which a write changes: the test's constants stay as they were.
  options.boards = options.boards.map((b) => ({ ...b }));
  const calls: Call[] = [];
  const audits: Audit[] = [];
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
    // The path as the router sees it: decoded first (a `%2F` is a slash), as uvicorn gives it to Starlette.
    const path = decodeURIComponent(url.split("?")[0] ?? "");
    const method = req.method ?? "";
    // The router answers first, as FastAPI's does.
    const rightsPath = path === "/v1/me/rights";
    const match = /^\/v1\/investigations\/([^/]+)\/boards(?:\/([^/]+)(\/share)?)?$/.exec(path);
    if (!match && !rightsPath) {
      if (/^\/v1\/investigations(?:\/[^/]+(?:\/.*)?)?$/.test(path)) return send(500, { detail: "the fixture Conduit does not model this route" });
      return send(404, { detail: "Not Found" });
    }
    const caseId = match?.[1] ?? "";
    const boardId = match?.[2];
    const route = rightsPath ? "rights" : match?.[3] !== undefined ? "share" : boardId === undefined ? "list" : "board";
    const methods: Record<string, string[]> = { rights: ["GET"], list: ["GET", "POST"], board: ["GET", "DELETE"], share: ["POST"] };
    if (!(methods[route] as string[]).includes(method)) return send(405, { detail: "Method Not Allowed" });
    const header = req.headers["authorization"];
    const token = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
    if (token === undefined) return send(401, { detail: "Not authenticated" });
    const reader = options.readers.find((r) => r.token === token);
    if (!reader) return send(401, { detail: UNKNOWN_BEARER });
    if (route === "rights") return canned(options.rights_answer, options.rights_no_answer, () => send(200, { rights: [...reader.rights].sort() }));
    // The route-level rights, before the case's gate: a write needs `draw_on_boards` (listed first), and every route `investigate`.
    const rights = method === "GET" ? ["investigate"] : ["draw_on_boards", "investigate"];
    for (const right of rights) if (!reader.rights.includes(right)) return send(403, rightRefusal(right));
    // The case's gate: no such case, another unit, no level: one 404. Then, for a write, a level too low: 403.
    const found = options.cases.find((c) => c.id === caseId);
    if (!found || found.owning_unit !== reader.unit || !reader.cases.includes(found.id)) return send(404, NOT_FOUND_CASE);
    if (method !== "GET" && reader.viewerCases?.includes(found.id) === true) return send(403, LEVEL_REFUSAL);
    const visible = (b: Board): boolean => b.case_id === found.id && (b.shared || b.created_by === reader.id);
    if (route === "list" && method === "GET") {
      return canned(options.list_answer, options.list_no_answer, () => send(200, options.boards.filter(visible).map((b) => boardOf(b, reader, options))));
    }
    if (route === "list") {
      const refused = boardInputRefusal(req.headers["content-type"], sent);
      if (refused) return send(refused.status, refused.body);
      const given = JSON.parse(sent) as { name: string; start?: string };
      const start = given.start ?? "blank";
      if (start !== "blank") return send(500, { detail: "the fixture Conduit does not model a board from a view or a selection" });
      return canned(options.write_answer, options.write_no_answer, () => {
        made += 1;
        const board: Board = { id: `b-made-${made}`, case_id: found.id, name: given.name, created_by: reader.id, created_at: "2026-11-26T10:00:00Z", shared: false, references: [], drawn: [] };
        options.boards.push(board);
        audits.push({ action: "make_board", board_id: board.id, start });
        send(201, boardOf(board, reader, options));
      });
    }
    // The board: someone else's private board, another case's, and none at all alike.
    const board = options.boards.find((b) => b.id === boardId);
    if (!board || !visible(board)) return send(404, NOT_FOUND_BOARD);
    if (method !== "GET") {
      // `own_board`: the board first (above), then its creator.
      if (board.created_by !== reader.id) return send(403, NOT_CREATOR);
      return canned(options.write_answer, options.write_no_answer, () => {
        if (method === "DELETE") {
          options.boards.splice(options.boards.indexOf(board), 1);
          audits.push({ action: "delete_board", board_id: board.id });
          res.statusCode = 204;
          res.end();
          return;
        }
        board.shared = true;
        audits.push({ action: "share_board", board_id: board.id });
        send(200, boardOf(board, reader, options));
      });
    }
    return canned(options.board_answer, options.board_no_answer, () => {
      const opened = openedOf(board, reader, options, found.owning_unit) as { nodes: unknown[]; edges: unknown[] };
      const refusal = (kind: string, cap: number, wouldBe: number): void => send(409, { error: "limit_exceeded", cap_kind: kind, cap, would_be: wouldBe, options: ["save_as_view", "filter", "promote_to_batch"] });
      if (options.cap !== undefined && opened.nodes.length > options.cap) return refusal("nodes", options.cap, opened.nodes.length);
      if (options.capEdges !== undefined && opened.edges.length > options.capEdges) return refusal("edges", options.capEdges, opened.edges.length);
      send(200, opened);
    });
  };
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    url: `http://127.0.0.1:${port}`,
    calls,
    audits,
    stop: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}
