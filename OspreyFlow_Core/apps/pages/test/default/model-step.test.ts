/**
 * The Studio's Model step as a server-rendered page, Default tree (slice IS2a; ADR-140 Amendment 22 items 1, 3 and 4;
 * ADR-152 decisions 6, 7, 12 and 13; FUNCTIONS rows `studio-model-text` and `studio-model-proposals`).
 *
 * There is no React screen to copy (`ModelTab.tsx` is a sentence and a placeholder), so each case's id is a scenario of
 * `spec/08_ACCEPTANCE_SCENARIOS.md` ("Scenario MS"), written from the decision records, the prototype's Model step and the
 * owner's rulings of 21 and 23 November 2026. `tests/glass_trees/test_model_step_scenario.py` holds the two in step; the
 * Conduit's rows (MS2 to MS8) are `tests/services/api/test_model_draft_expected_version.py`'s.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a type's class, identifiers, matching rule or an indexed flag not drawn, or a table with no caption or header cell  -> MS1
 *  - a save or a discard sent without the version the person's copy was read at, or with the page's own read of it   -> MS9, MS10
 *  - a stale save that loses what the person typed, or says nothing of being out of date                             -> MS9
 *  - a person who is not the draft's creator offered a form, or told the draft's content in a refusal                 -> MS11
 *  - "no right", "not reached" and "no such dataset" worded or drawn differently, or the id echoed                     -> MS12
 *  - a read or a save that failed drawn as an empty model, or as no alert                                              -> MS13
 *  - an action that needs a script, a control with no label, a form with no token                                      -> MS14, MS16, MS17
 *  - the word "recipe" on screen                                                                                       -> MS15
 *  - the Conduit asked with anything of the browser's                                                                  -> MS16
 *  - a fake Conduit that grants what the real one refuses                                                              -> MS18
 * Every planted fault is the real page with one thing changed, run through the same check the real page goes through (MS19).
 */
import { afterEach, describe, expect, it } from "vitest";

import { fakeConduit } from "../support/fakeConduit.js";
import type { FakeModel } from "../support/fakeConduit.js";
import { ALL_RIGHTS, CASE_ID, DATASET, DATASET_NAME, bearer, caseRow, person, textOf, world } from "../support/studioWorld.js";
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

const PATH = `/studio/model?case=${CASE_ID}`;
const ME = "alice-1";
const ELSE = "bob-2";
const OPENED = "2026-11-20T09:30:00Z";
const OPENED_WORDS = "20 November 2026 at 09:30 UTC";
const REFUSED = "The domain model is not available to you: it needs rights you do not hold, or the dataset is not one of yours.";
const UNREADABLE = "The domain model of this dataset could not be read just now. Try again in a few minutes.";
const SAVE_FAILED = "The draft could not be saved just now. Nothing was changed, and what you typed is still in the form. Try again in a few minutes.";
const NO_DRAFT = "There is no draft of the domain model. Open one to change it; nothing that runs changes until a version is made live.";
const NO_LIVE = "This dataset has no live domain model yet: it uses the POLE core until one is made live.";
const NO_TYPES = "This version adds no types of its own: it is the POLE core with its packs.";
/** Content nobody but a reader with the right may see: no refusal's words may carry it. */
const SECRET = "Zebra";

// ------------------------------------------------------------------------------------------------ what the Conduit holds

/** An extension as the Conduit serialises it: every field, the ones that do not apply null or empty. */
function ext(over: Record<string, unknown>): Record<string, unknown> {
  return {
    name: "Thing",
    kind: "entity_type",
    on_type: null,
    added_in: 1,
    retired_in: null,
    pole_class: null,
    identifiers: [],
    matching: null,
    value_type: null,
    indexed: false,
    ...over,
  };
}

const VESSEL = ext({ name: "Vessel", pole_class: "object", identifiers: ["imo_number"], matching: { match_on: "imo_number", on_match: "reference" } });
const FLAG_STATE = ext({ name: "flag_state", kind: "property", on_type: "Vessel", value_type: "string", indexed: true });
const CALL_SIGN = ext({ name: "call_sign", kind: "property", on_type: "Vessel", value_type: "string", indexed: false });
const WING = ext({ name: "Wing" });
const TYPES = [VESSEL, FLAG_STATE, CALL_SIGN, WING];

function model(over: Partial<FakeModel> = {}): FakeModel {
  return {
    dataset_id: DATASET,
    version: 2,
    state: "draft",
    packs: { niem: 3 },
    extensions: TYPES,
    reference_lists: [],
    created_at: OPENED,
    created_by: ME,
    made_live_at: null,
    made_live_by: null,
    reverted_from: null,
    ...over,
  };
}

const live = (over: Partial<FakeModel> = {}): FakeModel =>
  model({ version: 1, state: "live", packs: {}, extensions: [ext({ name: "Berth", pole_class: "location", identifiers: ["berth_code"] })], made_live_at: "2026-11-01T10:00:00Z", made_live_by: "sys-1", ...over });

