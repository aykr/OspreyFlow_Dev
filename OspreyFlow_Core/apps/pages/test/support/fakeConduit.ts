/**
 * A fake Conduit for the Studio pages' tests (slice IS5a): a real HTTP server on a free port that RECORDS every call and
 * REFUSES what the real Conduit refuses (rule 15: a fake that only grants proves the page agrees with our hopes).
 *
 * What it refuses, as `services/api/app.py` does:
 *  - every `/v1` route: no `Authorization: Bearer`, or a bearer it does not know, is 401 `{"detail": ...}`; a token in the
 *    query is ignored, so refused as missing;
 *  - a dataset or a case the person's own cases do not read is 404 `{"detail": "Not Found"}`, whatever the person's rights
 *    (the Conduit answers a thing a person may not see exactly as one that does not exist);
 *  - the release routes need rights: export `edit_target_model` and `publish_pipelines`, import `edit_target_model` and
 *    `edit_pipelines`: 403 `{"detail": ...}` with the right named, which the page must never show;
 *  - the release routes' parameters: `name` and `version` are required (FastAPI's own 422, `detail` a list); the name is a
 *    Kubernetes name; `dry_run` is `true` or `false`; `replace_own_draft` is a whole number; the body is JSON with `files`
 *    an object of text (422, `detail` a list);
 *  - an import into a composite or a drawn dataset is 409 with a string `detail` (`composite_read_only`, `drawn_not_loaded`),
 *    after the rights; the export has no such refusal;
 *  - the export's `name` is 1 to 253 characters and `version` 1 to 64: more or fewer is FastAPI's 422, `detail` a list;
 *  - an import with no `release.yaml` is 422 with the plan's `refused` words, as a refused plan comes back.
 */
import { createServer } from "node:http";
import type { IncomingHttpHeaders, IncomingMessage, Server, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export interface CaseRow {
  id: string;
  name: string;
  level: "viewer" | "editor" | "author";
  created_at: string;
  created_by: string;
  domains?: string[];
  datasets?: string[];
  dataset_ids?: string[];
}

export interface Person {
  /** The bearer this person's sessions carry. */
  token: string;
  rights: string[];
  /** The role ids the Conduit resolved for this person (`GET /v1/me`). */
  roles?: string[];
  cases: CaseRow[];
  /** The proposals the Conduit counts for this person, as it counted them (never above their clearance). */
  proposals?: { dataset_id: string; dataset_name: string; to_decide: number }[];
  pipelines?: Record<string, unknown>[];
  runs?: Record<string, unknown[]>;
  sources?: Record<string, unknown>[];
  /** The version of this person's own in-progress model draft: an import refuses to replace it until confirmed. */
  ownDraft?: number;
  /**
   * Datasets the person's cases list but the Conduit will no longer open for them (their access changed since the list was
   * read): its dataset routes answer 404 for these, exactly as for a dataset that does not exist.
   */
  datasetsDenied?: string[];
  /** Published pipelines the export left out as marked above what the person may view. */
  leftOut?: number;
  /**
   * What kind of dataset the person's case loads into, when it is not an ordinary one: the real import route refuses a
   * composite (`composite_read_only`) and a drawn dataset (`drawn_not_loaded`) with a 409 whose `detail` is words, after the
   * dataset's own gate and the rights (`refuse_loading_a_composite`, `services/api/app.py`).
   */
  datasetKind?: "composite" | "drawn";
}

/** The words the real Conduit sends with those 409s, as `dataset_scope.py` and `app.py` word them (the composite named: past the gate). */
export const COMPOSITE_WORDS = "This is the composite “Harbour prison extract (synthetic)”, which is read-only for now: do this in a case that reads that dataset.";
export const DRAWN_WORDS =
  "a drawn dataset is drawn on its board, not loaded: nothing is loaded or run into it, and it reaches another dataset by being merged into it";

export interface Seen {
  method: string;
  /** The request target as it reached the fake. */
  url: string;
  path: string;
  query: URLSearchParams;
  headers: IncomingHttpHeaders;
  rawHeaders: string[];
  body: string;
}

export interface FakeConduit {
  url: string;
  calls: Seen[];
  /** What the fake wrote as imported (dry_run=false), by dataset. */
  written: { dataset: string; files: Record<string, string>; replace: string | null }[];
  /** A route's path fragment that answers 500, to model a failing read. */
  failing: Set<string>;
  /** A next real import answers 422 with these words (a draft someone opened since the check). */
  refuseNextWrite: string[] | undefined;
  people: Map<string, Person>;
  stop(): Promise<void>;
}

export const EXPORT_FILES = {
  "release.yaml": "apiVersion: ospreyflow.io/v1\n",
  "model.yaml": "packs: {}\n",
  "pipelines/visits.yaml": "name: visits\n",
};
const K8S_NAME = /^[a-z0-9][a-z0-9.-]*$/;

function read(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
  });
}

