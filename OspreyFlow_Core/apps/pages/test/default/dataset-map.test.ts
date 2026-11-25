/**
 * The Studio's dataset map as a server-rendered page, Default tree (slice IS3; ADR-140 Amendment 22 items 1 and 8; ADR-141
 * Amendment 2; ADR-152 decisions 6, 7, 12 and 13; FUNCTIONS row `studio-dataset-map`), and the order pipelines run in (slice IS6a,
 * 24 November 2026: the owner's rulings on the IS6 draft; DM2 and DM11 to DM14 are changed with the spec and DM15 to DM24 are new).
 *
 * There is no React dataset map to read the behaviour from (`FUNCTIONS.yaml` says so), so each case's id is a scenario of
 * `spec/08_ACCEPTANCE_SCENARIOS.md` ("Scenario DM"), written from the ADR text, the prototype's Pipelines list and the owner's
 * ruling of 21 November 2026 ("show the dataset as a table with no 'runs after' column. IS6 adds the column when it stores the
 * order. Do not show an empty column or a suggestion nothing backs"). `tests/glass_trees/test_dataset_map_scenario.py` holds the
 * two in step.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a "runs after" column with no order stored, an empty column, a suggestion or a line -> DM2, DM14, DM16
 *  - the order not drawn when stored, or an undeployed pipeline not said so       -> DM15
 *  - a form with no label, no token, no number, or that needs a script            -> DM12, DM17
 *  - a save that sends another order than ticked, or another number than read     -> DM18
 *  - a cycle saved, or its pipelines not named, or the ticks lost                 -> DM19
 *  - an order that moved on overwritten, or its refusal not said                  -> DM20
 *  - a save for a person without the right, or a dataset not theirs, carried out  -> DM21
 *  - a form that is not the page's own carried to the Conduit                     -> DM22
 *  - an order that could not be read drawn as none, or a failed save as saved     -> DM23
 *  - a pipeline the reader may not see named, counted or implied                  -> DM24
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

import { ORDER_WORDS, openedWords } from "../support/fakeConduit.js";
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
/** With an order stored: the same and one more. */
const HEADERS_WITH_ORDER = [...HEADERS, "Runs after"];