/** A signed-in engineer who holds the draft, with a draft and a live version seeded in the Conduit. */
async function mine(draft: FakeModel | null = model(), liveVersion: FakeModel | null = live(), over: Parameters<typeof person>[0] = {}): Promise<World> {
  const w = await make(person({ id: ME, ...over }));
  w.conduit.models.set(DATASET, { live: liveVersion, draft });
  return w;
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

function tablesOf(html: string): Table[] {
  const rowsOf = (part: string): Cell[][] =>
    [...part.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((row) =>
      [...(row[1] as string).matchAll(/<(th|td)\b([^>]*)>([\s\S]*?)<\/\1>/g)].map((c) => ({ tag: c[1] as "th" | "td", attrs: c[2] as string, text: textOf(c[3] as string) })),
    );
  return [...strip(html).matchAll(/<table\b[^>]*>([\s\S]*?)<\/table>/g)].map((found) => {
    const inner = found[1] as string;
    const caption = /<caption\b[^>]*>([\s\S]*?)<\/caption>/.exec(inner);
    const head = /<thead\b[^>]*>([\s\S]*?)<\/thead>/.exec(inner);
    const body = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/.exec(inner);
    return { caption: caption ? textOf(caption[1] as string) : null, head: head ? (rowsOf(head[1] as string)[0] ?? []) : [], rows: body ? rowsOf(body[1] as string) : [] };
  });
}

const HEADERS = ["Type", "Class", "Identifiers", "Matching rule", "Properties"];
const DRAFT_CAPTION = `Types in the draft of ${DATASET_NAME}`;
const LIVE_CAPTION = `Types in the live model of ${DATASET_NAME}`;

/** Every fault in a page's tables, in words: the same function reads the real page and each planted one. */
function tableProblems(html: string): string[] {
  const found: string[] = [];
  const tables = tablesOf(html);
  if (tables.length === 0) return ["there is no table"];
  for (const [n, table] of tables.entries()) {
    const label = `table ${n + 1}`;
    if (!table.caption) found.push(`${label} has no caption`);
    if (table.head.length === 0) found.push(`${label} has no head row`);
    for (const cell of table.head) {
      if (cell.tag !== "th" || !/\bscope="col"/.test(cell.attrs)) found.push(`${label}: the header ${JSON.stringify(cell.text)} is not a th with scope="col"`);
      if (cell.text === "") found.push(`${label} has a column with an empty header`);
    }
    if (table.head.map((c) => c.text).join("|") !== HEADERS.join("|")) found.push(`${label}: the columns are ${JSON.stringify(table.head.map((c) => c.text))}, not ${JSON.stringify(HEADERS)}`);
    for (const [i, row] of table.rows.entries()) {
      if (row.length !== table.head.length) found.push(`${label} row ${i + 1} has ${row.length} cells under ${table.head.length} headers`);
      const first = row[0];
      if (!first || first.tag !== "th" || !/\bscope="row"/.test(first.attrs)) found.push(`${label} row ${i + 1} does not start with a th with scope="row"`);
      if (row.slice(1).some((c) => c.tag !== "td")) found.push(`${label} row ${i + 1} has a header cell after its first`);
      if (row.some((c) => c.text === "")) found.push(`${label} row ${i + 1} has an empty cell`);
    }
  }
  return found;
}

/** Every fault in what a page lets a person reach and what it needs to run (as the dataset map's, plus a form's own). */
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
    if (textOf(m[2] as string) === "" && !/\baria-label="[^"]+"/.test(m[1] as string)) found.push("a link with no words");
  }
  for (const m of page.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)) {
    if (textOf(m[2] as string) === "" && !/\baria-label="[^"]+"/.test(m[1] as string)) found.push("a button with no words");
    if (!/\btype="submit"/.test(m[1] as string)) found.push("a button that is not a native submit");
  }
  for (const m of page.matchAll(/<(input|select|textarea)\b([^>]*)>/g)) {
    const attrs = m[2] as string;
    if (/\btype="hidden"/.test(attrs)) continue;
    const id = /\bid="([^"]+)"/.exec(attrs)?.[1];
    const named = /\baria-label(?:ledby)?="[^"]+"/.test(attrs) || (id !== undefined && new RegExp(`<label[^>]*\\bfor="${id}"`).test(page));
    const before = page.slice(0, m.index);
    const inLabel = before.lastIndexOf("<label") > before.lastIndexOf("</label>");
    if (!named && !inLabel) found.push(`a ${m[1] as string} with no label`);
  }
  for (const m of page.matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/g)) {
    if (/\bmethod="post"/i.test(m[1] as string) && !/<input[^>]*\bname="_csrf"[^>]*\bvalue="[^"]+"/.test(m[2] as string)) found.push("a post form with no anti-forgery token");
  }
  return found;
}

/** A failure to read or to save must be said in an alert and never drawn as a model: the draft and live tables, and the "no types" and "no draft" sentences, are a model. */
function emptyModelProblems(html: string): string[] {
  const place = placeOf(html);
  const found: string[] = [];
  if (!/\brole="alert"/.test(place)) found.push("a failure is not said in an alert");
  if (/<table\b/.test(place)) found.push("a failure is drawn with a table");
  for (const sentence of [NO_DRAFT, NO_LIVE, NO_TYPES]) if (textOf(place).includes(sentence)) found.push(`a failure is drawn as a model: ${JSON.stringify(sentence.slice(0, 40))}`);
  return found;
}

/** The word "recipe" on screen: the text of a page, its alt text and its labels. */
function wordsProblems(html: string): string[] {
  const shown = textOf(strip(html)) + " " + [...strip(html).matchAll(/\b(?:aria-label|title|alt|value|placeholder)="([^"]*)"/g)].map((m) => m[1]).join(" ");
  return /recipe/i.test(shown) ? ["the page says recipe: the word is Pipeline"] : [];
}

/** What a refusal page must not carry: the dataset's id, its name, another's, a count, the right's identifier, the Conduit's words. */
function echoProblems(html: string, forbidden: string[]): string[] {
  return forbidden.filter((word) => html.includes(word)).map((word) => `the page carries ${JSON.stringify(word)}`);
}

interface Form {
  method: string;
  action: string;
  hidden: Record<string, string>;
  buttons: string[];
  inner: string;
}
function formsOf(html: string): Form[] {
  return [...placeOf(html).matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/g)].map((m) => {
    const attrs = m[1] as string;
    const inner = m[2] as string;
    const hidden: Record<string, string> = {};
    for (const input of inner.matchAll(/<input\b([^>]*\btype="hidden"[^>]*)>/g)) {
      const name = /\bname="([^"]*)"/.exec(input[1] as string)?.[1];
      const value = /\bvalue="([^"]*)"/.exec(input[1] as string)?.[1] ?? "";
      if (name !== undefined) hidden[name] = value;
    }
    return {
      method: /\bmethod="([^"]*)"/.exec(attrs)?.[1] ?? "",
      action: /\baction="([^"]*)"/.exec(attrs)?.[1] ?? "",
      hidden,
      buttons: [...inner.matchAll(/<button\b[^>]*>([\s\S]*?)<\/button>/g)].map((b) => textOf(b[1] as string)),
      inner,
    };
  });
}
const formFor = (html: string, action: string): Form | undefined => formsOf(html).find((f) => f.hidden["action"] === action);
const typed = (html: string, name: string): string | undefined => new RegExp(`<input\\b[^>]*\\bname="${name}"[^>]*>`).exec(placeOf(html))?.[0].match(/\bvalue="([^"]*)"/)?.[1];
const alertOf = (html: string): string => [...placeOf(html).matchAll(/<p\b[^>]*\brole="alert"[^>]*>([\s\S]*?)<\/p>/g)].map((m) => textOf(m[1] as string)).join(" | ");
const unnonced = (html: string): string => html.replace(/nonce="[^"]*"/g, 'nonce="-"');