function json(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

const missing = (where: string[]): unknown => ({
  detail: where.map((field) => ({ type: "missing", loc: ["query", field], msg: "Field required" })),
});

export async function fakeConduit(people: Person[]): Promise<FakeConduit> {
  const fake: FakeConduit = {
    url: "",
    calls: [],
    written: [],
    failing: new Set(),
    refuseNextWrite: undefined,
    people: new Map(people.map((p) => [p.token, p])),
    stop: () => new Promise((resolve) => server.close(() => resolve())),
  };

  const handle = async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
    const target = new URL(req.url ?? "/", "http://conduit.test");
    const body = await read(req);
    fake.calls.push({
      method: req.method ?? "GET",
      url: req.url ?? "",
      path: target.pathname,
      query: target.searchParams,
      headers: req.headers,
      rawHeaders: req.rawHeaders,
      body,
    });
    const header = req.headers["authorization"];
    const bearer = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
    const person = bearer === undefined ? undefined : fake.people.get(bearer);
    if (!person) {
      json(res, 401, { detail: "Not authenticated" });
      return;
    }
    for (const fragment of fake.failing) {
      if (target.pathname.includes(fragment)) {
        json(res, 500, { detail: "Internal Server Error" });
        return;
      }
    }
    const path = target.pathname;
    const method = req.method ?? "GET";
    const visibleCase = (id: string): CaseRow | undefined => person.cases.find((c) => c.id === id);
    const visibleDataset = (id: string): boolean =>
      !(person.datasetsDenied ?? []).includes(id) && person.cases.some((c) => c.dataset_ids?.includes(id));
    const has = (...rights: string[]): boolean => rights.every((r) => person.rights.includes(r));

    if (path === "/v1/me" && method === "GET") {
      return json(res, 200, { id: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-1", roles: person.roles ?? [], receivable_handling_codes: [] });
    }
    if (path === "/v1/me/rights" && method === "GET") return json(res, 200, { rights: [...person.rights].sort() });
    if (path === "/v1/investigations" && method === "GET") return json(res, 200, person.cases);
    if (path === "/v1/me/needs-you" && method === "GET") {
      return json(res, 200, {
        promotions_overdue: [],
        proposals: person.proposals ?? [],
        schedule_notices: [],
        schedule_notices_total: 0,
      });
    }
    let found = /^\/v1\/investigations\/([^/]+)\/ingest\/recipe-registry$/.exec(path);
    if (found && method === "GET") {
      if (!visibleCase(decodeURIComponent(found[1] as string))) return json(res, 404, { detail: "Not Found" });
      return json(res, 200, person.pipelines ?? []);
    }
    found = /^\/v1\/investigations\/([^/]+)\/ingest\/recipes\/([^/]+)\/runs$/.exec(path);
    if (found && method === "GET") {
      if (!visibleCase(decodeURIComponent(found[1] as string))) return json(res, 404, { detail: "Not Found" });
      return json(res, 200, person.runs?.[decodeURIComponent(found[2] as string)] ?? []);
    }
    found = /^\/v1\/datasets\/([^/]+)\/sources$/.exec(path);
    if (found && method === "GET") {
      if (!visibleDataset(decodeURIComponent(found[1] as string))) return json(res, 404, { detail: "Not Found" });
      return json(res, 200, person.sources ?? []);
    }
    found = /^\/v1\/datasets\/([^/]+)\/release$/.exec(path);
    if (found && method === "GET") {
      const dataset = decodeURIComponent(found[1] as string);
      if (!visibleDataset(dataset)) return json(res, 404, { detail: "Not Found" });
      if (!has("edit_target_model", "publish_pipelines")) {
        return json(res, 403, { detail: "Missing right: edit_target_model, publish_pipelines" });
      }
      const name = target.searchParams.get("name");
      const version = target.searchParams.get("version");
      const absent = [name === null ? "name" : "", version === null ? "version" : ""].filter(Boolean);
      if (absent.length > 0) return json(res, 422, missing(absent));
      if ((name as string).length < 1 || (name as string).length > 253 || (version as string).length < 1 || (version as string).length > 64) {
        return json(res, 422, {
          detail: [{ type: "string_too_long", loc: ["query", (name as string).length > 253 ? "name" : "version"], msg: "String should have at most 253 characters" }],
        });
      }
      if (!K8S_NAME.test(name as string)) {
        return json(res, 422, { error: "release_refused", problems: [`the release name "${name}" is not a name Kubernetes takes`] });
      }
      return json(res, 200, { files: EXPORT_FILES, left_out: person.leftOut ?? 0 });
    }
    found = /^\/v1\/datasets\/([^/]+)\/release\/import$/.exec(path);
    if (found && method === "POST") {
      const dataset = decodeURIComponent(found[1] as string);
      if (!visibleDataset(dataset)) return json(res, 404, { detail: "Not Found" });
      if (!has("edit_target_model", "edit_pipelines")) {
        return json(res, 403, { detail: "Missing right: edit_target_model, edit_pipelines" });
      }
      if (person.datasetKind === "composite") {
        return json(res, 409, { error: "composite_read_only", detail: COMPOSITE_WORDS });
      }
      if (person.datasetKind === "drawn") return json(res, 409, { error: "drawn_not_loaded", detail: DRAWN_WORDS });
      const dry = target.searchParams.get("dry_run");
      if (dry !== "true" && dry !== "false") return json(res, 422, missing(["dry_run"]));
      const replace = target.searchParams.get("replace_own_draft");
      if (replace !== null && !/^\d+$/.test(replace)) {
        return json(res, 422, { detail: [{ type: "int_parsing", loc: ["query", "replace_own_draft"], msg: "not an integer" }] });
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(body);
      } catch {
        parsed = undefined;
      }
      const files = (parsed as { files?: unknown } | undefined)?.files;
      if (
        typeof files !== "object" ||
        files === null ||
        Object.values(files).some((text) => typeof text !== "string")
      ) {
        return json(res, 422, { detail: [{ type: "missing", loc: ["body", "files"], msg: "Field required" }] });
      }
      const bundle = files as Record<string, string>;
      const dryRun = dry === "true";
      if (!("release.yaml" in bundle)) {
        return json(res, 422, { dry_run: dryRun, items: [], refused: ["release.yaml is missing from the folder"], missing_connections: [], notes: [] });
      }
      if (person.ownDraft !== undefined && replace !== String(person.ownDraft)) {
        return json(res, 422, {
          dry_run: dryRun,
          items: [],
          refused: [`the domain model has your own in-progress draft (version ${person.ownDraft}): importing replaces it`],
          missing_connections: [],
          notes: [],
          replaces_own_draft: true,
          own_draft_version: person.ownDraft,
        });
      }
      if (!dryRun && fake.refuseNextWrite) {
        const words = fake.refuseNextWrite;
        fake.refuseNextWrite = undefined;
        return json(res, 422, { dry_run: false, items: [], refused: words, missing_connections: [], notes: [], replaces_own_draft: false });
      }
      if (!dryRun) fake.written.push({ dataset, files: bundle, replace });
      const items: { role: string; name: string; action: string }[] = [
        { role: "pipeline", name: "Wing phone calls", action: person.ownDraft === undefined ? "new_draft" : "replaces_draft" },
      ];
      return json(res, 200, {
        dry_run: dryRun,
        items,
        refused: [],
        missing_connections: dryRun ? ["warehouse-read"] : [],
        notes: dryRun ? ["the release was made for version 1"] : [],
        replaces_own_draft: person.ownDraft !== undefined,
        ...(person.ownDraft === undefined ? {} : { own_draft_version: person.ownDraft }),
      });
    }
    return json(res, 404, { detail: "Not Found" });
  };

  const server: Server = createServer((req, res) => {
    handle(req, res).catch(() => {
      if (!res.headersSent) json(res, 500, { detail: "fake failed" });
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
  fake.url = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  return fake;
}
