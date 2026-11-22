/**
 * The Studio's dataset map as a server-rendered page, Default tree (slice IS3; ADR-140 Amendment 22 items 1 and 8; ADR-141
 * Amendment 2; ADR-152 decisions 6, 7, 12 and 13; FUNCTIONS row `studio-dataset-map`).
 *
 * There is no React dataset map to read the behaviour from (`FUNCTIONS.yaml` says so), so each case's id is a scenario of
 * `spec/08_ACCEPTANCE_SCENARIOS.md` ("Scenario DM"), written from the ADR text, the prototype's Pipelines list and the owner's
 * ruling of 21 November 2026 ("show the dataset as a table with no 'runs after' column. IS6 adds the column when it stores the
 * order. Do not show an empty column or a suggestion nothing backs"). `tests/glass_trees/test_dataset_map_scenario.py` holds the
 * two in step.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a "runs after" column, an empty column, a suggestion or a line               -> DM2
 *  - a pipeline of another dataset (or one placed in none) in the table          -> DM7
 *  - a count, a name or a title that belongs to what the reader may not see       -> DM8
 *  - "no such dataset" and "not allowed" worded or drawn differently              -> DM8
 *  - a read that failed drawn as an empty table                                   -> DM9
 *  - the Conduit asked with anything of the browser's                             -> DM11
 *  - a control that needs a script, a tab stop above 0, a control with no label  -> DM12
 * The fake Conduit refuses what the real one refuses and scopes the registry as the real route does
 * (`test/support/fakeConduit.ts`, rule 15). Every planted fault is the real page with one thing changed (DM14).
 */
import { afterEach, describe, expect, it } from "vitest";

import { ALL_RIGHTS, CASE_ID, DATASET, DATASET_NAME, caseRow, person, textOf, world } from "../support/studioWorld.js";
import type { World } from "../support/studioWorld.js";
import { request } from "../support/http.js";

const open: World[] = [];
async function make(...args: Parameters<typeof world>): Promise<World> {
  const w = await world(...args);
  open.push(w);
  return w;
}
afterEach(async () => {
  while (open.length > 0) await open.pop()?.stop();
});

const PATH = `/studio/dataset-map?case=${CASE_ID}`;
const REFUSED = "The dataset map is not available to you: it needs rights you do not hold, or the dataset is not one of yours.";
const EMPTY = "No pipeline loads this dataset yet.";
const UNREADABLE = "The pipelines of this dataset could not be read just now. Try again in a few minutes.";

// ------------------------------------------------------------------------------------------------ what a recipe looks like

type Node = { id: string; kind: string; label: string; config: Record<string, unknown> };
const node = (id: string, kind: string, label = id): Node => ({ id, kind, label, config: {} });

const CHAIN = {
  nodes: [node("d", "domain_model"), node("s", "source"), node("p", "profile"), node("m", "map"), node("l", "load")],
  edges: [
    { source: "s", target: "p" },
    { source: "p", target: "m" },
    { source: "d", target: "m" },
    { source: "m", target: "l" },
  ],
};

/** One row of the registry, as `StudioRecipeDraft` serialises it (the fields the page reads, and the ones it must not). */
function recipe(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    recipe_id: "r-visits",
    version: 3,
    status: "published",
    label: "Visits",
    dataset_id: DATASET,
    owning_unit: "unit-1",
    created_by: "analyst-1",
    created_at: "2026-11-02T10:00:00Z",
    source_location: "visits.csv",
    pipeline: CHAIN,
    ...over,
  };
}

// ------------------------------------------------------------------------------------------------ reading a page

const strip = (html: string): string => html.replace(/<!--[\s\S]*?-->/g, "");

/** The Studio's place block: what this page draws beyond the frame. */
function placeOf(html: string): string {
  const found = /<div class="studio-place">([\s\S]*?)<\/div>\s*(?:<\/main>|$)/.exec(strip(html));
  return found ? (found[1] as string) : "";
}

interface Cell {
  tag: "th" | "td";
  attrs: string;
  text: string;
}
interface Table {
  caption: string | null;
  head: Cell[];
  rows: Cell[][];
}