describe("the Model step (Scenario MS)", () => {
  it("MS1: the draft's types are a table, and the live model's another beside it: type, class, identifiers, matching rule and properties with the indexed flag in words", async () => {
    const w = await mine();
    const res = await w.get(PATH);
    expect(res.status).toBe(200);
    const [draft, liveTable] = tablesOf(res.text);
    expect(tablesOf(res.text)).toHaveLength(2);
    expect(draft?.caption).toBe(DRAFT_CAPTION);
    expect(liveTable?.caption).toBe(LIVE_CAPTION);
    for (const table of [draft, liveTable]) {
      expect(table?.head.map((c) => [c.tag, c.text])).toEqual(HEADERS.map((h) => ["th", h]));
      expect(table?.head.every((c) => /\bscope="col"/.test(c.attrs))).toBe(true);
      expect(table?.rows.every((r) => r[0]?.tag === "th" && /\bscope="row"/.test(r[0].attrs) && r.slice(1).every((c) => c.tag === "td"))).toBe(true);
    }
    // A type's own record: its class, identifiers and matching rule, and its properties each with the flag as words, by name.
    expect(draft?.rows.map((r) => r.map((c) => c.text))).toEqual([
      ["Vessel", "Object", "imo_number", "Matches on imo_number: an existing record is used", "call_sign (not indexed); flag_state (indexed)"],
      ["Wing", "Not recorded", "None", "No matching rule", "None"],
    ]);
    // A property is a property of its type, never a row of its own, and the live model is read apart from the draft.
    expect(liveTable?.rows.map((r) => r.map((c) => c.text))).toEqual([["Berth", "Location", "berth_code", "No matching rule", "None"]]);
    const text = textOf(placeOf(res.text));
    expect(text.indexOf(DRAFT_CAPTION)).toBeLessThan(text.indexOf(LIVE_CAPTION));
    expect(tableProblems(res.text)).toEqual([]);
    // The draft is said to be whose it is and since when, and the packs in words.
    expect(text).toContain(`Draft version 2, opened by ${ME} on ${OPENED_WORDS}.`);
    expect(text).toContain("Built on: POLE core + Crime case analysis (NIEM)");
    expect(res.text).toMatch(/<title>Ingest Studio · Model · OspreyFlow<\/title>/);
    // The matching rules the engine knows are said as words, and a retired type says so.
    const other = await mine(
      model({
        extensions: [
          ext({ name: "Quay", pole_class: "location", identifiers: ["quay_id", "name"], matching: { match_on: "quay_id", on_match: "create" } }),
          ext({ name: "Old", pole_class: "event", added_in: 1, retired_in: 2 }),
        ],
      }),
    );
    const rows = tablesOf((await other.get(PATH)).text)[0]?.rows.map((r) => r.map((c) => c.text));
    expect(rows).toEqual([
      ["Old (retired in version 2)", "Event", "None", "No matching rule", "None"],
      ["Quay", "Location", "quay_id, name", "Matches on quay_id: a new record is made each time", "None"],
    ]);
  });

  it("MS1: a version with no types of its own, no draft and no live model are each said in words, with no table", async () => {
    const noTypes = await mine(model({ extensions: [] }), live({ extensions: [] }));
    const none = await noTypes.get(PATH);
    expect(none.text).not.toContain("<table");
    expect(textOf(placeOf(none.text)).split(NO_TYPES).length - 1).toBe(2);
    const noDraft = await mine(null, null);
    const bare = await noDraft.get(PATH);
    expect(bare.status).toBe(200);
    expect(textOf(placeOf(bare.text))).toContain(NO_DRAFT);
    expect(textOf(placeOf(bare.text))).toContain(NO_LIVE);
    expect(bare.text).not.toContain("<table");
    // A draft opens by a form, with a button, and carries no version (there is none to carry).
    const open = formFor(bare.text, "open");
    expect(open?.method).toBe("post");
    expect(open?.action).toBe("/studio/model");
    expect(open?.buttons).toEqual(["Open a draft"]);
    expect(open?.hidden["case"]).toBe(CASE_ID);
    expect(open?.hidden["_csrf"]).toBe(noDraft.signed.csrf);
    expect(open?.hidden["expected_version"]).toBeUndefined();
  });

  it("MS9: a save carries the version the copy was read at; a stale one is refused, says the copy is out of date, and keeps what was typed and the draft as it is", async () => {
    const w = await mine();
    const page = await w.get(PATH);
    const save = formFor(page.text, "save");
    expect(save?.hidden["expected_version"]).toBe("2");
    expect(save?.buttons).toEqual(["Save draft"]);
    // The person's copy was read at version 2; meanwhile their draft was made live and a later one opened (version 3).
    w.conduit.models.set(DATASET, { live: model({ state: "live", made_live_at: OPENED, made_live_by: ME }), draft: model({ version: 3, packs: { fibo: 1 }, extensions: [VESSEL, FLAG_STATE] }) });
    const stale = await w.post("/studio/model", { case: CASE_ID, action: "save", expected_version: "2", pack_fibo: "", pack_niem: "7", pack_stix: "" });
    expect(stale.status).toBe(409);
    // The Conduit was sent the version of the copy, not one the page read for itself, and refused it in the store's words.
    const put = w.conduit.calls.filter((c) => c.method === "PUT");
    expect(put).toHaveLength(1);
    expect(JSON.parse(put[0]?.body ?? "{}").expected_version).toBe(2);
    const said = alertOf(stale.text);
    expect(said).toContain("Your copy of the draft was out of date: it is now version 3. Nothing was saved.");
    expect(said).toContain("you meant your draft's version 2, but your draft is now version 3");
    expect(said).toContain("read it again before changing it");
    // What was typed is kept in the form, and the form now carries the version the draft is, beside the draft as it now is.
    expect(typed(stale.text, "pack_niem")).toBe("7");
    expect(typed(stale.text, "pack_fibo")).toBe("");
    expect(formFor(stale.text, "save")?.hidden["expected_version"]).toBe("3");
    expect(tablesOf(stale.text)[0]?.rows.map((r) => r[0]?.text)).toEqual(["Vessel"]);
    // Nothing was changed in the Conduit.
    expect(w.conduit.models.get(DATASET)?.draft?.packs).toEqual({ fibo: 1 });
    // The same form sent again with the version it now carries saves, and the typed pins are the draft's.
    const again = await w.post("/studio/model", { case: CASE_ID, action: "save", expected_version: "3", pack_fibo: "", pack_niem: "7", pack_stix: "" });
    expect(again.status).toBe(200);
    expect(w.conduit.models.get(DATASET)?.draft?.packs).toEqual({ niem: 7 });
    expect(textOf(placeOf(again.text))).toContain("Draft saved as version 3. Nothing that runs has changed.");
    // The save kept the draft's own types: the page sent them back as it read them, so no type was lost.
    expect(w.conduit.models.get(DATASET)?.draft?.extensions).toEqual([VESSEL, FLAG_STATE]);
    expect(alertOf(again.text)).toBe("");
  });

  it("MS9: a pin that is not a whole number is refused in words with nothing sent, and what was typed is kept; a draft that is gone says so", async () => {
    const w = await mine();
    const bad = await w.post("/studio/model", { case: CASE_ID, action: "save", expected_version: "2", pack_fibo: "two", pack_niem: "3", pack_stix: "" });
    expect(bad.status).toBe(422);
    expect(alertOf(bad.text)).toContain("The version of the Financial fraud and AML (FIBO) pack must be a whole number of 1 or more, or blank.");
    expect(typed(bad.text, "pack_fibo")).toBe("two");
    expect(w.conduit.calls.filter((c) => c.method === "PUT")).toEqual([]);
    for (const version of ["", "0", "-3", "two", "1.5"]) {
      const res = await w.post("/studio/model", { case: CASE_ID, action: "save", expected_version: version, pack_niem: "3" });
      expect(res.status, version).toBe(400);
      expect(textOf(placeOf(res.text))).toContain("That request was not understood.");
    }
    expect(w.conduit.calls.filter((c) => c.method === "PUT")).toEqual([]);
    // Nothing to save into: the draft was discarded elsewhere.
    w.conduit.models.set(DATASET, { live: live(), draft: null });
    const gone = await w.post("/studio/model", { case: CASE_ID, action: "save", expected_version: "2", pack_niem: "4" });
    expect(gone.status).toBe(409);
    expect(alertOf(gone.text)).toContain("There is no draft to save: open one first.");
    expect(typed(gone.text, "pack_niem")).toBeUndefined();
    expect(w.conduit.calls.filter((c) => c.method === "PUT")).toEqual([]);
  });

  it("MS10: a discard carries the version the copy was read at; a stale one is refused and the draft is still there; a current one discards", async () => {
    const w = await mine();
    const discard = formFor((await w.get(PATH)).text, "discard");
    expect(discard?.hidden["expected_version"]).toBe("2");
    expect(discard?.buttons).toEqual(["Discard draft"]);
    w.conduit.models.set(DATASET, { live: live(), draft: model({ version: 3 }) });
    const stale = await w.post("/studio/model", { case: CASE_ID, action: "discard", expected_version: "2" });
    expect(stale.status).toBe(409);
    const deleted = w.conduit.calls.filter((c) => c.method === "DELETE");
    expect(deleted.map((c) => c.query.get("expected_version"))).toEqual(["2"]);
    expect(alertOf(stale.text)).toContain("Your copy of the draft was out of date: it is now version 3. Nothing was discarded.");
    expect(alertOf(stale.text)).toContain("read it again before changing it");
    expect(w.conduit.models.get(DATASET)?.draft?.version).toBe(3);
    expect(formFor(stale.text, "discard")?.hidden["expected_version"]).toBe("3");
    const current = await w.post("/studio/model", { case: CASE_ID, action: "discard", expected_version: "3" });
    expect(current.status).toBe(200);
    expect(w.conduit.models.get(DATASET)?.draft).toBeNull();
    expect(textOf(placeOf(current.text))).toContain("Draft discarded. Nothing that runs has changed.");
    expect(textOf(placeOf(current.text))).toContain(NO_DRAFT);
    expect(alertOf(current.text)).toBe("");
  });

  it("MS10: a draft is opened by a form, and a second is refused in the store's words", async () => {
    const w = await mine(null, live());
    const opened = await w.post("/studio/model", { case: CASE_ID, action: "open" });
    expect(opened.status).toBe(200);
    expect(w.conduit.models.get(DATASET)?.draft?.version).toBe(2);
    expect(w.conduit.models.get(DATASET)?.draft?.created_by).toBe(ME);
    expect(textOf(placeOf(opened.text))).toContain("Draft opened as version 2.");
    expect(formFor(opened.text, "save")?.hidden["expected_version"]).toBe("2");
    const second = await w.post("/studio/model", { case: CASE_ID, action: "open" });
    expect(second.status).toBe(409);
    expect(alertOf(second.text)).toContain("this dataset already has a draft, version 2: save or discard it first");
    expect(w.conduit.models.get(DATASET)?.draft?.version).toBe(2);
  });

  it("MS11: only the draft's creator is offered the forms; another person's forged save and discard are refused by the Conduit, in the store's words and with none of the draft's content", async () => {
    const secret = model({ created_by: ELSE, extensions: [ext({ name: SECRET, pole_class: "person", identifiers: ["secret_id"] })] });
    const w = await make(person({ id: ME }));
    w.conduit.models.set(DATASET, { live: live(), draft: secret });
    const page = await w.get(PATH);
    // The page says who holds it and offers no form to save into or discard it.
    expect(textOf(placeOf(page.text))).toContain(`Only ${ELSE} can save into or discard this draft.`);
    expect(formFor(page.text, "save")).toBeUndefined();
    expect(formFor(page.text, "discard")).toBeUndefined();
    // The forms are only words about who may act: the Conduit refuses a forged request all the same (rules 3 and 4).
    for (const fields of [
      { case: CASE_ID, action: "save", expected_version: "2", pack_niem: "9" } as Record<string, string>,
      { case: CASE_ID, action: "discard", expected_version: "2" },
      { case: CASE_ID, action: "open" },
    ]) {
      const res = await w.post("/studio/model", fields);
      expect(res.status, fields.action).toBe(409);
      const said = alertOf(res.text);
      // Save and discard are refused in words naming who holds it; opening a second draft says there is one, and not whose.
      expect(said, fields.action).toContain(fields.action === "open" ? "this dataset already has a draft, version 2" : ELSE);
      expect(said).not.toContain(SECRET);
      expect(said).not.toContain("secret_id");
    }
    expect(w.conduit.models.get(DATASET)?.draft).toEqual(secret); // as it was, in content, version and creator
    // The save is refused by the Conduit, which was asked: the page did not refuse it for the Conduit.
    expect(w.conduit.calls.filter((c) => c.method === "PUT")).toHaveLength(1);
    expect(w.conduit.calls.filter((c) => c.method === "DELETE")).toHaveLength(1);
  });

  it("MS12: no right, a case or dataset not reached and a dataset that does not exist get one sentence, and no row, count, name or id; an unknown dataset and a forbidden one are one page", async () => {
    const stranger = person({ cases: [caseRow({ id: "case-secret", name: "Secret case", datasets: ["Secret dataset"], dataset_ids: ["secret-ds"] })] });
    const w = await make(person({ id: ME }), [stranger]);
    w.conduit.models.set(DATASET, { live: live(), draft: model() });
    w.conduit.models.set("secret-ds", { live: live({ dataset_id: "secret-ds" }), draft: model({ dataset_id: "secret-ds", extensions: [ext({ name: SECRET })] }) });
    const unknown = await w.get(`${PATH}&dataset=no-such-dataset`);
    const forbidden = await w.get(`${PATH}&dataset=secret-ds`);
    expect(forbidden.status).toBe(unknown.status);
    expect(unnonced(forbidden.text)).toBe(unnonced(unknown.text));
    for (const page of [unknown, forbidden]) {
      expect(textOf(placeOf(page.text))).toContain(REFUSED);
      expect(textOf(page.text)).toContain("None of your cases loads into that dataset, so the Studio cannot open on it.");
      expect(page.text).not.toContain("<table");
      expect(echoProblems(page.text, ["Secret", "secret-ds", "no-such-dataset", SECRET, "Berth", "Vessel"])).toEqual([]);
    }
    // A person without the right to edit the model: the Conduit's 403 (which names the right) is the page's one sentence.
    const noRight = await make(person({ id: ME, rights: ALL_RIGHTS.filter((r) => r !== "edit_target_model") }));
    noRight.conduit.models.set(DATASET, { live: live(), draft: model() });
    const byRight = await noRight.get(PATH);
    // A dataset the case lists that the Conduit will no longer open for them (a 404): the same sentence.
    const gone = await make(person({ id: ME, datasetsDenied: [DATASET] }));
    gone.conduit.models.set(DATASET, { live: live(), draft: model() });
    const byDataset = await gone.get(PATH);
    expect(byRight.status).toBe(byDataset.status);
    expect(textOf(placeOf(byRight.text))).toBe(textOf(placeOf(byDataset.text)));
    for (const page of [byRight, byDataset]) {
      expect(textOf(placeOf(page.text))).toContain(REFUSED);
      expect(page.text).not.toContain("<table");
      expect(echoProblems(page.text, ["edit_target_model", "Missing right", "Not Found", "Vessel", "Berth", ME])).toEqual([]);
      expect(textOf(placeOf(page.text))).not.toMatch(/\d/);
      expect(formsOf(page.text)).toEqual([]);
    }
    // A save, a discard and an open by a person without the right, or for a dataset not theirs, are refused in the same words and write nothing.
    for (const fields of [
      { case: CASE_ID, action: "save", expected_version: "2", pack_niem: "9" } as Record<string, string>,
      { case: CASE_ID, action: "discard", expected_version: "2" },
      { case: CASE_ID, action: "open" },
    ]) {
      for (const who of [noRight, gone]) {
        const res = await who.post("/studio/model", fields);
        expect(res.status, fields.action).toBe(403);
        expect(textOf(placeOf(res.text))).toContain(REFUSED);
        expect(res.text).not.toContain("<table");
        expect(echoProblems(res.text, ["edit_target_model", "Missing right", "Vessel"])).toEqual([]);
        expect(who.conduit.models.get(DATASET)?.draft).toEqual(model());
      }
    }
    // A request that names a case the person does not hold is the same sentence as for any other reason, and asks for nothing written.
    const elsewhere = await w.post("/studio/model", { case: "case-not-mine", action: "discard", expected_version: "2" });
    expect(textOf(placeOf(elsewhere.text))).toContain(REFUSED);
    expect(w.conduit.calls.filter((c) => c.method === "DELETE")).toEqual([]);
    // (The frame's own switch form carries the case id the person's request named, as it does for every Studio page; no dataset's id is echoed.)
    expect(echoProblems(elsewhere.text, [DATASET, "Vessel", "Berth"].filter((word) => word !== DATASET))).toEqual([]);
  });

  it("MS13: a model that could not be read, or a save that failed, is said in an alert and never drawn as an empty model", async () => {
    const w = await mine();
    w.conduit.failing.add("/model");
    const res = await w.get(PATH);
    expect(res.status).toBe(502);
    expect(alertOf(res.text)).toContain(UNREADABLE);
    expect(emptyModelProblems(res.text)).toEqual([]);
    expect(res.text).not.toContain(REFUSED);
    // An answer that is not a model at all is a failure too, not a model with nothing in it.
    const odd = await mine();
    odd.conduit.models.set(DATASET, { live: "garbage" as never, draft: { version: "two" } as never });
    const garbled = await odd.get(PATH);
    expect(garbled.status).toBe(502);
    expect(alertOf(garbled.text)).toContain(UNREADABLE);
    expect(emptyModelProblems(garbled.text)).toEqual([]);
    // A save that failed says so, changes nothing and keeps what was typed; so does a discard and an open.
    const saving = await mine();
    saving.conduit.failing.add("/model/draft");
    const failedSave = await saving.post("/studio/model", { case: CASE_ID, action: "save", expected_version: "2", pack_niem: "5" });
    expect(failedSave.status).toBe(502);
    expect(alertOf(failedSave.text)).toContain(SAVE_FAILED);
    expect(typed(failedSave.text, "pack_niem")).toBe("5");
    expect(saving.conduit.models.get(DATASET)?.draft?.packs).toEqual({ niem: 3 });
    const failedDiscard = await saving.post("/studio/model", { case: CASE_ID, action: "discard", expected_version: "2" });
    expect(failedDiscard.status).toBe(502);
    expect(alertOf(failedDiscard.text)).toContain("The draft could not be discarded just now. Nothing was changed. Try again in a few minutes.");
    expect(saving.conduit.models.get(DATASET)?.draft?.version).toBe(2);
    const opener = await mine(null, live());
    opener.conduit.failing.add("/model/draft");
    const failedOpen = await opener.post("/studio/model", { case: CASE_ID, action: "open" });
    expect(failedOpen.status).toBe(502);
    expect(alertOf(failedOpen.text)).toContain("The draft could not be opened just now. Nothing was changed. Try again in a few minutes.");
    // A Conduit that is not there at all is the same as one that fails.
    const down = await mine();
    await down.conduit.stop();
    const unreachable = await down.get(PATH);
    expect(unreachable.text).not.toContain("<table");
    expect(unreachable.text).toMatch(/role="alert"/);
    expect(unreachable.text).not.toContain(NO_DRAFT);
    // The words the Conduit sent on a failure are never shown.
    for (const page of [res, failedSave, failedDiscard, failedOpen]) expect(echoProblems(page.text, ["Internal Server Error", "fake failed"])).toEqual([]);
  });

  it("MS13: the store's words are shown as text and only when the Conduit says they are a model refusal; any other 409 says nothing of its own", async () => {
    const w = await mine();
    w.conduit.nextModelRefusal = "<b>bold</b> <script>run()</script> words";
    const escaped = await w.post("/studio/model", { case: CASE_ID, action: "discard", expected_version: "2" });
    expect(escaped.status).toBe(409);
    expect(alertOf(escaped.text)).toContain("<b>bold</b> <script>run()</script> words");
    expect(placeOf(escaped.text)).not.toContain("<b>bold</b>");
    expect(escaped.text).not.toMatch(/<script>run\(\)/);
    // A 409 that is not the store's (another code) says nothing of its own: the page's sentence, with the Conduit's words nowhere.
    w.conduit.nextOtherConflict = "Internal words about owners and keys";
    const other = await w.post("/studio/model", { case: CASE_ID, action: "discard", expected_version: "2" });
    expect(other.status).toBe(409);
    expect(alertOf(other.text)).toContain("The draft was refused (409).");
    expect(echoProblems(other.text, ["Internal words", "owner_needed"])).toEqual([]);
  });

  it("MS14: with scripts off the lists are tables and every action is a form with a button, carrying the anti-forgery token, the case and the version", async () => {
    const w = await mine();
    const res = await w.get(PATH);
    expect(tablesOf(res.text)).toHaveLength(2);
    const forms = formsOf(res.text);
    expect(forms.map((f) => f.hidden["action"]).sort()).toEqual(["discard", "save"]);
    for (const form of forms) {
      expect(form.method).toBe("post");
      expect(form.action).toBe("/studio/model");
      expect(form.hidden["_csrf"]).toBe(w.signed.csrf);
      expect(form.hidden["case"]).toBe(CASE_ID);
      expect(form.hidden["expected_version"]).toBe("2");
      expect(form.buttons).toHaveLength(1);
    }
    // The save form's fields are labelled and prefilled from the draft: the pins in force and the ones left out.
    const save = formFor(res.text, "save");
    expect(save?.inner).toMatch(/<label[^>]*for="pack-niem"[^>]*>[^<]*Crime case analysis \(NIEM\)/);
    expect(typed(res.text, "pack_niem")).toBe("3");
    expect(typed(res.text, "pack_fibo")).toBe("");
    expect(typed(res.text, "pack_stix")).toBe("");
    // The page needs no script of its own: nothing is drawn or done by one (the only scripts are the data block and the frame's).
    expect(res.text).not.toMatch(/<script(?![^>]*(?:application\/json|src=))/);
    expect(res.text).not.toMatch(/<script[^>]*src="[^"]*model/);
    expect(controlProblems(res.text)).toEqual([]);
  });

  it("MS15: the word is Pipeline, never recipe, anywhere a person reads, whatever the page is saying", async () => {
    const w = await mine();
    const stale = (): Promise<{ text: string }> => w.post("/studio/model", { case: CASE_ID, action: "save", expected_version: "1", pack_niem: "3" });
    const pages = [await w.get(PATH), await stale(), await w.get(`${PATH}&dataset=no-such-dataset`), await w.post("/studio/model", { case: CASE_ID, action: "nonsense" })];
    w.conduit.failing.add("/model");
    pages.push(await w.get(PATH));
    for (const page of pages) expect(wordsProblems(page.text)).toEqual([]);
    expect(textOf(placeOf(pages[0]?.text ?? ""))).toContain("Every pipeline that loads this dataset maps into its domain model");
    expect(textOf(pages[0]?.text ?? "")).not.toMatch(/target model/i);
  });

  it("MS16: the Conduit is asked as the person, with their bearer and nothing of the browser's; a post needs its token; signed out is sent to sign-in; the Model place is a link to this page", async () => {
    const w = await mine();
    await w.get(PATH).set("X-CSRF-Token", w.signed.csrf).set("Origin", "https://evil.test");
    await w.post("/studio/model", { case: CASE_ID, action: "save", expected_version: "2", pack_niem: "3" });
    const asked = w.conduit.calls.map((c) => `${c.method} ${c.path}`);
    expect(asked).toContain(`GET /v1/datasets/${DATASET}/model`);
    expect(asked).toContain(`PUT /v1/datasets/${DATASET}/model/draft`);
    for (const call of w.conduit.calls) {
      expect(call.headers["authorization"], call.path).toBe(`Bearer ${w.me.token}`);
      expect(call.headers["cookie"]).toBeUndefined();
      expect(call.headers["x-csrf-token"]).toBeUndefined();
      expect(call.headers["origin"]).toBeUndefined();
      expect(call.url).not.toContain(w.me.token);
      expect(call.url).not.toContain(w.signed.csrf);
    }
    // A post with no token, or a wrong one, is refused and asks the Conduit nothing; it changes nothing.
    const before = w.conduit.calls.length;
    for (const csrf of [false, "not-the-token"] as const) {
      const res = await w.post("/studio/model", { case: CASE_ID, action: "discard", expected_version: "2" }, csrf);
      expect(res.status, String(csrf)).toBe(403);
      expect(res.text).not.toContain("<table");
    }
    expect(w.conduit.calls.length).toBe(before);
    expect(w.conduit.models.get(DATASET)?.draft?.version).toBe(2);
    // Signed out: sent to sign-in, and nothing asked.
    const anon = await mine();
    for (const path of ["/studio/model", PATH]) {
      const res = await request(anon.app).get(path);
      expect(res.status, path).toBe(302);
      expect(res.headers["location"]).toBe("/session/sign-in");
    }
    const post = await request(anon.app).post("/studio/model").type("form").send({ _csrf: "x", case: CASE_ID, action: "open" });
    expect([302, 403]).toContain(post.status);
    expect(anon.conduit.calls).toEqual([]);
    // No case: the frame says to open one, and nothing of the model is asked.
    const bare = await mine();
    const none = await bare.get("/studio/model");
    expect(textOf(none.text)).toContain("Open a case to use the Ingest Studio");
    expect(bare.conduit.calls.filter((c) => c.path.includes("/model"))).toEqual([]);
    // The place is a link to the page (no longer to the workspace), the open one marked, and no other method is answered.
    const frame = await w.get(`/studio/releases?case=${CASE_ID}`);
    const nav = /<nav aria-label="Ingest Studio places">([\s\S]*?)<\/nav>/.exec(frame.text)?.[1] ?? "";
    const model = [...nav.matchAll(/<a ([^>]*)>([^<]*)<\/a>/g)].find((m) => m[2] === "1 Model");
    expect(model?.[1]).toContain(`href="/studio/model?case=${CASE_ID}"`);
    expect(model?.[1]).not.toContain("data-opens-model");
    const here = /<nav aria-label="Ingest Studio places">([\s\S]*?)<\/nav>/.exec((await w.get(PATH)).text)?.[1] ?? "";
    expect(here).toMatch(/<a [^>]*href="\/studio\/model\?case=[^"]*"[^>]*aria-current="page"[^>]*>1 Model/);
    expect((await w.post("/studio/model", { case: CASE_ID, action: "nonsense" })).status).toBe(400);
    const put = await request(w.app).put("/studio/model").set("Cookie", w.signed.cookie).type("form").send({ _csrf: w.signed.csrf });
    expect(put.status).toBe(404);
  });

  it("MS17: every control is a native tab stop with a label: no handler, no tab stop above 0, no inline script or style, and no control but the frame's, a label's input and a form's button", async () => {
    const w = await mine();
    for (const path of [PATH, `${PATH}&dataset=no-such-dataset`, "/studio/model"]) {
      expect(controlProblems((await w.get(path)).text), path).toEqual([]);
    }
    const res = await w.get(PATH);
    // Beyond the frame's own controls the place adds only forms, their labelled inputs and their buttons: no link, select or script.
    expect(placeOf(res.text)).not.toMatch(/<(?:select|textarea|a)\b/i);
    expect(placeOf(res.text)).not.toMatch(/<input\b(?![^>]*type="hidden")(?![^>]*type="text")/i);
    expect(res.text).toMatch(/<form method="get" action="\/studio\/model"/);
    expect(res.text).not.toMatch(/Content-Security-Policy[^>]*unsafe-inline/i);
    for (const refused of [await w.post("/studio/model", { case: CASE_ID, action: "discard", expected_version: "9" }), await w.get(`${PATH}&dataset=no-such-dataset`)]) {
      expect(controlProblems(refused.text)).toEqual([]);
    }
  });

  it("MS18: the fake Conduit refuses what the real one refuses: no right, an unknown dataset, no version, a field the schema lacks, a stale version, another person's draft", async () => {
    const holder = person({ id: ME });
    const intruder = person({ id: ELSE });
    const analyst = person({ id: "ana-3", rights: ["edit_pipelines"] });
    const fake = await fakeConduit([holder, intruder, analyst]);
    try {
      fake.models.set(DATASET, { live: live(), draft: model() });
      const call = async (who: { token: string }, method: string, url: string, body?: unknown): Promise<{ status: number; json: Record<string, unknown> }> => {
        const res = await fetch(`${fake.url}${url}`, {
          method,
          headers: { Authorization: `Bearer ${who.token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
          ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        });
        const text = await res.text();
        return { status: res.status, json: text === "" ? {} : (JSON.parse(text) as Record<string, unknown>) };
      };
      const draft = `/v1/datasets/${DATASET}/model/draft`;
      const content = { packs: {}, extensions: [], reference_lists: [] };
      expect((await call({ token: "no-such" }, "GET", `/v1/datasets/${DATASET}/model`)).status).toBe(401);
      expect((await call(analyst, "GET", `/v1/datasets/${DATASET}/model`)).status).toBe(403);
      expect((await call(analyst, "PUT", draft, { ...content, expected_version: 2 })).status).toBe(403);
      expect((await call(holder, "GET", "/v1/datasets/not-one-of-theirs/model")).status).toBe(404);
      const noVersion = await call(holder, "PUT", draft, content);
      expect(noVersion.status).toBe(422);
      expect(JSON.stringify(noVersion.json)).toContain("expected_version");
      for (const unusable of [0, -1, "2", 1.5, null]) expect((await call(holder, "PUT", draft, { ...content, expected_version: unusable })).status, String(unusable)).toBe(422);
      expect((await call(holder, "PUT", draft, { ...content, expected_version: 2, surprise: 1 })).status).toBe(422);
      expect((await call(holder, "PUT", draft, { ...content, packs: { nope: 1 }, expected_version: 2 })).status).toBe(422);
      expect((await call(holder, "DELETE", draft)).status).toBe(422);
      expect((await call(holder, "DELETE", `${draft}?expected_version=0`)).status).toBe(422);
      const stale = await call(holder, "PUT", draft, { ...content, expected_version: 1 });
      expect(stale.status).toBe(409);
      expect(stale.json["error"]).toBe("model_refused");
      expect(String(stale.json["detail"])).toContain("you meant your draft's version 1, but your draft is now version 2");
      expect((await call(holder, "DELETE", `${draft}?expected_version=1`)).status).toBe(409);
      // Another person's draft: the creator is refused before the version is looked at, in words naming who holds it.
      for (const version of [1, 2]) {
        const refused = await call(intruder, "PUT", draft, { ...content, expected_version: version });
        expect(refused.status).toBe(409);
        expect(String(refused.json["detail"])).toContain(`only ${ME} can save into, replace or discard it`);
        expect(String(refused.json["detail"])).not.toContain("Vessel");
      }
      expect((await call(intruder, "DELETE", `${draft}?expected_version=2`)).status).toBe(409);
      expect(fake.models.get(DATASET)?.draft).toEqual(model());
      // And the grants: the creator's current version saves and discards.
      expect((await call(holder, "PUT", draft, { ...content, expected_version: 2 })).status).toBe(200);
      expect((await call(holder, "DELETE", `${draft}?expected_version=2`)).status).toBe(204);
      expect(fake.models.get(DATASET)?.draft).toBeNull();
    } finally {
      await fake.stop();
    }
  });

  it("MS19: every check above is red against the real page with one thing changed", async () => {
    const w = await mine();
    const real = (await w.get(PATH)).text;
    expect(tableProblems(real)).toEqual([]);
    expect(controlProblems(real)).toEqual([]);
    expect(wordsProblems(real)).toEqual([]);
    const failing = await mine();
    failing.conduit.failing.add("/model");
    const failed = (await failing.get(PATH)).text;
    expect(emptyModelProblems(failed)).toEqual([]);

    // The table checks: a column dropped, a missing caption, a header that is no column header, a row with no row header, an empty cell.
    expect(tableProblems(real.replace("<th scope=\"col\">Matching rule</th>", "")).join("; ")).toMatch(/columns are|cells under/);
    expect(tableProblems(real.replace(/<caption\b[^>]*>[\s\S]*?<\/caption>/, "")).join("; ")).toMatch(/no caption/);
    expect(tableProblems(real.replace(/<th scope="col">/, "<th>")).join("; ")).toMatch(/scope="col"/);
    expect(tableProblems(real.replace(/<th scope="row"/, "<td")).join("; ")).toMatch(/scope="row"/);
    expect(tableProblems(real.replace(/<td>None<\/td>/, "<td></td>")).join("; ")).toMatch(/empty cell/);
    expect(tableProblems(real.replace(/<table\b[\s\S]*?<\/table>/g, "")).join("; ")).toMatch(/no table/);
    // The control checks.
    expect(controlProblems(real.replace("<tr>", '<tr onclick="go()">')).join("; ")).toMatch(/onclick/);
    expect(controlProblems(real.replace(/<button /, '<button tabindex="4" ')).join("; ")).toMatch(/tab stop above 0/);
    expect(controlProblems(real.replace("</main>", '<input name="x"></main>')).join("; ")).toMatch(/input with no label/);
    expect(controlProblems(real.replace("</main>", '<button type="submit"></button></main>')).join("; ")).toMatch(/button with no words/);
    expect(controlProblems(real.replace("</main>", '<button type="button">Go</button></main>')).join("; ")).toMatch(/not a native submit/);
    expect(controlProblems(real.replace("</main>", "<script>run()</script></main>")).join("; ")).toMatch(/inline script/);
    expect(controlProblems(real.replace("<table", '<table style="width:9px"')).join("; ")).toMatch(/style attribute/);
    expect(controlProblems(real.replace("</main>", "<a>words</a></main>")).join("; ")).toMatch(/no href/);
    expect(controlProblems(real.replace(/<input type="hidden" name="_csrf"[^>]*>/, "")).join("; ")).toMatch(/anti-forgery token/);
    // The failure checks: an alert taken away, a table drawn, a model's own sentence in its place.
    expect(emptyModelProblems(failed.replace(/role="alert"/g, 'role="note"')).join("; ")).toMatch(/not said in an alert/);
    expect(emptyModelProblems(failed.replace('<div class="studio-place">', '<div class="studio-place"><table><caption>x</caption></table>')).join("; ")).toMatch(/drawn with a table/);
    expect(emptyModelProblems(failed.replace(UNREADABLE, NO_TYPES)).join("; ")).toMatch(/drawn as a model/);
    // The words and the echo checks.
    expect(wordsProblems(real.replace("Draft", "Recipe draft")).join("; ")).toMatch(/recipe/);
    expect(wordsProblems(real.replace(/<caption\b/, '<caption aria-label="recipe"')).join("; ")).toMatch(/recipe/);
    const refused = (await w.get(`${PATH}&dataset=no-such-dataset`)).text;
    expect(echoProblems(refused, ["no-such-dataset", "Vessel"])).toEqual([]);
    expect(echoProblems(refused.replace("</main>", "<p>no-such-dataset</p></main>"), ["no-such-dataset"]).join("; ")).toContain("no-such-dataset");
    // An unusable bearer, so the person's own token is no part of any page.
    expect(real).not.toContain(w.me.token);
    expect(bearer()).not.toBe(w.me.token);
  });
});