/** Every fault in a page's table, in words: the same function reads the real page and each planted one. */
function tableProblems(html: string, headers: string[] = HEADERS): string[] {
  const found: string[] = [];
  const table = tableOf(html);
  if (table === null) return ["there is no table"];
  if (!table.caption) found.push("the table has no caption");
  if (table.head.length === 0) found.push("the table has no head row");
  for (const cell of table.head) {
    if (cell.tag !== "th" || !/\bscope="col"/.test(cell.attrs)) found.push(`the header ${JSON.stringify(cell.text)} is not a th with scope="col"`);
    if (cell.text === "") found.push("a column has an empty header");
    if (/\bsuggest|\brecommend/i.test(cell.text)) found.push(`a column is named ${JSON.stringify(cell.text)}: no suggestion of an order is made`);
  }
  if (table.head.map((c) => c.text).join("|") !== headers.join("|")) found.push(`the columns are ${JSON.stringify(table.head.map((c) => c.text))}, not ${JSON.stringify(headers)}`);
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

// ------------------------------------------------------------------------------------------------ the order form

interface Box {
  id: string;
  name: string;
  value: string;
  checked: boolean;
  labelFor: string;
  label: string;
}
interface Group {
  legend: string;
  boxes: Box[];
}

/** The page's one POST form, its inside; null when there is none. */
const formOf = (html: string): string | null => /<form method="post" action="\/studio\/dataset-map">([\s\S]*?)<\/form>/.exec(strip(html))?.[1] ?? null;
const hiddenOf = (form: string): Record<string, string> =>
  Object.fromEntries([...form.matchAll(/<input type="hidden" name="([^"]+)" value="([^"]*)">/g)].map((m) => [m[1] as string, m[2] as string]));
const groupsOf = (form: string): Group[] =>
  [...form.matchAll(/<fieldset>\s*<legend>([\s\S]*?)<\/legend>([\s\S]*?)<\/fieldset>/g)].map((m) => ({
    legend: textOf(m[1] as string),
    boxes: [...(m[2] as string).matchAll(/<input type="checkbox" id="([^"]+)" name="([^"]+)" value="([^"]*)"( checked)?>\s*<label for="([^"]+)">([\s\S]*?)<\/label>/g)].map((b) => ({
      id: b[1] as string,
      name: b[2] as string,
      value: b[3] as string,
      checked: b[4] !== undefined,
      labelFor: b[5] as string,
      label: textOf(b[6] as string),
    })),
  }));

/** Every fault in the order form: the same function reads the real page and each planted one. */
function formProblems(html: string): string[] {
  const form = formOf(html);
  if (form === null) return ["there is no order form"];
  const found: string[] = [];
  const hidden = hiddenOf(form);
  for (const name of ["_csrf", "case", "dataset", "expected_version"]) if (!hidden[name]) found.push(`the form has no ${name}`);
  if (hidden["expected_version"] !== undefined && !/^\d+$/.test(hidden["expected_version"])) found.push("the form's number is not a whole number");
  const groups = groupsOf(form);
  if (groups.length === 0) found.push("the form has no group of tick boxes");
  for (const group of groups) {
    if (group.legend === "") found.push("a group has no legend");
    if (group.boxes.length === 0) found.push(`the group ${JSON.stringify(group.legend)} has no tick box`);
    for (const box of group.boxes) {
      if (box.name !== "link") found.push(`a tick box is named ${JSON.stringify(box.name)}, not link`);
      if (box.labelFor !== box.id || box.label === "") found.push(`a tick box ${JSON.stringify(box.id)} has no label of its own`);
    }
  }
  if (!/<button type="submit"[^>]*>\s*\S[\s\S]*?<\/button>/.test(form)) found.push("the form has no submit button with words");
  return found;
}

const link = (pipeline: string, after: string): string => `${encodeURIComponent(pipeline)}|${encodeURIComponent(after)}`;
const SAVED_AT = "2026-11-20T09:30:00Z";
const SAVED_WORDS = "20 November 2026 at 09:30 UTC";
const ORDERED = [
  recipe({ recipe_id: "r-visits", label: "Visits" }),
  recipe({ recipe_id: "r-calls", label: "Calls", version: 1, status: "draft" }),
  recipe({ recipe_id: "r-report", label: "Report", version: 2 }),
];
/** The Conduit holds this order for the dataset: its number, who saved it and the links, whoever may see their pipelines. */
function seed(w: World, version: number, runsAfter: Record<string, string[]>, by = "analyst-1"): void {
  w.conduit.orders.set(DATASET, { version, saved_by: by, saved_at: SAVED_AT, runs_after: runsAfter });
}
const MAP = "/studio/dataset-map";
/** The form as the page draws it, posted as a browser would, with the tick boxes named. */
const save = (w: World, expected: string, ticked: [string, string][], over: [string, string][] = []): ReturnType<World["postPairs"]> =>
  w.postPairs(MAP, [["case", CASE_ID], ["dataset", DATASET], ["expected_version", expected], ...over, ...ticked.map(([a, b]): [string, string] => ["link", link(a, b)])]);
const puts = (w: World): { path: string; method: string; headers: Record<string, unknown>; body: string }[] => w.conduit.calls.filter((c) => c.method === "PUT");

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

  it("DM2: with no order stored there are four columns, and no 'runs after' column, no empty column, no hint of an order, no suggestion and no line", async () => {
    const w = await make(person({ pipelines: [recipe(), recipe({ recipe_id: "r-calls", label: "Calls", version: 1, status: "draft" })] }));
    const res = await w.get(PATH);
    const table = tableOf(res.text);
    expect(table?.head.map((c) => c.text)).toEqual(HEADERS);
    for (const row of table?.rows ?? []) expect(row).toHaveLength(4);
    // Nothing of an order is in the table or beside it: no column, no line saying a version, no suggestion; the only words of
    // "runs after" are the form's own legends, which set it.
    expect(textOf(tableOf(res.text) ? (/<table\b[\s\S]*?<\/table>/.exec(strip(res.text))?.[0] ?? "") : "")).not.toMatch(/runs? after|suggest|depends on|must run|run order|order of runs|nothing/i);
    expect(textOf(placeOf(res.text))).not.toMatch(/suggest|recommend|Run order version|none (?:is|has been) (?:stored|saved)/i);
    expect(res.text).not.toMatch(/<(?:svg|canvas|line|polyline)\b/i);
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
    // A dataset that exists for someone else and one that does not are one page, byte for byte but for the nonce: nothing of the id is echoed.
    expect(forbidden.status).toBe(unknown.status);
    // (Each response carries its own script nonce, which is the only thing allowed to differ.)
    const unnonced = (html: string): string => html.replace(/nonce="[^"]*"/g, 'nonce="-"');
    expect(unnonced(forbidden.text)).toBe(unnonced(unknown.text));
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
    // The stored order, once, from the dataset's own route.
    expect(w.conduit.calls.filter((c) => c.path.includes("/run-order")).map((c) => [c.method, c.path])).toEqual([["GET", `/v1/datasets/${DATASET}/run-order`]]);
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

  it("DM12: the page needs no script: no handler, no tab stop above 0, no control without a label, no inline script or style", async () => {
    const w = await make(person({ pipelines: [recipe(), recipe({ recipe_id: "r2", label: "Calls", status: "draft" })] }));
    for (const path of [PATH, `${PATH}&dataset=no-such-dataset`, "/studio/dataset-map"]) {
      const res = await w.get(path);
      expect(controlProblems(res.text), path).toEqual([]);
    }
    const res = await w.get(PATH);
    // Beyond the frame's own controls (the dataset switch, a GET form with a button), the place's controls are the order form's
    // alone: one POST form, tick boxes and a submit button; no link, no select, no text field.
    const place = placeOf(res.text);
    expect(place.match(/<form\b/g)).toHaveLength(1);
    expect(place).not.toMatch(/<(?:select|textarea|a)\b/i);
    expect([...place.matchAll(/<input type="([a-z]+)"/g)].every((m) => m[1] === "hidden" || m[1] === "checkbox")).toBe(true);
    expect(formProblems(res.text)).toEqual([]);
    // The frame's switch still works from this page: a GET form to this path, with a labelled select.
    expect(res.text).toMatch(/<form method="get" action="\/studio\/dataset-map"/);
    expect(res.text).toMatch(/<label[^>]*>\s*(?:<span[^>]*>)?Dataset/);
    // The only scripts are the page's data block and, once built, the frame's enhancement; no module is the table's.
    expect(res.text).not.toMatch(/<script(?![^>]*(?:application\/json|src=))/);
    expect(res.text).not.toMatch(/Content-Security-Policy[^>]*unsafe-inline/i);
  });

  it("DM13: the page is the service's own: registered under /studio, a GET and its form's POST only, and the answer is HTML with the service's headers", async () => {
    const w = await make(person({ pipelines: [recipe()] }));
    const res = await w.get(PATH);
    expect(res.headers["content-type"]).toMatch(/^text\/html/);
    expect(res.headers["content-security-policy"]).toMatch(/default-src 'self'/);
    // A method the page does not list is a page that is not there.
    for (const method of ["put", "delete", "patch"] as const) {
      const other = await request(w.app)[method]("/studio/dataset-map").set("Cookie", w.signed.cookie).set("X-CSRF-Token", w.signed.csrf);
      expect(other.status, method).toBe(404);
    }
    // The POST is the form's: with no anti-forgery token it is refused before the page, and nothing is sent to the Conduit.
    const forged = await w.post("/studio/dataset-map", { case: CASE_ID }, false);
    expect(forged.status).toBe(403);
    expect(puts(w)).toEqual([]);
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
    expect(formProblems(real)).toEqual([]);

    // A fifth column named "Runs after" with no order stored: found by name and by count.
    const withColumn = real
      .replace("</tr>\n</thead>", '<th scope="col">Runs after</th></tr>\n</thead>')
      .replace(/<\/tr>(?=\s*(?:<tr|<\/tbody>))/g, "<td>Visits</td></tr>");
    expect(withColumn).not.toBe(real);
    expect(tableProblems(withColumn).join("; ")).toMatch(/Runs after/);
    // The same column with nothing in it, and a column of another name.
    const emptyColumn = real.replace(/<\/tr>(?=\s*(?:<tr|<\/tbody>))/g, "<td></td></tr>").replace("</tr>\n</thead>", '<th scope="col"></th></tr>\n</thead>');
    expect(tableProblems(emptyColumn).join("; ")).toMatch(/empty header|empty cell/);
    expect(tableProblems(real.replace(">Stages<", ">Depends on<")).join("; ")).toMatch(/Depends on/);
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
    // The form's checks: a tick box with no label of its own, a form with no token, no number, no button. Each is the real form
    // with one thing changed inside it (the frame has forms of its own, whose parts must not be the ones changed).
    const inForm = (change: (form: string) => string): string => real.replace(formOf(real) as string, change(formOf(real) as string));
    expect(formProblems(inForm((f) => f.replace(/<label for="[^"]+">/, '<label for="elsewhere">'))).join("; ")).toMatch(/no label of its own/);
    expect(formProblems(inForm((f) => f.replace(/<input type="hidden" name="_csrf"[^>]*>/, ""))).join("; ")).toMatch(/no _csrf/);
    expect(formProblems(inForm((f) => f.replace(/<input type="hidden" name="expected_version"[^>]*>/, ""))).join("; ")).toMatch(/no expected_version/);
    expect(formProblems(inForm((f) => f.replace(/(name="expected_version" value=")\d+"/, '$1one"'))).join("; ")).toMatch(/not a whole number/);
    expect(formProblems(inForm((f) => f.replace(/<button type="submit"[^>]*>[\s\S]*?<\/button>/, ""))).join("; ")).toMatch(/no submit button/);
    expect(formProblems(inForm((f) => f.replace(/name="link"/, 'name="order"'))).join("; ")).toMatch(/not link/);
    expect(formProblems(inForm((f) => f.replace(/<fieldset>\s*<legend>[\s\S]*?<\/legend>/, "<fieldset><legend></legend>"))).join("; ")).toMatch(/no legend/);
  });

  it("DM15: with an order stored the table has a fifth column, Runs after, naming what each pipeline runs after, and not deployed in words, with the version, who and when", async () => {
    const w = await make(person({ pipelines: ORDERED }));
    seed(w, 3, { "r-calls": ["r-visits"], "r-report": ["r-visits", "r-calls"] });
    const res = await w.get(PATH);
    expect(res.status).toBe(200);
    expect(tableProblems(res.text, HEADERS_WITH_ORDER)).toEqual([]);
    const rows = tableOf(res.text)?.rows ?? [];
    // Sorted by name: each pipeline's own after-list is sorted by name too; one that is not deployed (Calls is a draft) says so.
    expect(rows.map((r) => [r[0]?.text, r[4]?.text])).toEqual([
      ["Calls", "Visits"],
      ["Report", "Calls (not deployed), Visits"],
      ["Visits", "Nothing"],
    ]);
    expect(textOf(placeOf(res.text))).toContain(`Run order version 3, saved by analyst-1 on ${SAVED_WORDS}.`);
    // A pipeline that is not deployed may be in the order and is said so in the form's labels too.
    const labels = groupsOf(formOf(res.text) ?? "").flatMap((g) => g.boxes.map((b) => b.label));
    expect(labels).toContain("Calls (not deployed)");
    expect(labels).not.toContain("Visits (not deployed)");
    // The order's column draws no line and no suggestion.
    expect(textOf(placeOf(res.text))).not.toMatch(/suggest|recommend/i);
    expect(res.text).not.toMatch(/<(?:svg|canvas|line|polyline)\b/i);
  });

  it("DM16: an order with nothing to say about these pipelines draws no column, no sentence about none, and still the form", async () => {
    const orders: Record<string, string[]>[] = [{}, { "r-ghost": ["r-visits"], "r-visits": ["r-ghost"] }];
    for (const links of orders) {
      const w = await make(person({ pipelines: ORDERED, orderScope: "none" }));
      seed(w, 2, links);
      const res = await w.get(PATH);
      expect(tableOf(res.text)?.head.map((c) => c.text), JSON.stringify(links)).toEqual(HEADERS);
      expect(tableProblems(res.text)).toEqual([]);
      expect(textOf(placeOf(res.text))).not.toMatch(/ghost|none (?:is|has been) (?:stored|saved)|no order/i);
      expect(formProblems(res.text)).toEqual([]);
      // Nothing ticked: no stored link is among these pipelines.
      expect(groupsOf(formOf(res.text) ?? "").flatMap((g) => g.boxes).some((b) => b.checked)).toBe(false);
    }
  });

  it("DM17: the order form has a group of tick boxes for each pipeline, labelled, ticked as stored, and carries the token, the case, the dataset and the number read", async () => {
    const w = await make(person({ pipelines: ORDERED }));
    seed(w, 3, { "r-calls": ["r-visits"], "r-report": ["r-visits", "r-calls"] });
    const res = await w.get(PATH);
    expect(formProblems(res.text)).toEqual([]);
    const form = formOf(res.text) as string;
    expect(hiddenOf(form)).toEqual({ _csrf: w.signed.csrf, case: CASE_ID, dataset: DATASET, expected_version: "3" });
    const groups = groupsOf(form);
    expect(groups.map((g) => g.legend)).toEqual(["Calls runs after", "Report runs after", "Visits runs after"]);
    // Every other pipeline is a tick box of each group, and none is its own; each is ticked as the order stores it.
    const ticked = groups.flatMap((g, i) => g.boxes.filter((b) => b.checked).map((b) => [i, b.value]));
    expect(groups.every((g) => g.boxes.length === 2)).toBe(true);
    expect(ticked).toEqual([
      [0, link("r-calls", "r-visits")],
      [1, link("r-report", "r-calls")],
      [1, link("r-report", "r-visits")],
    ]);
    expect(new Set(groups.flatMap((g) => g.boxes.map((b) => b.id))).size).toBe(6);
    // No order yet: the number is 0 and nothing is ticked. One pipeline has nothing to put in order: no form. None: no table.
    const fresh = await make(person({ pipelines: ORDERED }));
    const none = await fresh.get(PATH);
    expect(hiddenOf(formOf(none.text) as string)["expected_version"]).toBe("0");
    expect(groupsOf(formOf(none.text) as string).flatMap((g) => g.boxes).some((b) => b.checked)).toBe(false);
    const single = await make(person({ pipelines: [recipe()] }));
    expect(formOf((await single.get(PATH)).text)).toBeNull();
    const empty = await make(person({ pipelines: [] }));
    expect(formOf((await empty.get(PATH)).text)).toBeNull();
  });

  it("DM18: a save sends the order as ticked and the number read, as the person, then says the new version; ticking nothing clears the links", async () => {
    const w = await make(person({ pipelines: ORDERED }));
    seed(w, 3, { "r-calls": ["r-visits"] });
    const res = await save(w, "3", [["r-report", "r-visits"], ["r-report", "r-calls"], ["r-calls", "r-visits"]]);
    expect(res.status).toBe(200);
    const sent = puts(w);
    expect(sent.map((c) => [c.method, c.path])).toEqual([["PUT", `/v1/datasets/${DATASET}/run-order`]]);
    const call = sent[0] as (typeof sent)[number];
    expect(call.headers["authorization"]).toBe(`Bearer ${w.me.token}`);
    for (const header of ["cookie", "x-csrf-token", "origin"]) expect(call.headers[header]).toBeUndefined();
    expect(JSON.parse(call.body)).toEqual({
      expected_version: 3,
      entries: [
        { pipeline_id: "r-report", runs_after: ["r-visits", "r-calls"] },
        { pipeline_id: "r-calls", runs_after: ["r-visits"] },
      ],
    });
    const text = textOf(placeOf(res.text));
    expect(text).toContain("The run order is saved as version 4.");
    expect(text).toContain("Run order version 4, saved by analyst-1 on");
    expect(w.conduit.orders.get(DATASET)?.version).toBe(4);
    expect(tableProblems(res.text, HEADERS_WITH_ORDER)).toEqual([]);
    expect((tableOf(res.text)?.rows ?? []).map((r) => [r[0]?.text, r[4]?.text])).toEqual([
      ["Calls", "Visits"],
      ["Report", "Calls (not deployed), Visits"],
      ["Visits", "Nothing"],
    ]);
    // The form is drawn again for the new number, ticked as saved.
    expect(hiddenOf(formOf(res.text) as string)["expected_version"]).toBe("4");
    // Ticking nothing clears the order's links: an empty save, a new number, and the column goes (no empty column).
    const cleared = await save(w, "4", []);
    expect(cleared.status).toBe(200);
    expect(JSON.parse((puts(w)[1] as (typeof sent)[number]).body)).toEqual({ expected_version: 4, entries: [] });
    expect(w.conduit.orders.get(DATASET)?.version).toBe(5);
    expect(tableOf(cleared.text)?.head.map((c) => c.text)).toEqual(HEADERS);
    expect(textOf(placeOf(cleared.text))).toContain("The run order is saved as version 5.");
  });

  it("DM19: a cycle is refused in the Conduit's words naming the pipelines in it, the order is shown as stored with the ticks kept, and nothing is saved", async () => {
    const w = await make(person({ pipelines: ORDERED }));
    seed(w, 3, { "r-calls": ["r-visits"] });
    const res = await save(w, "3", [["r-visits", "r-calls"], ["r-calls", "r-visits"], ["r-report", "r-visits"]]);
    expect(res.status).toBe(422);
    const place = placeOf(res.text);
    expect(place).toMatch(/<p role="alert">[^<]*“Calls”, “Visits”/);
    expect(textOf(place)).toContain(ORDER_WORDS.cycle(["Calls", "Visits"]));
    // Named by the labels the Studio shows, never an identifier, and not the pipeline that only runs after the cycle.
    expect(textOf(place)).not.toContain("“Report”");
    expect(place).not.toMatch(/r-visits|r-calls/.exec(textOf(place))?.[0] ?? "$^");
    // Nothing was saved; the table is the stored order, and what was ticked is ticked.
    expect(w.conduit.orders.get(DATASET)?.version).toBe(3);
    expect((tableOf(res.text)?.rows ?? []).map((r) => [r[0]?.text, r[4]?.text])).toEqual([
      ["Calls", "Visits"],
      ["Report", "Nothing"],
      ["Visits", "Nothing"],
    ]);
    const ticked = groupsOf(formOf(res.text) as string).flatMap((g) => g.boxes.filter((b) => b.checked).map((b) => b.value));
    expect(ticked.sort()).toEqual([link("r-calls", "r-visits"), link("r-report", "r-visits"), link("r-visits", "r-calls")].sort());
    // A pipeline after itself is a cycle too.
    const self = await save(w, "3", [["r-report", "r-report"]]);
    expect(self.status).toBe(422);
    expect(textOf(placeOf(self.text))).toContain(ORDER_WORDS.cycle(["Report"]));
  });

  it("DM20: an order that has moved on since the page was read is refused, said, shown as it now is with the ticks kept, and nothing is overwritten", async () => {
    const w = await make(person({ pipelines: ORDERED }));
    seed(w, 3, { "r-calls": ["r-visits"] }, "bob-2");
    const res = await save(w, "2", [["r-report", "r-visits"]]);
    expect(res.status).toBe(409);
    const text = textOf(placeOf(res.text));
    expect(text).toContain("The run order was changed by someone else since you read it");
    // In the Conduit's own words: the number meant, the number it is now, who and when, and to read it again.
    expect(text).toContain(ORDER_WORDS.stale(2, 3, "bob-2", openedWords(SAVED_AT)));
    expect(w.conduit.orders.get(DATASET)).toMatchObject({ version: 3, runs_after: { "r-calls": ["r-visits"] } });
    // The order as it now is, the form for its number, and what was ticked kept.
    expect(hiddenOf(formOf(res.text) as string)["expected_version"]).toBe("3");
    const ticked = groupsOf(formOf(res.text) as string).flatMap((g) => g.boxes.filter((b) => b.checked).map((b) => b.value));
    expect(ticked).toEqual([link("r-report", "r-visits")]);
    // The number from the future is as stale as one from the past; the number it is now saves.
    expect((await save(w, "9", [["r-report", "r-visits"]])).status).toBe(409);
    expect((await save(w, "3", [["r-report", "r-visits"]])).status).toBe(200);
    expect(w.conduit.orders.get(DATASET)?.version).toBe(4);
  });

  it("DM21: a save by a person without the right, for a dataset that is not theirs or after the sign-in ended is answered as the read is, and saves nothing", async () => {
    const hidden = [recipe({ label: "Secret pipeline" }), recipe({ recipe_id: "r-two", label: "Second secret", status: "draft" })];
    // No right to edit pipelines: the Conduit refuses the registry; the page says the one sentence and sends nothing.
    const noRight = await make(person({ rights: ALL_RIGHTS.filter((r) => r !== "edit_pipelines"), pipelines: hidden }));
    seed(noRight, 1, { "r-two": ["r-visits"] });
    const byRight = await save(noRight, "1", [["r-two", "r-visits"]]);
    // A case that is not theirs: no dataset to save for.
    const other = await make(person({ pipelines: hidden }));
    seed(other, 1, { "r-two": ["r-visits"] });
    const notTheirs = await other.postPairs(MAP, [["case", "case-not-theirs"], ["dataset", DATASET], ["expected_version", "1"], ["link", link("r-two", "r-visits")]]);
    // The Conduit no longer opens the dataset after the page was drawn (their access changed): refused at the save, the same words.
    const changed = await make(person({ pipelines: hidden, datasetsDenied: [DATASET] }));
    seed(changed, 1, { "r-two": ["r-visits"] });
    const byDataset = await save(changed, "1", [["r-two", "r-visits"]]);
    for (const [page, w] of [[byRight, noRight], [notTheirs, other], [byDataset, changed]] as const) {
      expect(page.status).toBe(page === notTheirs ? 200 : 403);
      expect(textOf(placeOf(page.text))).toContain(REFUSED);
      expect(page.text).not.toContain("<table");
      for (const named of ["Secret pipeline", "Second secret", "r-two", "r-visits", "edit_pipelines", "Missing right"]) expect(page.text).not.toContain(named);
      expect(textOf(placeOf(page.text))).not.toMatch(/\d/);
      expect(w.conduit.orders.get(DATASET)?.version).toBe(1);
    }
    // The first two never asked the Conduit to save; the third was refused there (404, as for a dataset that does not exist).
    expect(puts(noRight)).toEqual([]);
    expect(puts(other)).toEqual([]);
    expect(puts(changed).length).toBeLessThanOrEqual(1);
    // The read of the order is refused for the same reason (the dataset is no longer theirs): the one sentence, no table, no name.
    const read = await changed.get(PATH);
    expect(read.status).toBe(403);
    expect(textOf(placeOf(read.text))).toContain(REFUSED);
    for (const named of ["<table", "Secret pipeline", "Second secret", "r-two"]) expect(read.text).not.toContain(named);
    // The sign-in has ended: the words that it has, and nothing saved or named.
    const ended = await make(person({ pipelines: hidden }));
    seed(ended, 1, { "r-two": ["r-visits"] });
    ended.conduit.people.delete(ended.me.token);
    const gone = await save(ended, "1", [["r-two", "r-visits"]]);
    expect(gone.text).toContain("Your session has ended");
    expect(puts(ended)).toEqual([]);
    expect(gone.text).not.toContain("Secret pipeline");
    expect(ended.conduit.orders.get(DATASET)?.version).toBe(1);
  });

  it("DM22: a form that is not the page's own is refused and nothing is sent to the Conduit", async () => {
    const w = await make(person({ pipelines: ORDERED }));
    seed(w, 3, { "r-calls": ["r-visits"] });
    const ok: [string, string][] = [["case", CASE_ID], ["dataset", DATASET], ["expected_version", "3"], ["link", link("r-report", "r-visits")]];
    const without = (name: string): [string, string][] => ok.filter(([key]) => key !== name);
    const bad: [string, [string, string][]][] = [
      ["no number", without("expected_version")],
      ["a number that is not whole", [...without("expected_version"), ["expected_version", "1.5"]]],
      ["a negative number", [...without("expected_version"), ["expected_version", "-1"]]],
      ["a word for a number", [...without("expected_version"), ["expected_version", "three"]]],
      ["a tick box that is not a pair", [...without("link"), ["link", "garbage"]]],
      ["a tick box of three parts", [...without("link"), ["link", "a|b|c"]]],
      ["a tick box with an empty part", [...without("link"), ["link", "|r-visits"]]],
      ["a tick box with a broken escape", [...without("link"), ["link", "%E0%A4%A|r-visits"]]],
    ];
    for (const [what, pairs] of bad) {
      const res = await w.postPairs(MAP, pairs);
      expect(res.status, what).toBe(400);
      expect(textOf(placeOf(res.text)), what).toContain("That request was not understood. Nothing has changed.");
    }
    // A form for another dataset is not this page's: the number it carries is for another order.
    const elsewhere = await w.postPairs(MAP, [...without("dataset"), ["dataset", "some-other-dataset"]]);
    expect(elsewhere.status).toBe(409);
    expect(textOf(placeOf(elsewhere.text))).toContain("That form was for another dataset. Nothing has changed.");
    expect(elsewhere.text).not.toContain("some-other-dataset");
    // No anti-forgery token: refused before the page is reached.
    expect((await w.postPairs(MAP, ok, false)).status).toBe(403);
    expect((await w.postPairs(MAP, ok, "not-the-token")).status).toBe(403);
    expect(puts(w)).toEqual([]);
    expect(w.conduit.orders.get(DATASET)?.version).toBe(3);
    // Control: the same form with every part right is carried out.
    expect((await w.postPairs(MAP, ok)).status).toBe(200);
    expect(puts(w)).toHaveLength(1);
  });

  it("DM23: an order that could not be read is said in an alert, never drawn as none, with no column and no form; a save that could not be made says so and keeps the ticks", async () => {
    const w = await make(person({ pipelines: ORDERED }));
    seed(w, 3, { "r-calls": ["r-visits"] });
    w.conduit.failing.add("/run-order");
    const res = await w.get(PATH);
    expect(res.status).toBe(502);
    expect(placeOf(res.text)).toMatch(/role="alert"[^>]*>[^<]*run order of this dataset could not be read just now/);
    // The pipelines were read, so they are drawn; the order is not drawn at all, and not as none stored.
    expect(tableOf(res.text)?.head.map((c) => c.text)).toEqual(HEADERS);
    expect(formOf(res.text)).toBeNull();
    expect(textOf(placeOf(res.text))).not.toMatch(/Run order version|saved by/);
    // A save that failed at the store: said, nothing saved, and the form is there with the ticks kept.
    const v = await make(person({ pipelines: ORDERED }));
    seed(v, 3, { "r-calls": ["r-visits"] });
    v.conduit.failNextOrderSave = true;
    const failed = await save(v, "3", [["r-report", "r-visits"]]);
    expect(failed.status).toBe(502);
    expect(placeOf(failed.text)).toMatch(/role="alert"[^>]*>[^<]*could not be saved just now\. Nothing has changed/);
    expect(textOf(placeOf(failed.text))).not.toContain("The run order is saved");
    expect(v.conduit.orders.get(DATASET)?.version).toBe(3);
    const ticked = groupsOf(formOf(failed.text) as string).flatMap((g) => g.boxes.filter((b) => b.checked).map((b) => b.value));
    expect(ticked).toEqual([link("r-report", "r-visits")]);
    // The order's own failure at the page's save is the same: said, never a saved number.
    w.conduit.failing.add("/run-order");
    const down = await save(w, "3", [["r-report", "r-visits"]]);
    expect(down.status).toBe(502);
    expect(textOf(placeOf(down.text))).toContain("could not be saved just now");
  });

  it("DM24: a pipeline the reader may not see, or a link that names one, is not named, counted or implied", async () => {
    // A Conduit that sent every link it holds (the fault): the page draws only what its own table holds.
    const w = await make(person({ pipelines: ORDERED, orderScope: "none" }));
    seed(w, 5, {
      "r-calls": ["r-visits", "r-ghost-of-another-unit"],
      "r-ghost-of-another-unit": ["r-visits", "r-calls"],
      "r-report": ["r-ghost-of-another-unit"],
      // A link of a pipeline to itself is no order: drawn as running after nothing.
      "r-visits": ["r-visits"],
    });
    const res = await w.get(PATH);
    expect(tableProblems(res.text, HEADERS_WITH_ORDER)).toEqual([]);
    // A pipeline left with only a link it may not see runs after "Nothing": never "after something unnamed".
    expect((tableOf(res.text)?.rows ?? []).map((r) => [r[0]?.text, r[4]?.text])).toEqual([
      ["Calls", "Visits"],
      ["Report", "Nothing"],
      ["Visits", "Nothing"],
    ]);
    expect(res.text).not.toContain("ghost");
    const place = textOf(placeOf(res.text));
    expect(place).not.toMatch(/\b\d+ (?:pipelines?|links?|of|more|hidden|others?|not shown|left out)\b/i);
    expect(place).not.toMatch(/unnamed|another unit|you may not|hidden/i);
    // The form carries no identifier of a pipeline the table does not hold.
    expect(formOf(res.text)).not.toMatch(/ghost/);
    // A save never sends a link to a pipeline the page does not hold either: only what its own form could tick.
    const sent = await save(w, "5", [["r-report", "r-visits"]]);
    expect(sent.status).toBe(200);
    expect(puts(w).map((c) => c.body).join("")).not.toMatch(/ghost/);
  });
});