const cellText = (inner: string): string => textOf(inner);

/** The first table of `html`, as the browser would read its cells: the head row, then each body row. Null when there is none. */
function tableOf(html: string): Table | null {
  const found = /<table\b[^>]*>([\s\S]*?)<\/table>/.exec(strip(html));
  if (!found) return null;
  const inner = found[1] as string;
  const caption = /<caption\b[^>]*>([\s\S]*?)<\/caption>/.exec(inner);
  const rowsOf = (part: string): Cell[][] =>
    [...part.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((row) =>
      [...(row[1] as string).matchAll(/<(th|td)\b([^>]*)>([\s\S]*?)<\/\1>/g)].map((c) => ({
        tag: c[1] as "th" | "td",
        attrs: c[2] as string,
        text: cellText(c[3] as string),
      })),
    );
  const head = /<thead\b[^>]*>([\s\S]*?)<\/thead>/.exec(inner);
  const body = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/.exec(inner);
  return {
    caption: caption ? cellText(caption[1] as string) : null,
    head: head ? (rowsOf(head[1] as string)[0] ?? []) : [],
    rows: body ? rowsOf(body[1] as string) : [],
  };
}

const HEADERS = ["Pipeline", "Status", "Version", "Stages"];

/** Every fault in a page's table, in words: the same function reads the real page and each planted one. */
function tableProblems(html: string): string[] {
  const found: string[] = [];
  const table = tableOf(html);
  if (table === null) return ["there is no table"];
  if (!table.caption) found.push("the table has no caption");
  if (table.head.length === 0) found.push("the table has no head row");
  for (const cell of table.head) {
    if (cell.tag !== "th" || !/\bscope="col"/.test(cell.attrs)) found.push(`the header ${JSON.stringify(cell.text)} is not a th with scope="col"`);
    if (cell.text === "") found.push("a column has an empty header");
    if (/\bruns?\s+after\b|\bsuggest|\bdepends?\b|\bafter\b/i.test(cell.text)) found.push(`a column is named ${JSON.stringify(cell.text)}: the order of runs is IS6's`);
  }
  if (table.head.map((c) => c.text).join("|") !== HEADERS.join("|")) found.push(`the columns are ${JSON.stringify(table.head.map((c) => c.text))}, not ${JSON.stringify(HEADERS)}`);
  for (const [i, row] of table.rows.entries()) {
    if (row.length !== table.head.length) found.push(`row ${i + 1} has ${row.length} cells under ${table.head.length} headers`);
    const first = row[0];
    if (!first || first.tag !== "th" || !/\bscope="row"/.test(first.attrs)) found.push(`row ${i + 1} does not start with a th with scope="row"`);
    if (row.slice(1).some((c) => c.tag !== "td")) found.push(`row ${i + 1} has a header cell after its first`);
    if (row.some((c) => c.text === "")) found.push(`row ${i + 1} has an empty cell`);
  }
  if (/<(?:svg|canvas|line|polyline|path)\b/i.test(strip(html).replace(/<script\b[\s\S]*?<\/script>/g, ""))) found.push("the page draws a line or a canvas");
  return found;
}

/** Every fault in what a page lets a person reach and what it needs to run. */
function controlProblems(html: string): string[] {
  const page = strip(html);
  const found: string[] = [];
  for (const m of page.matchAll(/<[a-z][^>]*\s(on[a-z]+)\s*=/gi)) found.push(`an element has ${m[1] as string}`);
  for (const m of page.matchAll(/\btabindex="(-?\d+)"/g)) if (Number(m[1]) > 0) found.push(`tabindex="${m[1] as string}" puts a tab stop above 0`);
  for (const m of page.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    const attrs = m[1] as string;
    if (/\btype="application\/json"/.test(attrs)) continue;
    if (!/\bsrc="/.test(attrs) || (m[2] as string).trim() !== "") found.push("an inline script");
  }
  if (/\sstyle\s*=/.test(page)) found.push("an element has a style attribute");
  for (const m of page.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)) {
    if (!/\bhref="[^"]+"/.test(m[1] as string)) found.push("a link with no href: it is not a tab stop");
    if (cellText(m[2] as string) === "" && !/\baria-label="[^"]+"/.test(m[1] as string)) found.push("a link with no words");
  }
  for (const m of page.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)) {
    if (cellText(m[2] as string) === "" && !/\baria-label="[^"]+"/.test(m[1] as string)) found.push("a button with no words");
  }
  for (const m of page.matchAll(/<(input|select|textarea)\b([^>]*)>/g)) {
    const attrs = m[2] as string;
    if (/\btype="hidden"/.test(attrs)) continue;
    const id = /\bid="([^"]+)"/.exec(attrs)?.[1];
    const named = /\baria-label(?:ledby)?="[^"]+"/.test(attrs) || (id !== undefined && new RegExp(`<label[^>]*\\bfor="${id}"`).test(page));
    // A control inside a label element is named by it.
    const before = page.slice(0, m.index);
    const inLabel = before.lastIndexOf("<label") > before.lastIndexOf("</label>");
    if (!named && !inLabel) found.push(`a ${m[1] as string} with no label`);
  }
  return found;
}

const NAMES = (html: string): string[] => (tableOf(html)?.rows ?? []).map((r) => r[0]?.text ?? "");

describe("the dataset map (Scenario DM)", () => {
  it("DM1: the dataset's pipelines are a table with a caption, column headers and one row header per pipeline, drawn on the server", async () => {
    const w = await make(person({ pipelines: [recipe(), recipe({ recipe_id: "r-calls", label: "Calls", version: 1, status: "draft" })] }));
    const res = await w.get(PATH);
    expect(res.status).toBe(200);
    const table = tableOf(res.text);
    expect(table).not.toBeNull();
    expect(table?.caption).toBe(`Pipelines loading ${DATASET_NAME}`);
    expect(table?.head.map((c) => [c.tag, c.text])).toEqual(HEADERS.map((h) => ["th", h]));
    expect(table?.head.every((c) => /\bscope="col"/.test(c.attrs))).toBe(true);
    expect(table?.rows).toHaveLength(2);
    expect(table?.rows.every((r) => r[0]?.tag === "th" && /\bscope="row"/.test(r[0].attrs) && r.slice(1).every((c) => c.tag === "td"))).toBe(true);
    expect(tableProblems(res.text)).toEqual([]);
    expect(res.text).toMatch(/<title>Ingest Studio · Dataset map · OspreyFlow<\/title>/);
    // Drawn complete with no script: the table is in the first response, and the build's script is not what puts it there.
    expect(res.text).not.toMatch(/<script[^>]*src="[^"]*dataset-map/);
  });

  it("DM2: there are four columns and no 'runs after' column, no empty column, no suggestion and no line", async () => {
    const w = await make(person({ pipelines: [recipe(), recipe({ recipe_id: "r-calls", label: "Calls", version: 1, status: "draft" })] }));
    const res = await w.get(PATH);
    const table = tableOf(res.text);
    expect(table?.head.map((c) => c.text)).toEqual(HEADERS);
    for (const row of table?.rows ?? []) expect(row).toHaveLength(4);
    const place = textOf(placeOf(res.text));
    expect(place).not.toMatch(/runs? after|suggest|depends on|must run|run order|order of runs/i);
    expect(res.text).not.toMatch(/<(?:svg|canvas|line|polyline)\b/i);
    expect(placeOf(res.text)).not.toMatch(/<(?:form|input|select|button|textarea)\b/i);
    expect(tableProblems(res.text)).toEqual([]);
  });

  it("DM3: the stages are the kinds of the pipeline's graph, in words, in the order the canvas's layout would put them", async () => {
    // The node list is not in run order: the layout places a node by the longest path to it, then by its place in the list.
    const scrambled = {
      nodes: [node("l", "load"), node("m", "map"), node("b", "source", "B"), node("a", "source", "A"), node("d", "domain_model"), node("g", "geocode")],
      edges: [
        { source: "b", target: "m" },
        { source: "a", target: "m" },
        { source: "d", target: "m" },
        { source: "m", target: "g" },
        { source: "g", target: "l" },
      ],
    };
    const w = await make(
      person({
        pipelines: [
          recipe({ recipe_id: "r-a", label: "Scrambled", pipeline: scrambled }),
          recipe({ recipe_id: "r-b", label: "Chain" }),
          recipe({ recipe_id: "r-c", label: "Old style", pipeline: null }),
          recipe({ recipe_id: "r-d", label: "Staged", pipeline: { nodes: [node("s", "source"), node("q", "sql"), node("f", "fuzzy_match"), node("l", "load")], edges: [{ source: "s", target: "q" }, { source: "q", target: "f" }, { source: "f", target: "l" }] } }),
        ],
      }),
    );
    const rows = tableOf((await w.get(PATH)).text)?.rows ?? [];
    const stages = Object.fromEntries(rows.map((r) => [r[0]?.text, r[3]?.text]));
    expect(stages["Scrambled"]).toBe("Source, Source, Domain model, Map, geocode, Load");
    expect(stages["Chain"]).toBe("Domain model, Source, Profile, Map, Load");
    // A pipeline kept without a graph says so, never an empty cell; the Studio's expert steps keep their own names.
    expect(stages["Old style"]).toBe("Not recorded");
    expect(stages["Staged"]).toBe("Source, SQL transform, Fuzzy match, Load");
  });

  it("DM4: the status is the Studio's own word, the version is its number, and a previous version is not listed", async () => {
    const w = await make(
      person({
        pipelines: [
          recipe({ recipe_id: "r1", label: "A deployed one", status: "published", version: 3 }),
          recipe({ recipe_id: "r2", label: "A draft one", status: "draft", version: 1 }),
          recipe({ recipe_id: "r3", label: "A flagged one", status: "flagged", version: 2 }),
          recipe({ recipe_id: "r4", label: "An old one", status: "superseded", version: 1 }),
        ],
      }),
    );
    const rows = tableOf((await w.get(PATH)).text)?.rows ?? [];
    expect(rows.map((r) => [r[0]?.text, r[1]?.text, r[2]?.text])).toEqual([
      ["A deployed one", "deployed", "v3"],
      ["A draft one", "draft", "v1"],
      ["A flagged one", "needs attention", "v2"],
    ]);
  });

  it("DM5: the rows are sorted by pipeline name, whatever the case and the order they were read in, and the page says so", async () => {
    const w = await make(
      person({
        pipelines: [
          recipe({ recipe_id: "r3", label: "Wing visits" }),
          recipe({ recipe_id: "r2", label: "calls feed" }),
          recipe({ recipe_id: "r5", label: "Same name" }),
          recipe({ recipe_id: "r1", label: "Alpha extract" }),
          recipe({ recipe_id: "r4", label: "Same name", status: "draft" }),
        ],
      }),
    );
    const res = await w.get(PATH);
    expect(NAMES(res.text)).toEqual(["Alpha extract", "calls feed", "Same name", "Same name", "Wing visits"]);
    // Two of one name keep the order of their identifiers: the page is the same page every time.
    expect((tableOf(res.text)?.rows ?? []).map((r) => r[1]?.text)).toEqual(["deployed", "deployed", "draft", "deployed", "deployed"]);
    expect(textOf(placeOf(res.text))).toContain("Sorted by pipeline name.");
  });

  it("DM6: a dataset no pipeline loads says so in words, and draws no table", async () => {
    const w = await make(person({ pipelines: [] }));
    const res = await w.get(PATH);
    expect(res.status).toBe(200);
    expect(textOf(placeOf(res.text))).toContain(EMPTY);
    expect(res.text).not.toContain("<table");
    // A registry of pipelines that load other things is the same empty page.
    const other = await make(person({ cases: [caseRow({ datasets: [DATASET_NAME, "Second"], dataset_ids: [DATASET, "second-ds"] })], pipelines: [recipe({ dataset_id: "second-ds", label: "Elsewhere" })] }));
    const text = textOf(placeOf((await other.get(PATH)).text));
    expect(text).toContain(EMPTY);
    expect(text).not.toContain("Elsewhere");
  });

  it("DM7: only the pipelines that load this dataset are in the table: not another dataset's of the same case, none placed nowhere, and not what a faulty Conduit sent besides", async () => {
    const pipelines = [
      recipe({ recipe_id: "r-mine", label: "Mine" }),
      recipe({ recipe_id: "r-second", label: "Second dataset load", dataset_id: "second-ds" }),
      recipe({ recipe_id: "r-unplaced", label: "Unplaced load", dataset_id: null }),
      recipe({ recipe_id: "r-elsewhere", label: "Elsewhere load", dataset_id: "elsewhere-ds" }),
    ];
    const cases = [caseRow({ datasets: [DATASET_NAME, "Second dataset"], dataset_ids: [DATASET, "second-ds"] })];
    for (const registryScope of ["case", "none"] as const) {
      const w = await make(person({ cases, pipelines, registryScope }));
      const res = await w.get(PATH);
      expect(NAMES(res.text), registryScope).toEqual(["Mine"]);
      const place = textOf(placeOf(res.text));
      for (const hidden of ["Second dataset load", "Unplaced load", "Elsewhere load", "r-second", "r-unplaced", "r-elsewhere"]) expect(place).not.toContain(hidden);
      // No count is drawn by the map itself: not of the rows, and not of what was left out.
      expect(place).not.toMatch(/\b\d+ (?:pipelines?|of|more|hidden|others?)\b/i);
    }
  });

  it("DM8: a person without the right, a case the Conduit no longer opens, a dataset no case of theirs loads into and one that does not exist all get the same words, and no row, count or name", async () => {
    const secret = person({
      cases: [caseRow({ id: "case-secret", name: "Secret case", datasets: ["Secret dataset"], dataset_ids: ["secret-ds"] })],
      pipelines: [recipe({ recipe_id: "r-secret", label: "Secret pipeline", dataset_id: "secret-ds" })],
    });
    const w = await make(person({ pipelines: [recipe({ label: "Visible only with the right" })] }), [secret]);
    const unknown = await w.get(`${PATH}&dataset=no-such-dataset`);
    const forbidden = await w.get(`${PATH}&dataset=secret-ds`);
    // A dataset that exists for someone else and one that does not are one page, byte for byte: nothing of the id is echoed.
    expect(forbidden.status).toBe(unknown.status);
    expect(forbidden.text).toBe(unknown.text);
    for (const page of [unknown, forbidden]) {
      expect(textOf(placeOf(page.text))).toContain(REFUSED);
      expect(page.text).not.toContain("<table");
      for (const hidden of ["Secret", "secret-ds", "no-such-dataset", "Visible only with the right"]) expect(page.text).not.toContain(hidden);
      expect(page.text).not.toMatch(/<title>[^<]*(?:Secret|Visible)/);
    }
    // No right to read the pipelines (the Conduit's 403 names the right: the page never shows it) ...
    const noRight = await make(person({ rights: ALL_RIGHTS.filter((r) => r !== "edit_pipelines"), pipelines: [recipe({ label: "Hidden by the right" })] }));
    const refusedByRight = await noRight.get(PATH);
    // ... and a case the list still names that the Conduit has stopped opening (a 404): the same page.
    const gone = await make(person({ casesDenied: [CASE_ID], pipelines: [recipe({ label: "Hidden by the case" })] }));
    const refusedByCase = await gone.get(PATH);
    expect(refusedByRight.status).toBe(refusedByCase.status);
    expect(textOf(placeOf(refusedByRight.text))).toBe(textOf(placeOf(refusedByCase.text)));
    for (const page of [refusedByRight, refusedByCase]) {
      expect(textOf(placeOf(page.text))).toContain(REFUSED);
      expect(page.text).not.toContain("<table");
      for (const hidden of ["Hidden by", "edit_pipelines", "Missing right"]) expect(page.text).not.toContain(hidden);
      expect(textOf(placeOf(page.text))).not.toMatch(/\d/);
    }
    // The same words everywhere: one sentence, whatever the cause.
    expect(textOf(placeOf(refusedByRight.text))).toBe(textOf(placeOf(unknown.text)));
  });

  it("DM9: pipelines that could not be read are said so in an alert, never drawn as an empty table or as none loading", async () => {
    const w = await make(person({ pipelines: [recipe()] }));
    w.conduit.failing.add("/recipe-registry");
    const res = await w.get(PATH);
    expect(res.status).toBe(502);
    expect(placeOf(res.text)).toMatch(/role="alert"[^>]*>[^<]*could not be read just now/);
    const text = textOf(placeOf(res.text));
    expect(text).toContain(UNREADABLE);
    expect(text).not.toContain(EMPTY);
    expect(text).not.toContain(REFUSED);
    expect(res.text).not.toContain("<table");
  });

  it("DM10: the dataset's model is named in plain words, a link only if it is a page of this service (it is not yet)", async () => {
    const w = await make(person({ pipelines: [recipe()] }));
    const place = placeOf((await w.get(PATH)).text);
    expect(textOf(place)).toContain("Every pipeline that loads this dataset maps into its domain model, which is on 1 Model.");
    expect(place).not.toMatch(/<a\b/);
    expect(textOf(place)).not.toMatch(/target model/i);
  });

  it("DM11: the Conduit is asked once for the pipelines, as the person, with their bearer and nothing of the browser's", async () => {
    const w = await make(person({ pipelines: [recipe()] }));
    await w.get(PATH).set("X-CSRF-Token", w.signed.csrf).set("Origin", "https://evil.test");
    const asked = w.conduit.calls.filter((c) => c.path.endsWith("/ingest/recipe-registry"));
    expect(asked.map((c) => [c.method, c.path])).toEqual([["GET", `/v1/investigations/${CASE_ID}/ingest/recipe-registry`]]);
    expect(w.conduit.calls.length).toBeGreaterThan(0);
    for (const call of w.conduit.calls) {
      expect(call.method).toBe("GET");
      expect(call.headers["authorization"], call.path).toBe(`Bearer ${w.me.token}`);
      expect(call.headers["cookie"]).toBeUndefined();
      expect(call.headers["x-csrf-token"]).toBeUndefined();
      expect(call.headers["origin"]).toBeUndefined();
      expect(call.url).not.toContain(w.me.token);
      expect(call.url).not.toContain(w.signed.csrf);
    }
    // A request with no sign-in is sent to sign-in and asks the Conduit nothing; a page with no case asks for no pipelines.
    const anon = await make(person({ pipelines: [recipe()] }));
    for (const path of ["/studio/dataset-map", PATH]) {
      const res = await request(anon.app).get(path);
      expect(res.status, path).toBe(302);
      expect(res.headers["location"]).toBe("/session/sign-in");
    }
    expect(anon.conduit.calls).toEqual([]);
    const bare = await make(person({ pipelines: [recipe()] }));
    const none = await bare.get("/studio/dataset-map");
    expect(textOf(none.text)).toContain("Open a case to use the Ingest Studio");
    expect(none.text).not.toContain("<table");
    expect(bare.conduit.calls.filter((c) => c.path.includes("recipe-registry"))).toEqual([]);
  });

  it("DM12: the page needs no script and adds no action beyond links: no handler, no tab stop above 0, no control without a label, no inline script or style", async () => {
    const w = await make(person({ pipelines: [recipe(), recipe({ recipe_id: "r2", label: "Calls", status: "draft" })] }));
    for (const path of [PATH, `${PATH}&dataset=no-such-dataset`, "/studio/dataset-map"]) {
      const res = await w.get(path);
      expect(controlProblems(res.text), path).toEqual([]);
    }
    const res = await w.get(PATH);
    // Beyond the frame's own controls (the dataset switch, a GET form with a button), the place adds no control at all.
    expect(placeOf(res.text)).not.toMatch(/<(?:form|input|select|button|textarea|a)\b/i);
    // The frame's switch still works from this page: a GET form to this path, with a labelled select.
    expect(res.text).toMatch(/<form method="get" action="\/studio\/dataset-map"/);
    expect(res.text).toMatch(/<label[^>]*>\s*(?:<span[^>]*>)?Dataset/);
    // The only scripts are the page's data block and, once built, the frame's enhancement; no module is the table's.
    expect(res.text).not.toMatch(/<script(?![^>]*(?:application\/json|src=))/);
    expect(res.text).not.toMatch(/Content-Security-Policy[^>]*unsafe-inline/i);
  });

  it("DM13: the page is the service's own: registered under /studio, a GET only, and the answer is HTML with the service's headers", async () => {
    const w = await make(person({ pipelines: [recipe()] }));
    const res = await w.get(PATH);
    expect(res.headers["content-type"]).toMatch(/^text\/html/);
    expect(res.headers["content-security-policy"]).toMatch(/default-src 'self'/);
    const post = await w.post("/studio/dataset-map", { case: CASE_ID });
    expect(post.status).toBe(404);
    const noCases = await make(person({ cases: [], pipelines: [recipe()] }));
    const empty = await noCases.get(PATH);
    expect(empty.text).not.toContain("<table");
    expect(empty.text).not.toContain("Visits");
    expect(textOf(placeOf(empty.text))).toContain(REFUSED);
  });

  it("DM14: every check above is red against the real page with one thing changed", async () => {
    const w = await make(person({ pipelines: [recipe(), recipe({ recipe_id: "r2", label: "Calls", status: "draft" })] }));
    const real = (await w.get(PATH)).text;
    expect(tableProblems(real)).toEqual([]);
    expect(controlProblems(real)).toEqual([]);

    // A fifth column named "Runs after", as IS6 will add it: found by name and by count.
    const withColumn = real
      .replace("</tr>\n</thead>", '<th scope="col">Runs after</th></tr>\n</thead>')
      .replace(/<\/tr>(?=\s*(?:<tr|<\/tbody>))/g, "<td>Visits</td></tr>");
    expect(withColumn).not.toBe(real);
    expect(tableProblems(withColumn).join("; ")).toMatch(/Runs after/);
    // The same column with nothing in it.
    const emptyColumn = real.replace(/<\/tr>(?=\s*(?:<tr|<\/tbody>))/g, "<td></td></tr>").replace("</tr>\n</thead>", '<th scope="col"></th></tr>\n</thead>');
    expect(tableProblems(emptyColumn).join("; ")).toMatch(/empty header|empty cell/);
    // A header that is no longer a column header, a table with no caption, a row that does not start with a row header.
    expect(tableProblems(real.replace(/<th scope="col">/, "<th>")).join("; ")).toMatch(/scope="col"/);
    expect(tableProblems(real.replace(/<caption\b[^>]*>[\s\S]*?<\/caption>/, "")).join("; ")).toMatch(/no caption/);
    expect(tableProblems(real.replace(/<th scope="row"/, "<td")).join("; ")).toMatch(/scope="row"/);
    // A line drawn between the rows.
    expect(tableProblems(real.replace("</table>", '</table><svg><line x1="0" y1="0" x2="9" y2="9"/></svg>')).join("; ")).toMatch(/line or a canvas/);
    // A suggestion in the words.
    expect(tableProblems(real.replace(">Stages<", ">Suggested order<")).join("; ")).toMatch(/suggest/i);

    // The control checks.
    expect(controlProblems(real.replace("<tr>", '<tr onclick="go()">')).join("; ")).toMatch(/onclick/);
    expect(controlProblems(real.replace(/<a /, '<a tabindex="3" ')).join("; ")).toMatch(/tab stop above 0|tabindex="3"/);
    expect(controlProblems(real.replace("</main>", '<input name="x"></main>')).join("; ")).toMatch(/input with no label/);
    expect(controlProblems(real.replace("</main>", '<button type="button"></button></main>')).join("; ")).toMatch(/button with no words/);
    expect(controlProblems(real.replace("</main>", "<script>run()</script></main>")).join("; ")).toMatch(/inline script/);
    expect(controlProblems(real.replace("<table", '<table style="width:9px"')).join("; ")).toMatch(/style attribute/);
    expect(controlProblems(real.replace("</main>", "<a>words</a></main>")).join("; ")).toMatch(/no href/);
  });
});
