/**
 * A case's drawing boards and one board's drawn items and links as tables, read-only, on the GOV.UK tree (slice GG4a; ADR-143 decisions 3
 * to 5; ADR-152 decisions 1, 4, 5, 6, 7 and 12; FUNCTIONS row `drawing-boards`; scenario BD of `spec/08_ACCEPTANCE_SCENARIOS.md`, written
 * first). `tests/glass_trees/test_govuk_boards_scenario.py` holds the scenario and this file in step: each case's id is a row of the
 * scenario.
 *
 * There is no React-first proof (the React boards are a place of buttons and a drawing surface): the proof is the real service started for
 * the GOV.UK tree, the real page list and a fixture Conduit that refuses what the real routes refuse (`boardsConduit.ts`).
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a board missing, added, out of order, a column other than the five, a count the page made, a name not a link     -> BD1
 *  - an empty list drawn as a table, or as headings with no rows                                                         -> BD2
 *  - a drawn item without its marking or grading, a reference not said as loaded                                         -> BD3
 *  - a drawn item's or link's source said in any way until GG4b: a note, a document's id, "No note given", a column       -> BD3
 *  - a link listed twice, an end looked up outside the route's items or said as unknown                                  -> BD4
 *  - a private board, another case's, none, no level, no right told apart, or told in other words than an unknown path's -> BD5
 *  - the withdrawn count said to another reader, said at zero, made by the page, or naming an item                       -> BD6
 *  - an item hidden by its marking leaving a gap, a row, a count or a "hidden" line                                       -> BD7
 *  - a board past the cap drawn in part, or said without its three options                                               -> BD8
 *  - a read made twice in one render, the browser's headers sent on, a write, an unsigned read                           -> BD9
 *  - a failed read drawn as an empty table, an ended session not said                                                    -> BD10
 *  - a missing required field read as empty                                                                               -> BD11
 *  - a field neither drawn nor named as left out, a left-out field that changes the page                                 -> BD12
 *  - an empty board drawn as headings with no rows                                                                        -> BD13
 *  - a form, a control, a skipped heading, a stop out of order                                                            -> BD14
 *  - a script, a handler, an inline style                                                                                 -> BD15
 *  - the page in the Default tree, left out of the route list, the case's page not linking to it, the shared words again -> BD16
 * Every planted fault is the real page (or the real view, or the real file) with one thing changed, run through the same function that
 * finds nothing in the real one (BD17, rule 15).
 */
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Express } from "express";
import { afterEach, describe, expect, it } from "vitest";
import { utcStampOf } from "@ospreyflow/glass-shared";

import { createApp } from "../../server/app.js";
import { PAGES } from "../../server/pageList.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { BOARDS_WORDS, CENSUS, MAY_BE_ABSENT, NOT_SENT, REQUIRED, boardHref, boardView, boardsHref, limitView, listView } from "../../server/views/boardsWords.js";
import { CASES_WORDS } from "../../server/views/casesWords.js";
import { refusalWords } from "../../server/views/studioWords.js";
import { testClock } from "../support/clock.js";
import { cookieFrom, csrfFromPage, request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { bearer, providerFor, textOf } from "../support/studioWorld.js";
import { NOT_FOUND_BOARD, NOT_FOUND_CASE, UNKNOWN_BEARER, boardOf, boardsConduit, openedOf, rightRefusal } from "./boardsConduit.js";
import type { Board, BoardsConduit, BoardsConduitOptions, Item, Link, Reader } from "./boardsConduit.js";

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CORE = join(PAGES_DIR, "..", "..");
const read = (...parts: string[]): string => readFileSync(join(...parts), "utf8");

const PATH = "/cases/boards";
const NOWHERE = "/nothing-is-served-here";
const CASE = "c-harbour";
const listOf = (caseId = CASE): string => `${PATH}?case=${encodeURIComponent(caseId)}`;
const boardOfPath = (boardId: string, caseId = CASE): string => `${PATH}?case=${encodeURIComponent(caseId)}&board=${encodeURIComponent(boardId)}`;

// ------------------------------------------------------------------------------------------------ the world

const conduits: BoardsConduit[] = [];
afterEach(async () => {
  while (conduits.length > 0) await conduits.pop()?.stop();
});

const UNIT = "harbour-unit";
const ALEX = "acct-alex";
const BLAKE = "acct-blake";

const CASES = [
  { id: CASE, owning_unit: UNIT },
  { id: "c-other", owning_unit: UNIT },
  { id: "c-elsewhere", owning_unit: "other-unit" },
  { id: "c-unshared", owning_unit: UNIT },
];

const drawnBy = (who: string, board: string, item: string, label: string, extra: Partial<Item["drawn"]> = {}): NonNullable<Item["drawn"]> => ({
  label,
  grading: { scheme: "5x5x5", source: "B", intelligence: "2", handling: "1" },
  source_note: "Seen from the harbour wall",
  source_document: null,
  asserted_by: who,
  item_id: item,
  board_id: board,
  ...extra,
});

/** The items of the case's layer and its datasets: loaded ones, drawn ones, one hidden from Alex by its marking, two withdrawn. */
const ITEMS: Item[] = [
  { id: "n-vessel", type: "Vessel", properties: { name: "Morning Star", imo: "9-000-001" }, marking: "OFFICIAL" },
  { id: "n-owner", type: "Person", properties: { given_names: "Rowan", family_name: "Hale" }, marking: "OFFICIAL-SENSITIVE" },
  { id: "d-old", type: "Person", properties: {}, marking: "OFFICIAL", drawn: drawnBy(ALEX, "b-earlier", "i-old", "Old lead"), withdrawn: true },
  { id: "d-tall", type: "Person", properties: { name: "not this name" }, marking: "OFFICIAL", drawn: drawnBy(ALEX, "b-quay", "i-tall", "Unknown male “Tall”", { grading: { scheme: "5x5x5", source: "A", intelligence: "1", handling: "1" } }) },
  { id: "d-van", type: "Vehicle", properties: {}, marking: "OFFICIAL-SENSITIVE", drawn: drawnBy(ALEX, "b-quay", "i-van", "White van", { source_note: null, source_document: "doc-photo-7" }) },
  { id: "d-crew", type: "Organisation", properties: {}, marking: "OFFICIAL", drawn: drawnBy(ALEX, "b-quay", "i-crew", "Night crew", { source_document: "doc-memo-2", grading: { scheme: "5x5x5", source: "C", intelligence: "3", handling: "2" } }) },
  { id: "d-secret", type: "Person", properties: {}, marking: "SECRET", drawn: drawnBy(ALEX, "b-quay", "i-secret", "Hidden informant") },
  { id: "d-courier", type: "Person", properties: {}, marking: "OFFICIAL", drawn: drawnBy(BLAKE, "b-shift", "i-courier", "Courier") },
  { id: "d-gone", type: "Person", properties: {}, marking: "OFFICIAL", drawn: drawnBy(BLAKE, "b-earlier", "i-gone", "Gone lead"), withdrawn: true },
  { id: "d-private", type: "Person", properties: {}, marking: "OFFICIAL", drawn: drawnBy(BLAKE, "b-blake", "i-private", "Blake's own lead") },
];

const LINKS: Link[] = [
  // A drawn link between a drawn item and a loaded one.
  { id: "l-seen", type: "KNOWS", source: "d-tall", target: "n-owner", marking: "OFFICIAL", drawn: drawnBy(ALEX, "b-quay", "i-seen", "Seen with") },
  // A loaded link between two loaded items.
  { id: "l-owns", type: "OWNS", source: "n-owner", target: "n-vessel", marking: "OFFICIAL" },
  { id: "l-used", type: "USES", source: "d-crew", target: "d-van", marking: "OFFICIAL-SENSITIVE", drawn: drawnBy(ALEX, "b-quay", "i-used", "Used by", { source_note: null, source_document: "doc-memo-2" }) },
  // Hidden from Alex: one touching the secret item, and one of a marking above his clearance between items he may see.
  { id: "l-secret", type: "KNOWS", source: "d-tall", target: "d-secret", marking: "OFFICIAL", drawn: drawnBy(ALEX, "b-quay", "i-l-secret", "Meets") },
  { id: "l-high", type: "KNOWS", source: "d-tall", target: "d-van", marking: "SECRET", drawn: drawnBy(ALEX, "b-quay", "i-high", "Drives") },
];

/** The case's boards in the fixture's own order, which no sort gives: not by name either way (Quay, Empty, Night), not by when made
 * either way (November, September, October), not by count either way (3, 0, 1). The real store sends oldest first; a page that sorted,
 * on any of these, would show. */
const BOARDS: Board[] = [
  { id: "b-quay", case_id: CASE, name: "Quay sketch", created_by: ALEX, created_at: "2026-11-10T09:30:00Z", shared: false, references: ["n-vessel", "n-owner", "d-old"], drawn: ["d-tall", "d-van", "d-crew", "d-secret"] },
  { id: "b-empty", case_id: CASE, name: "Empty start", created_by: ALEX, created_at: "2026-09-03T14:00:00Z", shared: false, references: [], drawn: [] },
  { id: "b-shift", case_id: CASE, name: "Night shift", created_by: BLAKE, created_at: "2026-10-21T22:15:00Z", shared: true, references: ["d-gone"], drawn: ["d-courier"] },
  // Not Alex's to see: Blake's private board, and a board of another case.
  { id: "b-blake", case_id: CASE, name: "Blake's private board", created_by: BLAKE, created_at: "2026-10-22T08:00:00Z", shared: false, references: [], drawn: ["d-private"] },
  { id: "b-elsewhere", case_id: "c-other", name: "Another case's board", created_by: ALEX, created_at: "2026-10-23T08:00:00Z", shared: true, references: [], drawn: [] },
];
const ALEXS = ["b-quay", "b-empty", "b-shift"];

interface World {
  app: Express;
  conduit: BoardsConduit;
  reader: Reader;
  options: BoardsConduitOptions;
  cookie: string;
  csrf: string;
}

interface WorldOptions extends Partial<Omit<BoardsConduitOptions, "readers">> {
  as?: string;
  rights?: string[];
  levels?: string[];
  tree?: "govuk" | "default";
  conduitUrl?: string;
  unknownBearer?: boolean;
}

async function world(options: WorldOptions = {}): Promise<World> {
  const token = bearer();
  const reader: Reader = {
    token,
    id: options.as ?? ALEX,
    unit: UNIT,
    rights: options.rights ?? ["investigate", "draw_on_boards"],
    cases: options.levels ?? [CASE, "c-other", "c-elsewhere"],
    clearance: "OFFICIAL-SENSITIVE",
  };
  const { as: _a, rights: _r, levels: _l, tree: _t, conduitUrl: _c, unknownBearer: _u, ...rest } = options;
  const conduitOptions: BoardsConduitOptions = { readers: options.unknownBearer === true ? [] : [reader], cases: CASES, boards: BOARDS, items: ITEMS, links: LINKS, ...rest };
  const conduit = await boardsConduit(conduitOptions);
  conduits.push(conduit);
  const app = createApp({
    store: new MemorySessionStore({ clock: testClock() }),
    identityProvider: providerFor(token),
    sessionSecret: generateSecret(48),
    pages: PAGES,
    tree: options.tree ?? "govuk",
    forward: { conduitUrl: options.conduitUrl ?? conduit.url, bodyMaxBytes: 1024, uploadMaxBytes: 1024, upstreamTimeoutSeconds: 2 },
  });
  const res = await request(app).get("/session/sign-in");
  if (res.status !== 302) throw new Error(`sign-in answered ${res.status}`);
  const cookie = cookieFrom(res);
  const home = await request(app).get("/").set("Cookie", cookie);
  conduit.calls.splice(0);
  return { app, conduit, reader, options: conduitOptions, cookie, csrf: csrfFromPage(home.text) };
}

const getAs = (w: World, path: string) => request(w.app).get(path).set("Cookie", w.cookie);
const calls = (c: BoardsConduit): string[] => c.calls.map((call) => `${call.method} ${call.url}`);
const listCall = (caseId = CASE): string => `GET /v1/investigations/${encodeURIComponent(caseId)}/boards`;
const boardCall = (boardId: string, caseId = CASE): string => `GET /v1/investigations/${encodeURIComponent(caseId)}/boards/${encodeURIComponent(boardId)}`;

async function closedAddress(): Promise<string> {
  const server = createServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  await new Promise<void>((resolve) => server.close(() => resolve()));
  return `http://127.0.0.1:${port}`;
}

// ------------------------------------------------------------------------------------------------ reading a page

const strip = (html: string): string => html.replace(/<!--[\s\S]*?-->/g, "");
const attr = (tag: string, name: string): string | undefined => new RegExp(`\\s${name}="([^"]*)"`).exec(tag)?.[1];
const withoutNonce = (html: string): string => html.replace(/nonce="[^"]*"/g, 'nonce="N"');
const unescape = (s: string): string => s.replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"');

function mainOf(html: string): string {
  const found = /<main\b[^>]*>([\s\S]*?)<\/main>/.exec(strip(html));
  return found ? (found[1] as string) : "";
}
const mainText = (html: string): string => unescape(textOf(mainOf(html)));

interface Stop {
  tag: string;
  href: string | undefined;
  text: string;
}

function focusable(html: string): Stop[] {
  const stops: Stop[] = [];
  for (const m of strip(html).matchAll(/<(a|button)\b([^>]*)>([\s\S]*?)<\/\1>|<(input|select|textarea)\b([^>]*)>/g)) {
    const tag = (m[1] ?? m[4]) as string;
    const attrs = (m[2] ?? m[5]) as string;
    if (tag === "input" && /\stype="hidden"/.test(attrs)) continue;
    if (tag === "a" && attr(attrs, "href") === undefined) continue;
    const href = attr(attrs, "href");
    stops.push({ tag, href: href === undefined ? undefined : unescape(href), text: unescape(textOf(m[3] ?? "")) });
  }
  return stops;
}

const headings = (html: string): { level: number; text: string }[] =>
  [...strip(html).matchAll(/<h([1-6])\b([^>]*)>([\s\S]*?)<\/h\1>/g)].map((m) => ({ level: Number(m[1]), text: unescape(textOf(m[3] as string)) }));

interface Row {
  head: string;
  href: string | undefined;
  cells: string[];
}

interface Table {
  caption: string;
  columns: string[];
  rows: Row[];
}

function tablesOf(html: string): Table[] {
  return [...mainOf(html).matchAll(/<table\b[^>]*>([\s\S]*?)<\/table>/g)].map((found) => {
    const inner = found[1] as string;
    const caption = unescape(textOf(/<caption\b[^>]*>([\s\S]*?)<\/caption>/.exec(inner)?.[1] ?? ""));
    const head = /<thead\b[^>]*>([\s\S]*?)<\/thead>/.exec(inner)?.[1] ?? "";
    const columns = [...head.matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/g)].map((m) => unescape(textOf(m[1] as string)));
    const body = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/.exec(inner)?.[1] ?? "";
    const rows = [...body.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((row) => {
      const cells = [...(row[1] as string).matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/g)].map((c) => c[1] as string);
      const link = /<a\b([^>]*)>([\s\S]*?)<\/a>/.exec(cells[0] ?? "");
      return {
        head: unescape(textOf(link?.[2] ?? cells[0] ?? "")),
        href: link ? unescape(attr(link[1] as string, "href") ?? "") : undefined,
        cells: cells.map((c) => unescape(textOf(c))),
      };
    });
    return { caption, columns, rows };
  });
}
const tableCalled = (html: string, caption: string): Table | undefined => tablesOf(html).find((t) => t.caption === caption);

/** Every fault in a page's structure, in words: the same function reads the real page and each planted one (BD14). */
function structureProblems(html: string): string[] {
  const page = strip(html);
  const found: string[] = [];
  if (!/<html\b[^>]*\slang="en-GB"/.test(page)) found.push('the page is not lang="en-GB"');
  if (!/<title>[^<]+<\/title>/.test(page)) found.push("the page has no title");
  const mains = [...page.matchAll(/<main\b([^>]*)>/g)];
  if (mains.length !== 1) found.push(`the page has ${mains.length} main landmarks, not one`);
  const mainId = attr((mains[0]?.[1] as string | undefined) ?? "", "id");
  if ([...page.matchAll(/<header\b/g)].length !== 1) found.push("the page has not exactly one header (banner) landmark");
  const first = focusable(page)[0];
  if (!first || first.href !== `#${mainId}` || !/skip to main content/i.test(first.text)) found.push(`the first stop is not the skip link (it is ${JSON.stringify(first)})`);
  const h = headings(mainOf(page));
  if (h.filter((x) => x.level === 1).length !== 1) found.push(`the main landmark has ${h.filter((x) => x.level === 1).length} headings of the first level, not one`);
  h.forEach((x, i) => {
    const before = h[i - 1]?.level ?? 0;
    if (x.level > before + 1) found.push(`the heading ${JSON.stringify(x.text)} skips from level ${before} to ${x.level}`);
  });
  for (const t of mainOf(page).matchAll(/<table\b[^>]*>([\s\S]*?)<\/table>/g)) {
    const inner = t[1] as string;
    const caption = /<caption\b[^>]*>([\s\S]*?)<\/caption>/.exec(inner);
    if (!caption || textOf(caption[1] as string) === "") found.push("a table has no caption");
    const head = /<thead\b[^>]*>([\s\S]*?)<\/thead>/.exec(inner);
    const heads = head ? [...(head[1] as string).matchAll(/<th\b([^>]*)>/g)] : [];
    if (heads.length === 0 || heads.some((c) => attr(c[1] as string, "scope") !== "col")) found.push('a table has a column header that is not a th scope="col"');
    const body = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/.exec(inner);
    const rows = body ? [...(body[1] as string).matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)] : [];
    if (rows.length === 0) found.push("a table has no row");
    for (const row of rows) {
      const firstCell = /<(th|td)\b([^>]*)>/.exec(row[1] as string);
      if (!firstCell || firstCell[1] !== "th" || attr(firstCell[2] as string, "scope") !== "row") found.push('a table row does not start with a th scope="row"');
    }
  }
  const forms = [...page.matchAll(/<form\b([^>]*)>/g)].map((f) => `${attr(f[1] as string, "method") ?? ""} ${attr(f[1] as string, "action") ?? ""}`);
  if (forms.some((f) => f !== "post /session/sign-out")) found.push(`a form that is not the sign-out: ${forms.join("; ")}`);
  if (/<(form|button|input|select|textarea)\b/.test(mainOf(page))) found.push("the main landmark holds a control or a form");
  return found;
}

/** Every thing in a page that needs a script, an inline rule or a tab stop out of order (BD15). */
function scriptsOffProblems(html: string): string[] {
  const page = strip(html);
  const found: string[] = [];
  for (const s of page.matchAll(/<script\b([^>]*)>/g)) {
    if (attr(s[1] as string, "type") !== "application/json") found.push(`a script element that is not a data block: <script${s[1] as string}>`);
  }
  if (/\son[a-z]+\s*=/i.test(page)) found.push("an event-handler attribute");
  if (/\sstyle\s*=/i.test(page)) found.push("an inline style attribute");
  if (/<style\b/i.test(page)) found.push("a style element");
  if (/javascript:/i.test(page)) found.push("a javascript: address");
  for (const t of page.matchAll(/\stabindex="(-?\d+)"/g)) if (Number(t[1]) > 0) found.push(`a tab stop of ${t[1] as string}`);
  return found;
}

/** What the refusal must be: the unknown path's page, byte for byte but for the script nonce. */
const refusalProblems = (refused: { status: number; text: string }, unknown: { status: number; text: string }): string[] =>
  refused.status === unknown.status && withoutNonce(refused.text) === withoutNonce(unknown.text) ? [] : ["the refusal is not the page of a path nothing serves"];

/** Words and identifiers the page must never show: the Conduit's refusals, a right's name, an account's, a document's or an item's id,
 * what the reader may not see, a property of a drawn item, and any word that a thing is hidden or not shared. */
const NEVER = [
  "investigation_not_found", "board_not_found", "right_required", "investigate", "acct-", "doc-", "i-tall", "layer-of-the-case", "ds-ledger",
  "Hidden informant", "Meets", "Drives", "Blake's own lead", "Blake's private board", "Another case's board", "SECRET<", "not this name", "9-000-001",
  "hidden", "Hidden", "not shared", "Old lead", "Gone lead", "ceiling", "A document of the case", UNIT,
];
/** Read in the main landmark: the layout's sign-out form holds a hidden input, which is the layout's and says nothing of the board. */
/** Any sign of an item the reader may not see (BD7): a fourth drawn item counted, a word that something is withheld or unseen. */
const hiddenProblems = (html: string): string[] =>
  [/\b4 drawn items\b/, /\b4\b/, /withheld|cannot see|may not see|not shown to you|hidden/i].filter((re) => re.test(mainText(html))).map((re) => `the page says ${re}`);
const neverProblems = (html: string): string[] => NEVER.filter((word) => mainOf(html).includes(word)).map((word) => `the page shows ${JSON.stringify(word)}`);

// ------------------------------------------------------------------------------------------------ what the page should draw

const itemById = (id: string): Item => ITEMS.find((i) => i.id === id) as Item;
const boardById = (id: string): Board => BOARDS.find((b) => b.id === id) as Board;
const NAME_KEYS = ["name", "family_name", "value_normalised", "account_number", "title"] as const;

/** What the React board calls an item (`apps/workspace/src/boards/boardModel.ts`'s `itemLabel`), restated for the test's own world. */
function labelOf(item: Item): string {
  if (item.drawn) return item.drawn.label;
  for (const key of NAME_KEYS) {
    const value = item.properties[key];
    if (typeof value === "string" && value.trim()) {
      const given = item.properties["given_names"];
      if (key === "family_name" && typeof given === "string" && given.trim()) return `${given} ${value}`;
      return value;
    }
  }
  return `Unnamed ${item.type}`;
}
const gradingSaid = (g: { scheme: string; source: string; intelligence: string; handling: string }): string => `${g.source}${g.intelligence}${g.handling} (${g.scheme})`;

// ------------------------------------------------------------------------------------------------ no source (until GG4b)

/** A board with an item drawn from a note alone, one from a document alone and one from both, a drawn link carrying each, and a loaded
 * item and link beside them. No source of any of them may reach the page: the route sends a document's id to every reader of the board,
 * and a drawn item needs a note or a document, so even "no note" would tell a reader a document is there (the owner's ruling). */
const SOURCES_OF: Record<string, { source_note: string | null; source_document: string | null }> = {
  "d-s-note": { source_note: "Overheard at the chandlery", source_document: null },
  "d-s-doc": { source_note: null, source_document: "doc-sealed-statement" },
  "d-s-both": { source_note: "Copied from the berth register", source_document: "doc-berth-register" },
  "l-s-note": { source_note: "Told by the night watchman", source_document: null },
  "l-s-doc": { source_note: null, source_document: "doc-sealed-intercept" },
  "l-s-both": { source_note: "Read in the pilot log", source_document: "doc-pilot-log" },
};
const sourced = (id: string, label: string): NonNullable<Item["drawn"]> => drawnBy(ALEX, "b-sources", `i-${id}`, label, SOURCES_OF[id]);
const SOURCE_ITEMS: Item[] = [
  { id: "n-s-vessel", type: "Vessel", properties: { name: "Grey Heron" }, marking: "OFFICIAL" },
  { id: "n-s-owner", type: "Person", properties: { name: "Ira Vale" }, marking: "OFFICIAL" },
  { id: "d-s-note", type: "Person", properties: {}, marking: "OFFICIAL", drawn: sourced("d-s-note", "First lead") },
  { id: "d-s-doc", type: "Person", properties: {}, marking: "OFFICIAL", drawn: sourced("d-s-doc", "Second lead") },
  { id: "d-s-both", type: "Person", properties: {}, marking: "OFFICIAL", drawn: sourced("d-s-both", "Third lead") },
];
const SOURCE_LINKS: Link[] = [
  { id: "l-s-note", type: "KNOWS", source: "d-s-note", target: "n-s-owner", marking: "OFFICIAL", drawn: sourced("l-s-note", "First tie") },
  { id: "l-s-doc", type: "KNOWS", source: "d-s-doc", target: "n-s-owner", marking: "OFFICIAL", drawn: sourced("l-s-doc", "Second tie") },
  { id: "l-s-both", type: "KNOWS", source: "d-s-both", target: "n-s-vessel", marking: "OFFICIAL", drawn: sourced("l-s-both", "Third tie") },
  { id: "l-s-loaded", type: "OWNS", source: "n-s-owner", target: "n-s-vessel", marking: "OFFICIAL" },
];
const SOURCE_BOARD: Board = { id: "b-sources", case_id: CASE, name: "Where from", created_by: ALEX, created_at: "2026-11-12T10:00:00Z", shared: false, references: ["n-s-vessel", "n-s-owner"], drawn: ["d-s-note", "d-s-doc", "d-s-both"] };
const sourceWorld = (): Promise<World> => world({ boards: [SOURCE_BOARD], items: SOURCE_ITEMS, links: SOURCE_LINKS });
const NOTES_AND_DOCUMENTS: string[] = Object.values(SOURCES_OF).flatMap((s) => [s.source_note, s.source_document].filter((v): v is string => v !== null));
/** What the drawn and links tables must never say. "Source" is matched in any case. */
const SOURCE_WORDS = [/no note given/i, /source/i, /a dataset this case reads/i];

/** Every sign of a source on a board's page, in words: a note's text or a document's id anywhere in the whole HTML, and a source's words
 * in the drawn or links table. The same function reads the real page and each planted one. */
function sourceProblems(html: string): string[] {
  const whole = unescape(html);
  const found = NOTES_AND_DOCUMENTS.filter((value) => whole.includes(value)).map((value) => `the page holds ${JSON.stringify(value)}`);
  const tables = [...mainOf(html).matchAll(/<table\b[^>]*>[\s\S]*?<\/table>/g)].map((m) => m[0]);
  for (const caption of [BOARDS_WORDS.drawnCaption, BOARDS_WORDS.linksCaption]) {
    const table = tables.find((t) => t.includes(`>${caption}</caption>`));
    if (table === undefined) {
      found.push(`there is no table captioned ${JSON.stringify(caption)} to read`);
      continue;
    }
    for (const word of SOURCE_WORDS) {
      const said = word.exec(unescape(textOf(table)));
      if (said) found.push(`the table ${JSON.stringify(caption)} says ${JSON.stringify(said[0])}`);
    }
  }
  return found;
}

/** Every fault in the list as drawn against what the route sent: the same function reads the real page and each planted one (BD1). */
function listProblems(html: string, w: World, ids: string[]): string[] {
  const table = tableCalled(html, BOARDS_WORDS.caption);
  if (!table) return ["the list has no table captioned as the boards"];
  const found: string[] = [];
  if (JSON.stringify(table.columns) !== JSON.stringify(BOARDS_WORDS.columns)) found.push(`the columns are ${JSON.stringify(table.columns)}`);
  if (table.rows.length !== ids.length) found.push(`${table.rows.length} rows were drawn for ${ids.length} boards sent`);
  ids.forEach((id, i) => {
    const row = table.rows[i];
    if (!row) return;
    const sent = boardOf(boardById(id), w.reader, w.options) as { name: string; shared: boolean; start: "blank" | "view" | "selection"; drawn: number; created_at: string };
    if (row.head !== sent.name) found.push(`row ${i} is ${JSON.stringify(row.head)}, not ${JSON.stringify(sent.name)}`);
    if (row.href !== boardOfPath(id)) found.push(`row ${i}'s link is ${JSON.stringify(row.href)}, not ${boardOfPath(id)}`);
    const want = [sent.shared ? BOARDS_WORDS.shared : BOARDS_WORDS.private, BOARDS_WORDS.drawnCount(sent.drawn), utcStampOf(sent.created_at)];
    if (JSON.stringify(row.cells.slice(1)) !== JSON.stringify(want)) found.push(`row ${i}'s cells are ${JSON.stringify(row.cells.slice(1))}, not ${JSON.stringify(want)}`);
  });
  return found;
}

/** Every fault in one board's tables as drawn against what the route sent this reader (BD3, BD4, BD7). */
function boardProblems(html: string, w: World, boardId: string): string[] {
  const opened = openedOf(boardById(boardId), w.reader, w.options, UNIT) as { nodes: { id: string }[]; edges: { id: string; type: string; source: string; target: string }[] };
  const shownItems = opened.nodes.map((n) => itemById(n.id));
  const drawnItems = shownItems.filter((i) => i.drawn);
  const loadedItems = shownItems.filter((i) => !i.drawn);
  const found: string[] = [];
  const drawnTable = tableCalled(html, BOARDS_WORDS.drawnCaption);
  if (drawnItems.length > 0) {
    if (!drawnTable) found.push("no table of drawn items");
    else {
      if (JSON.stringify(drawnTable.columns) !== JSON.stringify(BOARDS_WORDS.drawnColumns)) found.push(`the drawn columns are ${JSON.stringify(drawnTable.columns)}`);
      if (drawnTable.rows.length !== drawnItems.length) found.push(`${drawnTable.rows.length} drawn rows for ${drawnItems.length} drawn items sent`);
      drawnItems.forEach((item, i) => {
        const d = item.drawn as NonNullable<Item["drawn"]>;
        const want = [`${d.label} ${BOARDS_WORDS.drawnNote}`, item.type, item.marking, gradingSaid(d.grading)];
        if (JSON.stringify(drawnTable.rows[i]?.cells) !== JSON.stringify(want)) found.push(`drawn row ${i} is ${JSON.stringify(drawnTable.rows[i]?.cells)}, not ${JSON.stringify(want)}`);
      });
    }
  } else if (drawnTable) found.push("a drawn table with no drawn item sent");
  const loadedTable = tableCalled(html, BOARDS_WORDS.loadedCaption);
  if (loadedItems.length > 0) {
    if (!loadedTable) found.push("no table of loaded items");
    else {
      if (JSON.stringify(loadedTable.columns) !== JSON.stringify(BOARDS_WORDS.loadedColumns)) found.push(`the loaded columns are ${JSON.stringify(loadedTable.columns)}`);
      if (loadedTable.rows.length !== loadedItems.length) found.push(`${loadedTable.rows.length} loaded rows for ${loadedItems.length} loaded items sent`);
      loadedItems.forEach((item, i) => {
        const want = [`${labelOf(item)} ${BOARDS_WORDS.loadedNote}`, item.type, item.marking];
        if (JSON.stringify(loadedTable.rows[i]?.cells) !== JSON.stringify(want)) found.push(`loaded row ${i} is ${JSON.stringify(loadedTable.rows[i]?.cells)}, not ${JSON.stringify(want)}`);
      });
    }
  } else if (loadedTable) found.push("a loaded table with no loaded item sent");
  const linksTable = tableCalled(html, BOARDS_WORDS.linksCaption);
  if (opened.edges.length > 0) {
    if (!linksTable) found.push("no table of links");
    else {
      if (JSON.stringify(linksTable.columns) !== JSON.stringify(BOARDS_WORDS.linkColumns)) found.push(`the link columns are ${JSON.stringify(linksTable.columns)}`);
      if (linksTable.rows.length !== opened.edges.length) found.push(`${linksTable.rows.length} link rows for ${opened.edges.length} links sent`);
      opened.edges.forEach((edge, i) => {
        const link = LINKS.find((l) => l.id === edge.id) as Link;
        const d = link.drawn;
        const name = d ? d.label : link.type.toLowerCase().replaceAll("_", " ");
        const want = [
          name,
          link.type,
          labelOf(itemById(link.source)),
          labelOf(itemById(link.target)),
          d ? BOARDS_WORDS.drawn : BOARDS_WORDS.loaded,
          link.marking,
          d ? gradingSaid(d.grading) : BOARDS_WORDS.notGraded,
        ];
        if (JSON.stringify(linksTable.rows[i]?.cells) !== JSON.stringify(want)) found.push(`link row ${i} is ${JSON.stringify(linksTable.rows[i]?.cells)}, not ${JSON.stringify(want)}`);
      });
    }
  } else if (linksTable) found.push("a links table with no link sent");
  return found;
}

/** What an empty list must be (BD2): said in words, with no table or part of one. */
const emptyListProblems = (html: string): string[] => {
  const found: string[] = [];
  if (!mainText(html).includes(BOARDS_WORDS.noBoards)) found.push("the empty list is not said in words");
  if (/<table|<th\b|<caption/.test(mainOf(html))) found.push("the empty list draws a table or part of one");
  return found;
};

/** What a failed read must be (BD10): the words, as an alert, and no table or part of one. */
const failedProblems = (html: string): string[] => {
  const found: string[] = [];
  if (!/<p role="alert">[^<]*could not be read/.test(mainOf(html))) found.push("the failure is not said as an alert");
  if (/<table|<th\b|<caption/.test(mainOf(html))) found.push("a failed read draws a table or part of one");
  return found;
};

/** What the cap's refusal must be (BD8): its three options in words, and nothing of the board. */
const tooLargeProblems = (html: string): string[] => {
  const found: string[] = [];
  const text = mainText(html);
  if (!text.includes(BOARDS_WORDS.tooLargeTitle)) found.push("the board's size is not said");
  for (const option of Object.values(BOARDS_WORDS.optionWords)) if (!text.includes(option)) found.push(`the option ${JSON.stringify(option)} is not said`);
  if (/<table|<th\b|<caption/.test(mainOf(html))) found.push("a board past the cap draws a table or part of one");
  for (const label of ["Unknown male", "White van", "Morning Star", "Rowan Hale"]) if (text.includes(label)) found.push(`a board past the cap draws ${label}`);
  return found;
};

const callProblems = (made: string[], want: string[]): string[] => (JSON.stringify(made) === JSON.stringify(want) ? [] : [`the page asked ${JSON.stringify(made)}, not ${JSON.stringify(want)}`]);

// ------------------------------------------------------------------------------------------------ the sources

const SOURCES = ["server/boards.ts", "server/views/boardsWords.ts", "tree-govuk/boards.njk"];
const sourcesOfThePage = (): { name: string; text: string }[] => SOURCES.map((name) => ({ name, text: read(PAGES_DIR, name) }));
const withoutComments = (text: string): string => text.replace(/\/\*[\s\S]*?\*\/|\/\/.*$|\{#[\s\S]*?#\}/gm, "");
/** The page does not choose what is drawn: no call in its code removes, cuts, sorts or turns a row round (decision 5). The census's own
 * filters (lists of field names, not of rows) and the split of what was sent into drawn and loaded (each element in one table, in the
 * order sent, none left out: BD3 counts both) are the words module's named ones. */
const NAMED_FILTERS = [
  ".filter((field) => !NOT_SENT.includes(`${model}.${field}`) && !MAY_BE_ABSENT.includes(`${model}.${field}`))",
  ".filter((node) => drawnIds.has(node.id))",
  ".filter((node) => !drawnIds.has(node.id))",
];
const CHOOSING = /\.(?:filter|slice|splice|sort|toSorted|reverse|toReversed|shift|pop)\s*\(|\b(?:continue|break)\s*;|\|\s*(?:sort|reverse|first|last|batch|slice|reject|select|selectattr|rejectattr)\b/;
const choosingProblems = (sources: { name: string; text: string }[]): string[] =>
  sources
    .map((s) => ({ ...s, text: NAMED_FILTERS.reduce((t, named) => t.replaceAll(named, ""), withoutComments(s.text)) }))
    .filter((s) => CHOOSING.test(s.text))
    .map((s) => `${s.name} chooses what is drawn: ${CHOOSING.exec(s.text)?.[0] ?? ""}`);
const AMERICAN = /\b(?:color|colors|organization|organizations|center|centers|authorize|authorized|behavior|license|licenses|analyze|favorite|catalog)\b/i;

// ------------------------------------------------------------------------------------------------ the bodies, for the census and the reader

const sampleReader: Reader = { token: "t", id: ALEX, unit: UNIT, rights: ["investigate"], cases: [CASE], clearance: "OFFICIAL-SENSITIVE" };
const sampleOptions: BoardsConduitOptions = { readers: [sampleReader], cases: CASES, boards: BOARDS, items: ITEMS, links: LINKS };
const listBody = (): Record<string, unknown>[] => ALEXS.map((id) => boardOf(boardById(id), sampleReader, sampleOptions));
const openedBody = (): Record<string, unknown> => JSON.parse(JSON.stringify(openedOf(boardById("b-quay"), sampleReader, sampleOptions, UNIT))) as Record<string, unknown>;
/** The cap's refusal as the route sends it (`LimitExceeded`). */
const limitBody = (): Record<string, unknown> => ({ error: "limit_exceeded", cap_kind: "nodes", cap: 50000, would_be: 50012, options: ["save_as_view", "filter", "promote_to_batch"] });
const quayView = (body: unknown): unknown => boardView(CASE, "b-quay", body);

type Json = Record<string, unknown>;
const nodeIn = (opened: Json, id: string): Json => (opened["nodes"] as Json[]).find((n) => n["id"] === id) as Json;
const edgeIn = (opened: Json, id: string): Json => (opened["edges"] as Json[]).find((e) => e["id"] === id) as Json;
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

/** A different valid value for each field of each model: a drawn field must change a page with it (the page still drawn), a checked
 * field must make the body one the page cannot draw from, and a left-out field must change nothing. A function is given the bodies, for a
 * value made from another part of them. */
const OTHER_GRADING = { scheme: "3x5x2", source: "C", intelligence: "4", handling: "P" };
const OTHER: Record<string, Record<string, unknown>> = {
  Board: { id: "b-renamed", case_id: "c-other", name: "Renamed board", created_by: "acct-other", created_at: "2025-01-03T04:05:00Z", shared: true, drawn: 9, start: "view" },
  BoardOpened: {
    board: { id: "b-quay", case_id: CASE, name: "Another name", created_by: ALEX, created_at: "2026-11-10T09:30:00Z", shared: false, drawn: 3, start: "selection" },
    nodes: (b: Bodies) => [...(b.opened["nodes"] as Json[])].reverse(),
    edges: (b: Bodies) => [...(b.opened["edges"] as Json[])].reverse(),
    drawn: [],
    items: {},
    layout: {},
    missing: 4,
    node_types: [],
    link_types: [],
    markings: [],
    ceiling: null,
    grading_scheme: "3x5x2",
    grading_grades: null,
    may_draw: false,
    may_promote: true,
  },
  Node: {
    id: "n-owner-2",
    type: "Company",
    properties: { name: "Hale Shipping" },
    // On the drawn tall man (`TARGET`): another drawn provenance, another label.
    provenance: (b: Bodies) => {
      const other = copy(nodeIn(b.opened, "d-tall")["provenance"] as Json);
      (other["drawn"] as Json)["label"] = "Tall man, renamed";
      return other;
    },
    handling: (b: Bodies) => ({ ...(nodeIn(b.opened, "n-owner")["handling"] as Json), classification: "OFFICIAL" }),
    resolution: { cluster_id: "k-1" },
    audit: { revision: 2 },
    datasets: ["ds-other"],
  },
  Edge: {
    id: "l-seen-2",
    type: "EMPLOYS",
    source: "n-vessel",
    target: "d-crew",
    properties: { since: "2020" },
    interval: { valid_from: "2020-01-01T00:00:00Z", valid_to: null },
    occurrences: 5,
    weight: 0.5,
    basis: "probabilistic",
    // Another drawn link's provenance: another label, grading and note.
    provenance: (b: Bodies) => copy(edgeIn(b.opened, "l-used")["provenance"]),
    handling: (b: Bodies) => ({ ...(edgeIn(b.opened, "l-seen")["handling"] as Json), classification: "OFFICIAL-SENSITIVE" }),
    audit: { revision: 3 },
    datasets: ["ds-other"],
  },
  Provenance: {
    state: "inferred",
    sources: [],
    sources_withheld: true,
    extracted_by: "a model",
    extraction_confidence: 0.4,
    first_seen: "2025-01-03T04:05:00Z",
    last_confirmed: "2025-02-03T04:05:00Z",
    confirmed_by: "acct-other",
    drawn: (b: Bodies) => ({ ...copy((nodeIn(b.opened, "d-tall")["provenance"] as Json)["drawn"] as Json), label: "Another assertion" }),
    gazetteer: "gazetteer-osm-x",
  },
  DrawnAssertion: { provenance_class: "analyst_guessed", item_id: "i-other", asserted_by: "acct-other", board_id: "b-other", case_id: "c-other", label: "Another label", grading: OTHER_GRADING, original_grading: OTHER_GRADING, source_note: "Another note", source_document: "doc-another", icon: "anchor" },
  Grading: { scheme: "3x5x2", source: "C", intelligence: "4", handling: "P" },
  Handling: { classification: "OFFICIAL", handling_code: "H9", action_code: "act", sanitisation_code: "san", originator: "unit-o", owning_unit: "unit-p", review_date: "2027-01-01", legal_basis: "a basis" },
  LimitExceeded: { error: "conflict", cap_kind: "edges", cap: 250000, would_be: 250031, options: ["promote_to_batch", "filter", "save_as_view"] },
};

interface Bodies {
  list: unknown;
  opened: Record<string, unknown>;
  limit: Record<string, unknown>;
}
const bodies = (): Bodies => ({ list: listBody(), opened: openedBody(), limit: limitBody() });

/** Where a field is changed, when not where its model's others are: the node's provenance on a drawn node (a loaded one carries no
 * assertion to change). */
const TARGET: Record<string, (b: Bodies) => Json[]> = {
  "Node.provenance": (b) => [nodeIn(b.opened, "d-tall")],
};

/** Where each model is changed in the bodies: a Board in the list's first row and in the opened board, a Node the loaded owner (a link's
 * end), an Edge the drawn link to it, the drawn tall man's provenance, assertion and grading, the owner's handling, the cap's refusal. */
function targetsOf(b: Bodies, model: string, field: string): Json[] {
  const special = TARGET[`${model}.${field}`];
  if (special) return special(b);
  const opened = b.opened;
  const provenance = nodeIn(opened, "d-tall")["provenance"] as Json;
  switch (model) {
    case "Board":
      return [(b.list as Json[])[0] as Json, opened["board"] as Json];
    case "BoardOpened":
      return [opened];
    case "Node":
      return [nodeIn(opened, "n-owner")];
    case "Edge":
      return [edgeIn(opened, "l-seen")];
    case "Provenance":
      return [provenance];
    case "DrawnAssertion":
      return [provenance["drawn"] as Json];
    case "Grading":
      return [(provenance["drawn"] as Json)["grading"] as Json];
    case "Handling":
      return [nodeIn(opened, "n-owner")["handling"] as Json];
    case "LimitExceeded":
      return [b.limit];
    default:
      throw new Error(`no model ${model}`);
  }
}

/** The bodies with one field of one model changed (or removed, `value` undefined; a function is called with the bodies first). */
function withField(model: string, field: string, value: unknown): Bodies {
  const b = bodies();
  const given = typeof value === "function" ? (value as (b: Bodies) => unknown)(b) : value;
  for (const target of targetsOf(b, model, field)) {
    if (given === undefined) delete target[field];
    else target[field] = copy(given);
  }
  return b;
}

interface Drawn {
  pages: { html: string; status: number }[];
}

/** Two signed-in services for `drawn`: one whose list and board answer, one whose board is past the cap. A census draws every field's
 * bodies through one pair: a new pair for each used most of the Mac's local ports in one run of this file, and the next run to want one
 * failed with `EADDRNOTAVAIL`. */
interface Pair {
  open: World;
  capped: World;
}
const pair = async (): Promise<Pair> => ({ open: await world(), capped: await world() });

/** The three pages as the real service draws them from these bodies (the fixture serves them through its real refusals): the list, the
 * board, and the board past the cap. The fixture reads what it is to answer at each request. */
async function drawn(b: Bodies, services?: Pair): Promise<Drawn> {
  const { open, capped } = services ?? (await pair());
  open.options.list_answer = { status: 200, body: b.list };
  open.options.board_answer = { status: 200, body: b.opened };
  capped.options.board_answer = { status: 409, body: b.limit };
  const list = await getAs(open, listOf());
  const one = await getAs(open, boardOfPath("b-quay"));
  const cap = await getAs(capped, boardOfPath("b-quay"));
  return { pages: [list, one, cap].map((res) => ({ html: mainOf(res.text), status: res.status })) };
}

type Census = Record<string, { readonly drawn: readonly string[]; readonly checked: readonly string[]; readonly left: readonly string[] }>;

/** Every field a census puts in the wrong list (BD12): a drawn field that changes no page that is still drawn, a checked field the page
 * still draws from when it changes, a left-out field that changes a page. The same function reads the real census and each planted one
 * (BD17). */
async function censusProblems(census: Census): Promise<string[]> {
  const found: string[] = [];
  const services = await pair();
  const base = await drawn(bodies(), services);
  if (JSON.stringify(base.pages.map((p) => p.status)) !== "[200,200,409]") return [`the pages answered ${base.pages.map((p) => p.status).join(", ")}`];
  for (const [model, { drawn: drawnFields, checked, left }] of Object.entries(census)) {
    const fields = [...drawnFields, ...checked, ...left];
    if (JSON.stringify(Object.keys(OTHER[model] ?? {}).sort()) !== JSON.stringify(fields.filter((f) => !NOT_SENT.includes(`${model}.${f}`)).sort())) found.push(`the census of ${model} is not the fields the test can change`);
    for (const field of fields) {
      if (NOT_SENT.includes(`${model}.${field}`)) continue;
      const changed = await drawn(withField(model, field, (OTHER[model] as Record<string, unknown>)[field]), services);
      const pairs = changed.pages.map((page, i) => ({ page, was: base.pages[i] as { html: string; status: number } }));
      const redrawn = pairs.some(({ page, was }) => page.status === was.status && page.html !== was.html);
      const refused = pairs.some(({ page, was }) => page.status !== was.status);
      const moved = pairs.some(({ page, was }) => page.html !== was.html || page.status !== was.status);
      if (drawnFields.includes(field) && !redrawn) found.push(`${model}.${field} is drawn but changes no page that is still drawn`);
      if (checked.includes(field) && !refused) found.push(`${model}.${field} is checked but the page still draws from a body with it changed`);
      if (left.includes(field) && moved) found.push(`${model}.${field} is left out but changes the page`);
    }
  }
  return found;
}

/** A shape of the wrong kind for a field: a string where the field is an object, an object otherwise. */
const OBJECT_FIELDS = new Set([
  "BoardOpened.board", "BoardOpened.items", "BoardOpened.layout", "BoardOpened.grading_grades",
  "Node.properties", "Node.provenance", "Node.handling", "Node.resolution", "Node.audit",
  "Edge.properties", "Edge.interval", "Edge.provenance", "Edge.handling", "Edge.audit",
  "DrawnAssertion.grading", "DrawnAssertion.original_grading",
]);
const wrongOf = (model: string, field: string): unknown => (OBJECT_FIELDS.has(`${model}.${field}`) ? "not an object" : { wrong: true });

// ------------------------------------------------------------------------------------------------ the cases

describe("the boards page on the GOV.UK tree (scenario BD)", () => {
  it("BD1: a case's boards are a table in the order sent, each name a link to its board, with sharing, start, the route's count and when made", async () => {
    const w = await world();
    const res = await getAs(w, listOf());
    expect(res.status).toBe(200);
    expect(listProblems(res.text, w, ALEXS)).toEqual([]);
    expect(headings(mainOf(res.text))[0]).toEqual({ level: 1, text: BOARDS_WORDS.listTitle });
    expect(neverProblems(res.text)).toEqual([]);
    // The route's own count: the quay board has four drawn items, one hidden from Alex by its marking; three are said, never four.
    expect(tableCalled(res.text, BOARDS_WORDS.caption)?.rows.map((r) => r.cells[2])).toEqual(["3 drawn items", "0 drawn items", "1 drawn item"]);
    expect([BOARDS_WORDS.shared, BOARDS_WORDS.private]).toEqual(["Shared with the case", "Only you"]);
    // How a board began is not said: the route's `start` says only whether a reference the reader may see is on it (`Boards.wire`).
    expect(BOARDS_WORDS.columns).toEqual(["Board", "Shared", "Drawn items", "Made"]);
    expect(mainText(res.text)).not.toMatch(/From a selection|From a view|Blank/);
    // The way back is the case's own page.
    expect(focusable(res.text).map((s) => s.href)).toContain(`/cases?case=${CASE}`);
  });

  it("BD2: a case with no board the reader may see is told so in one sentence, with no table, and a way back to the case", async () => {
    const w = await world({ boards: BOARDS.filter((b) => b.created_by === BLAKE && !b.shared) });
    const res = await getAs(w, listOf());
    expect(res.status).toBe(200);
    expect(emptyListProblems(res.text)).toEqual([]);
    expect(BOARDS_WORDS.noBoards).toBe("No boards in this case yet.");
    expect(focusable(res.text).map((s) => s.href ?? s.text)).toEqual(["#main", "Sign out", `/cases?case=${CASE}`, "/"]);
  });

  it("BD3: one board draws its facts, then its drawn items, its loaded items and its links, each in the Conduit's order", async () => {
    const w = await world();
    const res = await getAs(w, boardOfPath("b-quay"));
    expect(res.status).toBe(200);
    expect(headings(mainOf(res.text))[0]).toEqual({ level: 1, text: "Quay sketch" });
    expect(boardProblems(res.text, w, "b-quay")).toEqual([]);
    const text = mainText(res.text);
    for (const fact of [BOARDS_WORDS.private, utcStampOf("2026-11-10T09:30:00Z")]) expect(text).toContain(fact);
    // Every drawn item is said as drawn, with its marking and its grading; no source is said (the next case).
    const drawnRows = tableCalled(res.text, BOARDS_WORDS.drawnCaption)?.rows ?? [];
    expect(drawnRows.map((r) => r.head)).toEqual(["Unknown male “Tall” Drawn, not loaded", "White van Drawn, not loaded", "Night crew Drawn, not loaded"]);
    expect(drawnRows.map((r) => r.cells[2])).toEqual(["OFFICIAL", "OFFICIAL-SENSITIVE", "OFFICIAL"]);
    expect(drawnRows.map((r) => r.cells[3])).toEqual(["A11 (5x5x5)", "B21 (5x5x5)", "C32 (5x5x5)"]);
    // Four columns and no fifth: no source note, and no document by its identifier or its kind.
    expect(BOARDS_WORDS.drawnColumns).toEqual(["Item", "Type", "Marking", "Grading"]);
    expect(drawnRows.map((r) => r.cells.length)).toEqual([4, 4, 4]);
    expect(text).not.toMatch(/Seen from the harbour wall|No note given|A document of the case/);
    const loadedRows = tableCalled(res.text, BOARDS_WORDS.loadedCaption)?.rows ?? [];
    expect(loadedRows.map((r) => r.head)).toEqual([`Morning Star ${BOARDS_WORDS.loadedNote}`, `Rowan Hale ${BOARDS_WORDS.loadedNote}`]);
    expect(BOARDS_WORDS.loadedNote).toBe("A dataset this case reads: a live reference, not editable here");
    expect(neverProblems(res.text)).toEqual([]);
    // The item's name is the React board's rule: the same keys, in the same order, and the same name for an item with none.
    const react = read(CORE, "apps", "workspace", "src", "boards", "boardModel.ts");
    expect(react).toContain('const NAME_KEYS = ["name", "family_name", "value_normalised", "account_number", "title"] as const;');
    expect(read(PAGES_DIR, "server", "views", "boardsWords.ts")).toContain('const NAME_KEYS = ["name", "family_name", "value_normalised", "account_number", "title"] as const;');
    for (const line of ['if (key === "family_name" && typeof given === "string" && given.trim()) return `${given} ${value}`;', "return `Unnamed ${node.type}`;", 'if (edge.type === "SAME_AS") return "same as";', 'if (edge.type === "NOT_SAME_AS") return "not the same as";', 'return edge.type.toLowerCase().replaceAll("_", " ");']) {
      expect(react, line).toContain(line);
      expect(read(PAGES_DIR, "server", "views", "boardsWords.ts"), line).toContain(line);
    }
    const unnamed = await world({ items: ITEMS.map((i) => (i.id === "n-vessel" ? { ...i, properties: {} } : i)) });
    expect(tableCalled((await getAs(unnamed, boardOfPath("b-quay"))).text, BOARDS_WORDS.loadedCaption)?.rows[0]?.head).toBe(`Unnamed Vessel ${BOARDS_WORDS.loadedNote}`);
  });

  it("BD3: an item and a link sent with neither a note nor a document, as the Conduit sends them to a reader who may not read the document, are drawn like any other (GG4b)", async () => {
    // ADR-143 Amendment 8 item 8: an item drawn before it with a document and no note is sent to such a reader with neither, its source
    // `drawn:<item_id>`. One such item must not make the whole board unreadable, and no source is said of it either.
    const withheld = <T extends { id: string; drawn?: NonNullable<Item["drawn"]> }>(all: T[], id: string): T[] =>
      all.map((e) => (e.id === id && e.drawn ? { ...e, drawn: { ...e.drawn, source_note: null, source_document: null } } : e));
    const w = await world({ boards: [SOURCE_BOARD], items: withheld(SOURCE_ITEMS, "d-s-doc"), links: withheld(SOURCE_LINKS, "l-s-doc") });
    const res = await getAs(w, boardOfPath("b-sources"));
    expect(res.status).toBe(200);
    expect(mainText(res.text)).not.toContain(BOARDS_WORDS.unreadableBoard);
    expect((tableCalled(res.text, BOARDS_WORDS.drawnCaption)?.rows ?? []).map((r) => r.head)).toEqual(["First lead Drawn, not loaded", "Second lead Drawn, not loaded", "Third lead Drawn, not loaded"]);
    expect((tableCalled(res.text, BOARDS_WORDS.linksCaption)?.rows ?? []).map((r) => r.head)).toEqual(["First tie", "Second tie", "Third tie", "owns"]);
    expect(sourceProblems(res.text)).toEqual([]);
  });

  it("BD3: the board page sends no source: over items and links drawn from a note, a document and both, no note, document id or source word", async () => {
    const w = await sourceWorld();
    // The route does send them, so their absence from the page is the page's doing.
    const sent = JSON.stringify(openedOf(SOURCE_BOARD, w.reader, w.options, UNIT));
    for (const value of NOTES_AND_DOCUMENTS) expect(sent, value).toContain(value);
    const res = await getAs(w, boardOfPath("b-sources"));
    expect(res.status).toBe(200);
    expect(tableCalled(res.text, BOARDS_WORDS.drawnCaption)?.rows.map((r) => r.head)).toEqual(["First lead Drawn, not loaded", "Second lead Drawn, not loaded", "Third lead Drawn, not loaded"]);
    expect(tableCalled(res.text, BOARDS_WORDS.linksCaption)?.rows.map((r) => r.head)).toEqual(["First tie", "Second tie", "Third tie", "owns"]);
    expect(sourceProblems(res.text)).toEqual([]);
    expect(tableCalled(res.text, BOARDS_WORDS.linksCaption)?.columns).toEqual(["Link", "Type", "From", "To", "Drawn or loaded", "Marking", "Grading"]);
    // An item with a note and one without are drawn alike: nothing of a row says which has a document.
    const shape = (table: string): number[] => tableCalled(res.text, table)?.rows.map((r) => r.cells.length) ?? [];
    expect(shape(BOARDS_WORDS.drawnCaption)).toEqual([4, 4, 4]);
    expect(shape(BOARDS_WORDS.linksCaption)).toEqual([7, 7, 7, 7]);
    expect("noNote" in BOARDS_WORDS).toBe(false);
    expect("loadedSource" in BOARDS_WORDS).toBe(false);
  });

  it("BD4: each link is listed once, in the order sent, both ends named as the route's items name them; an end outside them is not drawn", async () => {
    const w = await world();
    const res = await getAs(w, boardOfPath("b-quay"));
    const links = tableCalled(res.text, BOARDS_WORDS.linksCaption);
    expect(links?.rows.map((r) => r.cells.slice(0, 5))).toEqual([
      ["Seen with", "KNOWS", "Unknown male “Tall”", "Rowan Hale", "Drawn, not loaded"],
      ["owns", "OWNS", "Rowan Hale", "Morning Star", "Loaded"],
      ["Used by", "USES", "Night crew", "White van", "Drawn, not loaded"],
    ]);
    expect(boardProblems(res.text, w, "b-quay")).toEqual([]);
    // A link whose end the route did not send: a body the page cannot draw from, never an end said as unknown or looked up elsewhere.
    const b = openedBody();
    (b["edges"] as Json[])[0] = { ...((b["edges"] as Json[])[0] as Json), target: "n-not-sent" };
    expect(quayView(b)).toBeUndefined();
    const w2 = await world({ board_answer: { status: 200, body: b } });
    const res2 = await getAs(w2, boardOfPath("b-quay"));
    expect(res2.status).toBe(502);
    expect(failedProblems(res2.text)).toEqual([]);
    expect(calls(w2.conduit)).toEqual([boardCall("b-quay")]);
  });

  it("BD5: every refusal is the very page of a path nothing serves, and nothing more is asked", async () => {
    const w = await world();
    const unknown = await getAs(w, NOWHERE);
    expect(unknown.status).toBe(404);
    // Someone else's private board, another case's board, a board that does not exist.
    for (const id of ["b-blake", "b-elsewhere", "b-no-such-board"]) {
      w.conduit.calls.splice(0);
      const res = await getAs(w, boardOfPath(id));
      expect(refusalProblems(res, unknown), id).toEqual([]);
      expect(calls(w.conduit), id).toEqual([boardCall(id)]);
    }
    // A case the reader holds no level on, one of another unit, one that does not exist: for the list and for a board.
    for (const caseId of ["c-unshared", "c-elsewhere", "c-no-such-case"]) {
      for (const path of [listOf(caseId), boardOfPath("b-quay", caseId)]) {
        w.conduit.calls.splice(0);
        const res = await getAs(w, path);
        expect(refusalProblems(res, unknown), path).toEqual([]);
        expect(calls(w.conduit), path).toHaveLength(1);
      }
    }
    // Values that name nothing: nothing is asked.
    for (const query of ["", "?case=", "?board=b-quay", "?case=c-harbour&case=c-other", "?case=.", "?case=..", "?case=%2E%2E", "?case=c-harbour&board=", "?case=c-harbour&board=.", "?case=c-harbour&board=..", "?case=c-harbour&board=b-quay&board=b-empty", "?case=c-harbour&board=b-quay%2Fmatches", "?case=c-harbour&board=b-quay%2Fpictures", "?case=c-harbour%2Fviews", "?case=c-harbour%2Fboards&board=b-quay", "?case=c-harbour&board=%2F"]) {
      w.conduit.calls.splice(0);
      const res = await getAs(w, `${PATH}${query}`);
      expect(refusalProblems(res, unknown), query).toEqual([]);
      expect(calls(w.conduit), query).toEqual([]);
    }
    // A reader without the right to investigate: the same page, for the list and for a board; and any other 4xx but a 401 and the cap's.
    const unrighted = await world({ rights: [] });
    const unknown2 = await getAs(unrighted, NOWHERE);
    for (const path of [listOf(), boardOfPath("b-quay")]) expect(refusalProblems(await getAs(unrighted, path), unknown2), path).toEqual([]);
    for (const status of [403, 404, 409, 422]) {
      const w3 = await world({ list_answer: { status, body: { detail: "refused" } }, board_answer: { status, body: { error: "not_the_boards_creator" } } });
      const unknown3 = await getAs(w3, NOWHERE);
      expect(refusalProblems(await getAs(w3, listOf()), unknown3), `list ${status}`).toEqual([]);
      expect(refusalProblems(await getAs(w3, boardOfPath("b-quay")), unknown3), `board ${status}`).toEqual([]);
    }
  });

  it("BD6: the withdrawn count is said to the creator when the route sends more than zero, naming none; another reader is told nothing", async () => {
    const alex = await world();
    const quay = await getAs(alex, boardOfPath("b-quay"));
    expect(mainText(quay.text)).toContain("1 item you placed has since been withdrawn.");
    expect(mainText(quay.text)).not.toContain("Old lead");
    // Two withdrawn, said in the plural.
    const two = await world({
      items: [...ITEMS, { id: "d-older", type: "Person", properties: {}, marking: "OFFICIAL", drawn: drawnBy(ALEX, "b-earlier", "i-older", "Older lead"), withdrawn: true }],
      boards: BOARDS.map((b) => (b.id === "b-quay" ? { ...b, references: [...b.references, "d-older"] } : b)),
    });
    expect(mainText((await getAs(two, boardOfPath("b-quay"))).text)).toContain("2 items you placed have since been withdrawn.");
    // The shared board's creator is Blake: Alex is sent zero and told nothing; Blake is told.
    const shift = await getAs(alex, boardOfPath("b-shift"));
    expect(mainText(shift.text)).not.toMatch(/withdrawn/);
    const blake = await world({ as: BLAKE });
    expect(mainText((await getAs(blake, boardOfPath("b-shift"))).text)).toContain("1 item you placed has since been withdrawn.");
    // A board with nothing withdrawn says nothing of it.
    expect(mainText((await getAs(alex, boardOfPath("b-empty"))).text)).not.toMatch(/withdrawn/);
    expect(BOARDS_WORDS.withdrawn(1)).toBe("1 item you placed has since been withdrawn.");
    expect(BOARDS_WORDS.withdrawn(2)).toBe("2 items you placed have since been withdrawn.");
  });

  it("BD7: an item hidden by its marking, and every link touching it, is absent from every table and count, with no gap or hidden line", async () => {
    const w = await world();
    const res = await getAs(w, boardOfPath("b-quay"));
    expect(boardProblems(res.text, w, "b-quay")).toEqual([]);
    expect(neverProblems(res.text)).toEqual([]);
    expect(tableCalled(res.text, BOARDS_WORDS.drawnCaption)?.rows).toHaveLength(3);
    expect(tableCalled(res.text, BOARDS_WORDS.linksCaption)?.rows).toHaveLength(3);
    expect(hiddenProblems(res.text)).toEqual([]);
    // The list's count is the route's, three: the hidden fourth is in none.
    expect(tableCalled((await getAs(w, listOf())).text, BOARDS_WORDS.caption)?.rows[0]?.cells[2]).toBe("3 drawn items");
    // The fixture models the route: the hidden item is in no part of what it sends, and `missing` does not count it.
    const sent = JSON.stringify(openedOf(boardById("b-quay"), w.reader, w.options, UNIT));
    expect(sent).not.toMatch(/d-secret|Hidden informant|l-secret|l-high/);
    expect((openedOf(boardById("b-quay"), w.reader, w.options, UNIT) as { missing: number }).missing).toBe(1);
  });

  it("BD8: a board past the cap is said too large with the three options in words, and no part of it is drawn", async () => {
    const w = await world({ cap: 3 });
    const res = await getAs(w, boardOfPath("b-quay"));
    expect(res.status).toBe(409);
    expect(tooLargeProblems(res.text)).toEqual([]);
    expect(headings(mainOf(res.text))[0]).toEqual({ level: 1, text: BOARDS_WORDS.tooLargeTitle });
    expect(structureProblems(res.text)).toEqual([]);
    expect(calls(w.conduit)).toEqual([boardCall("b-quay")]);
    // A cap refusal the page cannot read is could not be read, never a 404 and never a part of the board.
    for (const body of [{ error: "limit_exceeded" }, { error: "limit_exceeded", cap_kind: "nodes", cap: 3, would_be: 5, options: ["filter"] }]) {
      const w2 = await world({ board_answer: { status: 409, body } });
      const res2 = await getAs(w2, boardOfPath("b-quay"));
      expect(res2.status, JSON.stringify(body)).toBe(502);
      expect(failedProblems(res2.text)).toEqual([]);
    }
    expect(mainText(res.text)).toContain("Too many to show: 5 items against a limit of 3.");
    const linksCapped = await world({ capEdges: 2 });
    const byLinks = await getAs(linksCapped, boardOfPath("b-quay"));
    expect(byLinks.status).toBe(409);
    expect(tooLargeProblems(byLinks.text)).toEqual([]);
    expect(mainText(byLinks.text)).toContain("Too many to show: 3 links against a limit of 2.");
    expect(limitView({ error: "limit_exceeded", cap_kind: "edges", cap: 250000, would_be: 250001, options: ["save_as_view", "filter", "promote_to_batch"] })?.says).toBe(
      "Too many to show: 250,001 links against a limit of 250,000. Nothing of the board is shown.",
    );
  });

  it("BD9: the Conduit is asked as the person, each route exactly once per render, nothing of the browser's, no write, nothing unsigned", async () => {
    const w = await world();
    await getAs(w, listOf()).set("Origin", "http://example.invalid").set("Referer", "http://example.invalid/x");
    expect(callProblems(calls(w.conduit), [listCall()])).toEqual([]);
    w.conduit.calls.splice(0);
    await getAs(w, boardOfPath("b-quay")).set("Origin", "http://example.invalid");
    expect(callProblems(calls(w.conduit), [boardCall("b-quay")])).toEqual([]);
    for (const call of w.conduit.calls) {
      expect(call.headers["authorization"]).toBe(`Bearer ${w.reader.token}`);
      for (const header of ["cookie", "origin", "referer", "x-csrf-token", "x-forwarded-for"]) expect(call.headers[header], header).toBeUndefined();
    }
    w.conduit.calls.splice(0);
    const unsigned = await request(w.app).get(boardOfPath("b-quay"));
    expect(unsigned.status).toBe(302);
    expect(unsigned.headers["location"]).toBe("/session/sign-in");
    const unknown = await getAs(w, NOWHERE);
    for (const method of ["post", "put", "patch", "delete"] as const) {
      const res = await request(w.app)[method](boardOfPath("b-quay")).set("Cookie", w.cookie).set("X-CSRF-Token", w.csrf).type("form").send({ _csrf: w.csrf });
      expect(res.status, method).toBe(unknown.status);
    }
    expect(calls(w.conduit)).toEqual([]);
  });

  it("BD10: a failed read draws nothing of the boards or the board (502); an ended session says to sign in again (401)", async () => {
    const failures: [WorldOptions, string][] = [
      [{ list_answer: { status: 500, body: { detail: "boom" } } }, "list"],
      [{ list_answer: { status: 200, body: "not json" } }, "list"],
      [{ list_no_answer: true }, "list"],
      [{ board_answer: { status: 503, body: { detail: "down" } } }, "board"],
      [{ board_answer: { status: 200, body: "not json" } }, "board"],
      [{ board_no_answer: true }, "board"],
      [{ conduitUrl: await closedAddress() }, "list"],
      [{ conduitUrl: await closedAddress() }, "board"],
    ];
    for (const [options, which] of failures) {
      const w = await world(options);
      const res = await getAs(w, which === "list" ? listOf() : boardOfPath("b-quay"));
      expect(res.status, JSON.stringify(options)).toBe(502);
      expect(failedProblems(res.text), JSON.stringify(options)).toEqual([]);
      expect(mainText(res.text)).toContain(which === "list" ? BOARDS_WORDS.unreadableList : BOARDS_WORDS.unreadableBoard);
      expect(mainText(res.text)).not.toMatch(/Quay sketch|Unknown male/);
    }
    const ended = refusalWords(401, undefined, "");
    for (const options of [{ unknownBearer: true }, { list_answer: { status: 401, body: { detail: "Not authenticated" } }, board_answer: { status: 401, body: { detail: "Not authenticated" } } }] as WorldOptions[]) {
      const w = await world(options);
      for (const path of [listOf(), boardOfPath("b-quay")]) {
        const res = await getAs(w, path);
        expect(res.status, `${path} ${JSON.stringify(options)}`).toBe(401);
        expect(mainText(res.text)).toContain(unescape(ended));
      }
    }
  });

  it("BD11: a body missing any field the routes' models send, or of the wrong shape, is the could-not-be-read page, never empty", async () => {
    expect(listView(CASE, listBody())).toBeDefined();
    expect(quayView(openedBody())).toBeDefined();
    expect(limitView(limitBody())).toBeDefined();
    const models = Object.keys(REQUIRED) as (keyof typeof REQUIRED)[];
    expect([...models].sort()).toEqual(["Board", "BoardOpened", "DrawnAssertion", "Edge", "Grading", "Handling", "LimitExceeded", "Node", "Provenance"]);
    /** Every view a body of `model` reaches: the board (and the list, for a board), or the cap's refusal. */
    const viewsOf = (b: Bodies, model: string): unknown[] =>
      model === "LimitExceeded" ? [limitView(b.limit)] : model === "Board" ? [quayView(b.opened), listView(CASE, b.list)] : [quayView(b.opened)];
    let tried = 0;
    for (const model of models) {
      for (const field of REQUIRED[model]) {
        expect(viewsOf(withField(model, field, undefined), model), `${model}.${field} removed`).toEqual(viewsOf(withField(model, field, undefined), model).map(() => undefined));
        expect(viewsOf(withField(model, field, wrongOf(model, field)), model).every((v) => v === undefined), `${model}.${field} of the wrong shape`).toBe(true);
        tried += 1;
      }
    }
    expect(tried).toBe(80);
    // A field that may be absent from what is sent is not required, and is still read strictly when it is there.
    expect(MAY_BE_ABSENT).toEqual(["Provenance.drawn", "Provenance.gazetteer"]);
    expect(NOT_SENT).toEqual(["Edge.weight_components"]);
    const noGazetteer = bodies();
    expect(quayView(noGazetteer.opened)).toBeDefined();
    expect(quayView(withField("Provenance", "gazetteer", 7).opened)).toBeUndefined();
    expect(quayView(withField("Provenance", "drawn", "not an object").opened)).toBeUndefined();
    // A drawn element without its assertion, and an assertion on an element the route does not name as drawn.
    expect(quayView(withField("Provenance", "drawn", undefined).opened)).toBeUndefined();
    const extra = bodies();
    (nodeIn(extra.opened, "n-owner")["provenance"] as Json)["drawn"] = copy((nodeIn(extra.opened, "d-tall")["provenance"] as Json)["drawn"]);
    expect(quayView(extra.opened)).toBeUndefined();
    const namedButLoaded = bodies();
    (namedButLoaded.opened["drawn"] as string[]).push("n-vessel");
    expect(quayView(namedButLoaded.opened)).toBeUndefined();
    // A body that is not the one asked for: another case's board, another board.
    expect(boardView("c-other", "b-quay", openedBody())).toBeUndefined();
    expect(boardView(CASE, "b-empty", openedBody())).toBeUndefined();
    expect(listView("c-other", listBody())).toBeUndefined();
    // An element named twice, a board listed twice, a drawn id named twice.
    const twiceNode = bodies();
    (twiceNode.opened["nodes"] as Json[]).push(copy(nodeIn(twiceNode.opened, "n-vessel")));
    expect(quayView(twiceNode.opened)).toBeUndefined();
    const twiceEdge = bodies();
    (twiceEdge.opened["edges"] as Json[]).push(copy(edgeIn(twiceEdge.opened, "l-owns")));
    expect(quayView(twiceEdge.opened)).toBeUndefined();
    const twiceDrawn = bodies();
    (twiceDrawn.opened["drawn"] as string[]).push("d-tall");
    expect(quayView(twiceDrawn.opened)).toBeUndefined();
    expect(listView(CASE, [...listBody(), listBody()[0]])).toBeUndefined();
    // A drawn item with neither a note nor a document is read (GG4b; ADR-143 Amendment 8 item 8): the Conduit sends one to a reader
    // who may not read its document. A note or a document of another shape is still refused (below).
    for (const source_note of [null, "  "]) {
      const neither = bodies();
      Object.assign((nodeIn(neither.opened, "d-tall")["provenance"] as Json)["drawn"] as Json, { source_note, source_document: null });
      expect(quayView(neither.opened), JSON.stringify(source_note)).toBeDefined();
    }
    for (const [field, value] of [["source_note", 7], ["source_document", ["doc"]]] as const) {
      const misshapen = bodies();
      Object.assign((nodeIn(misshapen.opened, "d-tall")["provenance"] as Json)["drawn"] as Json, { [field]: value });
      expect(quayView(misshapen.opened), field).toBeUndefined();
    }
    // Wrong values, one field at a time.
    const wrong: [string, string, unknown][] = [
      ["Board", "start", "drawing"],
      ["Board", "drawn", -1],
      ["Board", "drawn", 1.5],
      ["Board", "created_at", "yesterday"],
      ["Board", "created_at", "7"],
      ["Board", "created_at", "2026"],
      ["Board", "shared", "yes"],
      ["Board", "name", ""],
      ["BoardOpened", "missing", -2],
      ["BoardOpened", "drawn", [1]],
      ["BoardOpened", "may_draw", "no"],
      ["Node", "datasets", [1]],
      ["Node", "type", ""],
      ["Edge", "basis", "certain"],
      ["Edge", "occurrences", "many"],
      ["Provenance", "state", "withdrawn"],
      ["Provenance", "first_seen", "not a time"],
      ["Provenance", "first_seen", "12"],
      ["Provenance", "sources", [7]],
      ["DrawnAssertion", "provenance_class", "analyst_guessed"],
      ["DrawnAssertion", "label", 7],
      ["DrawnAssertion", "label", ""],
      ["Grading", "source", null],
      ["Grading", "source", ""],
      ["Grading", "scheme", ""],
      ["Handling", "classification", 3],
      ["Handling", "review_date", "soon"],
    ];
    for (const [model, field, value] of wrong) {
      const b = withField(model, field, value);
      expect(quayView(b.opened), `${model}.${field} = ${JSON.stringify(value)}`).toBeUndefined();
      if (model === "Board") expect(listView(CASE, b.list), `list ${field} = ${JSON.stringify(value)}`).toBeUndefined();
    }
    const wrongLimit: [string, unknown][] = [["cap_kind", "items"], ["cap", -1], ["would_be", 2.5], ["options", ["filter"]], ["options", ["filter", "filter", "filter"]], ["error", "conflict"]];
    for (const [field, value] of wrongLimit) expect(limitView(withField("LimitExceeded", field, value).limit), `LimitExceeded.${field} = ${JSON.stringify(value)}`).toBeUndefined();
    for (const top of [null, {}, "x", [null], 3]) {
      expect(listView(CASE, top)).toBeUndefined();
      expect(quayView(top)).toBeUndefined();
      expect(limitView(top)).toBeUndefined();
    }
    // And through the service: one missing field of each model is the 502 page.
    for (const model of models) {
      const pages = (await drawn(withField(model, REQUIRED[model][0] as string, undefined))).pages;
      if (model === "LimitExceeded") expect(pages[2]?.status, model).toBe(502);
      else expect(pages[1]?.status, model).toBe(502);
      if (model === "Board") expect(pages[0]?.status).toBe(502);
    }
  });

  it("BD12: every field of the nine models is drawn, checked or named as left out; a drawn field changes a page, a checked one refuses the body, a left-out one changes nothing", { timeout: 120_000 }, async () => {
    expect(await censusProblems(CENSUS)).toEqual([]);
  });

  it("BD13: an empty board, and a board with an empty part, are said in words, never drawn as headings with no rows", async () => {
    const w = await world();
    const empty = await getAs(w, boardOfPath("b-empty"));
    expect(empty.status).toBe(200);
    expect(mainText(empty.text)).toContain("No items are shown on this board.");
    expect(mainOf(empty.text)).not.toMatch(/<table|<caption|<th\b/);
    expect(focusable(empty.text).map((s) => s.href ?? s.text)).toEqual(["#main", "Sign out", listOf(), "/"]);
    // The shared board: one drawn item, nothing loaded, no link.
    const shift = await getAs(w, boardOfPath("b-shift"));
    expect(boardProblems(shift.text, w, "b-shift")).toEqual([]);
    expect(mainText(shift.text)).toContain("No loaded items are shown on this board.");
    expect(mainText(shift.text)).toContain("No links are shown on this board.");
    expect(tablesOf(shift.text).map((t) => t.caption)).toEqual([BOARDS_WORDS.drawnCaption]);
    // Loaded items and nothing drawn.
    const onlyLoaded = await world({ boards: BOARDS.map((b) => (b.id === "b-quay" ? { ...b, drawn: [] } : b)) });
    const res = await getAs(onlyLoaded, boardOfPath("b-quay"));
    expect(mainText(res.text)).toContain("No drawn items are shown on this board.");
    expect(tablesOf(res.text).map((t) => t.caption)).toEqual([BOARDS_WORDS.loadedCaption, BOARDS_WORDS.linksCaption]);
    expect(structureProblems(res.text)).toEqual([]);
  });

  it("BD14: both pages are whole in structure, read-only, and their stops come in order", async () => {
    const w = await world();
    const list = await getAs(w, listOf());
    const one = await getAs(w, boardOfPath("b-quay"));
    expect(structureProblems(list.text)).toEqual([]);
    expect(structureProblems(one.text)).toEqual([]);
    const hrefs = (html: string): (string | undefined)[] => focusable(html).map((s) => s.href ?? s.text);
    expect(hrefs(list.text)).toEqual(["#main", "Sign out", ...ALEXS.map((id) => boardOfPath(id)), `/cases?case=${CASE}`, "/"]);
    expect(hrefs(one.text)).toEqual(["#main", "Sign out", listOf(), "/"]);
    expect(focusable(list.text).map((s) => s.text).slice(-2)).toEqual([BOARDS_WORDS.toCase, BOARDS_WORDS.back]);
    expect(focusable(one.text).map((s) => s.text).slice(2)).toEqual([BOARDS_WORDS.toBoards, BOARDS_WORDS.back]);
    expect(headings(mainOf(one.text)).map((h) => h.level)).toEqual([1, 2, 2, 2, 2]);
  });

  it("BD15: with scripts off both pages are whole: no script but the data block, no handler, no inline style", async () => {
    const w = await world();
    for (const path of [listOf(), boardOfPath("b-quay"), boardOfPath("b-empty"), boardOfPath("b-shift")]) {
      const res = await getAs(w, path);
      expect(scriptsOffProblems(res.text), path).toEqual([]);
      expect(res.text).toMatch(/<script type="application\/json" id="page-data"[^>]*>\{"page":"boards"\}<\/script>/);
    }
    const capped = await world({ cap: 1 });
    expect(scriptsOffProblems((await getAs(capped, boardOfPath("b-quay"))).text)).toEqual([]);
  });

  it("BD16: the GOV.UK tree serves the page and the Default tree does not; the lists name it; the case links to it; its words are British", async () => {
    const w = await world({ tree: "default" });
    const unknown = await getAs(w, NOWHERE);
    for (const path of [listOf(), boardOfPath("b-quay")]) {
      const res = await getAs(w, path);
      expect(res.status, path).toBe(404);
      expect(withoutNonce(res.text)).toBe(withoutNonce(unknown.text));
    }
    expect(calls(w.conduit)).toEqual([]);
    const page = PAGES.find((p) => p.path === PATH);
    expect(page?.id).toBe("drawing-boards");
    expect(page?.trees).toEqual(["govuk"]);
    expect(page?.methods).toEqual(["GET"]);
    expect(read(PAGES_DIR, "tree-govuk", "routes.yaml")).toMatch(/^ {2}- \/cases\/boards$/m);
    expect(boardsHref(CASE)).toBe(listOf());
    expect(boardHref(CASE, "b-quay")).toBe(boardOfPath("b-quay"));
    // The case's own page links to its boards (Scenario CS's page; its own test pins the stops).
    expect(read(PAGES_DIR, "tree-govuk", "cases.njk")).toContain("{{ view.boards }}");
    expect(CASES_WORDS.boards).toBe("Drawing boards in this case");
    const sources = sourcesOfThePage();
    for (const s of sources) expect([...withoutComments(s.text).matchAll(new RegExp(AMERICAN.source, "gi"))].map((m) => m[0]), s.name).toEqual([]);
    expect(choosingProblems(sources)).toEqual([]);
    // A moment's words are the shared package's: the page writes none of its own.
    expect(read(PAGES_DIR, "server", "views", "boardsWords.ts")).toContain("utcStampOf");
    expect(read(PAGES_DIR, "server", "views", "boardsWords.ts")).not.toMatch(/toISOString|toLocaleDateString|toLocaleTimeString|toLocaleString\("en-GB", \{|getUTC/);
    expect(read(PAGES_DIR, "scripts", "build.mjs")).toContain('join(root, "server", "views", "boardsWords.ts")');
  });

  describe("BD17: each check is red against the real page with one thing changed", () => {
    it("BD17: the list's check fails for the opened board's items counted, a board added, a row skipped or sorted, headings with no rows", async () => {
      const w = await world();
      const real = (await getAs(w, listOf())).text;
      expect(listProblems(real, w, ALEXS)).toEqual([]);
      const rowsOf = (html: string): string[] => [...(/<tbody>([\s\S]*?)<\/tbody>/.exec(html)?.[1] ?? "").matchAll(/<tr>[\s\S]*?<\/tr>/g)].map((m) => m[0]);
      const rows = rowsOf(real);
      expect(rows).toHaveLength(3);
      const withRows = (next: string[]): string => real.replace(rows.join("\n"), next.join("\n"));
      const plants: [string, string][] = [
        // The page counting the opened board's nodes (five: three drawn, two loaded) in place of the route's `drawn`.
        ["the opened board's nodes counted in place of drawn", real.replace(">3 drawn items<", ">5 drawn items<")],
        ["a board added from a second read", withRows([...rows, (rows[0] as string).replace("Quay sketch", "Blake&#39;s private board")])],
        ["a row skipped", withRows([rows[0] as string, rows[2] as string])],
        ["the rows sorted by name", withRows([rows[1] as string, rows[2] as string, rows[0] as string])],
        ["shared said in other words", real.replace(">Shared with the case<", ">Shared<")],
        ["headings with no rows", withRows([])],
      ];
      for (const [label, html] of plants) {
        expect(html, label).not.toBe(real);
        expect(listProblems(html, w, ALEXS).length + structureProblems(html).length, label).toBeGreaterThan(0);
      }
    });

    it("BD17: the board's check fails for a drawn item without its marking or grading, a link's end looked up elsewhere, a hidden item said", async () => {
      const w = await world();
      const real = (await getAs(w, boardOfPath("b-quay"))).text;
      expect(boardProblems(real, w, "b-quay")).toEqual([]);
      expect(boardProblems(real.replace(">A11 (5x5x5)<", "><"), w, "b-quay")).not.toEqual([]);
      expect(boardProblems(real.replace(/(Unknown male “Tall”[\s\S]*?<td>Person<\/td><td>)OFFICIAL/, "$1"), w, "b-quay")).not.toEqual([]);
      // A link's end looked up outside the route's items: the end said by an identifier, or as unknown.
      expect(boardProblems(real.replace(/(<td>KNOWS<\/td><td>Unknown male “Tall”<\/td><td>)Rowan Hale/, "$1n-owner"), w, "b-quay")).not.toEqual([]);
      expect(boardProblems(real.replace(/(<td>KNOWS<\/td><td>Unknown male “Tall”<\/td><td>)Rowan Hale/, "$1An item you cannot see"), w, "b-quay")).not.toEqual([]);
      // A link drawn twice.
      const linkRow = /<tr><th scope="row">Seen with<\/th>[\s\S]*?<\/tr>/.exec(real)?.[0] as string;
      expect(linkRow).toBeDefined();
      expect(boardProblems(real.replace(linkRow, `${linkRow}\n${linkRow}`), w, "b-quay")).not.toEqual([]);
      // A hidden item said, as a count, a row or a line.
      expect(hiddenProblems(real.replace("</main>", "<p>4 drawn items</p></main>"))).not.toEqual([]);
      expect(hiddenProblems(real.replace("</main>", "<p>Some items are withheld from you.</p></main>"))).not.toEqual([]);
      expect(neverProblems(real.replace("</main>", "<p>1 item is hidden from you</p></main>"))).not.toEqual([]);
      expect(neverProblems(real.replace("White van", "Hidden informant"))).not.toEqual([]);
      // A document said by its identifier, or by its kind.
      for (const said of ["doc-photo-7", "A document of the case"]) {
        const planted = real.replace(">B21 (5x5x5)<", `>${said}<`);
        expect(planted, said).not.toBe(real);
        expect(neverProblems(planted), said).not.toEqual([]);
      }
      // The fixture sending the hidden item's count as `missing`, which the real route never does: the page draws what it is sent.
      const b = openedBody();
      b["missing"] = 2;
      const w2 = await world({ board_answer: { status: 200, body: b } });
      expect(mainText((await getAs(w2, boardOfPath("b-quay"))).text)).toContain("2 items you placed have since been withdrawn.");
    });

    it("BD17: the no-source check fails for a note, a document's id or a source's words in a table, and for a table it cannot find", async () => {
      const w = await sourceWorld();
      const real = (await getAs(w, boardOfPath("b-sources"))).text;
      expect(sourceProblems(real)).toEqual([]);
      const inCell = (said: string): string => real.replace("<td>OFFICIAL</td>", `<td>${said}</td>`);
      for (const value of NOTES_AND_DOCUMENTS) expect(sourceProblems(inCell(value)), value).toContain(`the page holds ${JSON.stringify(value)}`);
      // Anywhere in the whole HTML, not only in a table: a title, an attribute.
      expect(sourceProblems(real.replace("<table", '<table data-from="doc-pilot-log"'))).toContain('the page holds "doc-pilot-log"');
      for (const said of ["No note given", "Source note", "A dataset this case reads"]) expect(sourceProblems(inCell(said)), said).not.toEqual([]);
      const header = real.replace('<th scope="col">Grading</th>', '<th scope="col">Grading</th><th scope="col">Source note</th>');
      expect(header).not.toBe(real);
      expect(sourceProblems(header)).toContain('the table "Drawn items on this board" says "Source"');
      expect(sourceProblems(real.replace(`>${BOARDS_WORDS.linksCaption}</caption>`, ">Links</caption>"))).not.toEqual([]);
    });

    it("BD17: the refusal's check fails for a 'not shared with you' sentence, the 404 passed through with the Conduit's words, another status", async () => {
      const w = await world();
      const unknown = await getAs(w, NOWHERE);
      const refused = await getAs(w, boardOfPath("b-blake"));
      expect(refusalProblems(refused, unknown)).toEqual([]);
      expect(refusalProblems({ status: 404, text: refused.text.replace("That page could not be found.", "This board is not shared with you.") }, unknown)).not.toEqual([]);
      expect(refusalProblems({ status: 403, text: refused.text }, unknown)).not.toEqual([]);
      expect(refusalProblems({ status: 404, text: refused.text.replace("</main>", "<p>board_not_found</p></main>") }, unknown)).not.toEqual([]);
      expect(neverProblems(refused.text.replace("</main>", "<p>This board is not shared with you</p></main>"))).not.toEqual([]);
    });

    it("BD17: the withdrawn sentence drawn for another reader, the cap's refusal drawn in part, a failed read drawn as an empty table", async () => {
      const w = await world();
      const shift = (await getAs(w, boardOfPath("b-shift"))).text;
      const planted = shift.replace("</main>", `<p>${BOARDS_WORDS.withdrawn(1)}</p></main>`);
      expect(mainText(planted)).toMatch(/withdrawn/);
      const capped = await world({ cap: 3 });
      const tooLarge = (await getAs(capped, boardOfPath("b-quay"))).text;
      expect(tooLargeProblems(tooLarge)).toEqual([]);
      const firstPart = tooLarge.replace("</main>", `<table><caption>${BOARDS_WORDS.drawnCaption}</caption><thead><tr><th scope="col">Item</th></tr></thead><tbody><tr><th scope="row">Unknown male “Tall”</th></tr></tbody></table></main>`);
      expect(tooLargeProblems(firstPart)).not.toEqual([]);
      expect(tooLargeProblems(tooLarge.replace(BOARDS_WORDS.optionWords.filter, ""))).not.toEqual([]);
      const failed = await world({ board_answer: { status: 500, body: {} } });
      const failedHtml = (await getAs(failed, boardOfPath("b-quay"))).text;
      expect(failedProblems(failedHtml)).toEqual([]);
      expect(failedProblems(failedHtml.replace('<p role="alert">', "<p>"))).not.toEqual([]);
      expect(failedProblems(failedHtml.replace("</main>", `<table><caption>${BOARDS_WORDS.drawnCaption}</caption></table></main>`))).not.toEqual([]);
      expect(callProblems([boardCall("b-quay"), boardCall("b-quay")], [boardCall("b-quay")])).not.toEqual([]);
      const emptyList = await world({ boards: [] });
      const emptyHtml = (await getAs(emptyList, listOf())).text;
      expect(emptyListProblems(emptyHtml)).toEqual([]);
      expect(emptyListProblems(emptyHtml.replace("No boards in this case yet.", `<table><caption>${BOARDS_WORDS.caption}</caption></table>`))).not.toEqual([]);
      // A reader that took a missing field as empty: the real view given a default for it draws, where the real one refuses.
      const lenient = (body: Json): unknown => quayView({ missing: 0, ...body });
      const removed = withField("BoardOpened", "missing", undefined);
      expect(quayView(removed.opened)).toBeUndefined();
      expect(lenient(removed.opened)).toBeDefined();
    });

    it("BD17: the census fails for a drawn field that changes nothing; the structure for a control or a link out of order; scripts off for a script", { timeout: 120_000 }, async () => {
      const w = await world();
      const real = (await getAs(w, boardOfPath("b-quay"))).text;
      expect(structureProblems(real.replace("</h1>", '</h1><form method="get" action="/cases/boards"><button>Draw</button></form>'))).not.toEqual([]);
      expect(structureProblems(real.replace(/<caption[^>]*>[^<]*<\/caption>/, ""))).not.toEqual([]);
      expect(structureProblems(real.replace('scope="row"', ""))).not.toEqual([]);
      expect(structureProblems(real.replace("</h1>", "</h1><h3>Skipped</h3>"))).not.toEqual([]);
      const hrefs = focusable(real.replace('<a class="skip-link" href="#main">Skip to main content</a>', "")).map((s) => s.href);
      expect(hrefs[0]).not.toBe("#main");
      expect(scriptsOffProblems(real.replace("</main>", '<script src="/x.js"></script></main>'))).not.toEqual([]);
      expect(scriptsOffProblems(real.replace("<table", '<table style="color: red"'))).not.toEqual([]);
      expect(scriptsOffProblems(real.replace("<a ", '<a onclick="x()" '))).not.toEqual([]);
      type List = "drawn" | "checked" | "left";
      const moved = (model: keyof typeof CENSUS, field: string, to: List): Census => {
        const lists: Record<List, string[]> = { drawn: [...CENSUS[model].drawn], checked: [...CENSUS[model].checked], left: [...CENSUS[model].left] };
        for (const list of Object.keys(lists) as List[]) lists[list] = lists[list].filter((f) => f !== field);
        lists[to].push(field);
        return { ...CENSUS, [model]: lists };
      };
      expect(await censusProblems(moved("DrawnAssertion", "asserted_by", "drawn"))).toEqual(["DrawnAssertion.asserted_by is drawn but changes no page that is still drawn"]);
      // Neither source field changes any page (until GG4b).
      expect(await censusProblems(moved("DrawnAssertion", "source_note", "drawn"))).toEqual(["DrawnAssertion.source_note is drawn but changes no page that is still drawn"]);
      expect(await censusProblems(moved("DrawnAssertion", "source_document", "drawn"))).toEqual(["DrawnAssertion.source_document is drawn but changes no page that is still drawn"]);
      expect(await censusProblems(moved("BoardOpened", "layout", "drawn"))).toEqual(["BoardOpened.layout is drawn but changes no page that is still drawn"]);
      expect(await censusProblems(moved("Grading", "handling", "left"))).toEqual(["Grading.handling is left out but changes the page"]);
      expect(await censusProblems(moved("Board", "drawn", "left"))).toEqual(["Board.drawn is left out but changes the page"]);
      // A field the page only checks, claimed as drawn (the review of 25 November: a refusal is not a drawing); a drawn one claimed as checked.
      expect(await censusProblems(moved("Edge", "id", "drawn"))).toEqual(["Edge.id is drawn but changes no page that is still drawn"]);
      expect(await censusProblems(moved("Board", "name", "checked"))).toEqual(["Board.name is checked but the page still draws from a body with it changed"]);
      expect(await censusProblems(moved("LimitExceeded", "would_be", "left"))).toEqual(["LimitExceeded.would_be is left out but changes the page"]);
    });

    it("BD17: the source checks fail for a filter, a sort or a cut in the page's code", () => {
      const sources = sourcesOfThePage();
      expect(choosingProblems(sources)).toEqual([]);
      const planted = (name: string, change: (text: string) => string): { name: string; text: string }[] => sources.map((s) => (s.name === name ? { ...s, text: change(s.text) } : s));
      expect(choosingProblems(planted("server/views/boardsWords.ts", (t) => `${t}\nconst x = [].sort();\n`))).not.toEqual([]);
      expect(choosingProblems(planted("server/views/boardsWords.ts", (t) => `${t}\nconst y = [1].slice(0, 1);\n`))).not.toEqual([]);
      expect(choosingProblems(planted("tree-govuk/boards.njk", (t) => t.replace("in view.rows %}", 'in view.rows | sort(attribute="name") %}')))).not.toEqual([]);
      expect(choosingProblems(planted("tree-govuk/boards.njk", (t) => t.replace("in view.links %}", 'in view.links | reject("odd") %}')))).not.toEqual([]);
    });

    it("BD17: the fixture Conduit refuses what the real routes refuse, in their order", async () => {
      const w = await world({ rights: [] });
      const ask = async (path: string, init: RequestInit = {}): Promise<{ status: number; body: unknown }> => {
        const res = await fetch(`${w.conduit.url}${path}`, init);
        return { status: res.status, body: await res.json() };
      };
      const as = { headers: { Authorization: `Bearer ${w.reader.token}` } };
      const base = `/v1/investigations/${CASE}/boards`;
      expect(await ask(base)).toEqual({ status: 401, body: { detail: "Not authenticated" } });
      expect(await ask(base, { headers: { Authorization: "Bearer someone-else" } })).toEqual({ status: 401, body: { detail: UNKNOWN_BEARER } });
      expect(await ask(`${base}?access_token=${w.reader.token}`)).toEqual({ status: 401, body: { detail: "Not authenticated" } });
      expect(await ask(`${base}/b-quay`, { method: "PATCH", ...as })).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
      expect(await ask(base, { method: "PUT" })).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
      // A route the real Conduit serves and the fixture does not model: never a 404 the real router would not give.
      expect((await ask(`${base}/b-quay/items`, as)).status).toBe(500);
      expect((await ask(`/v1/investigations/${CASE}/drawn-watches`, as)).status).toBe(500);
      expect(await ask("/v1/boards", as)).toEqual({ status: 404, body: { detail: "Not Found" } });
      // The right is checked before the case's gate and the board, as the route-level dependency runs first.
      expect(await ask(`/v1/investigations/c-no-such-case/boards`, as)).toEqual({ status: 403, body: rightRefusal("investigate") });
      expect(await ask(`${base}/b-no-such-board`, as)).toEqual({ status: 403, body: rightRefusal("investigate") });
      expect(await ask(base, { method: "POST", ...as })).toEqual({ status: 403, body: rightRefusal("draw_on_boards") });
      const w2 = await world();
      const as2 = { headers: { Authorization: `Bearer ${w2.reader.token}` } };
      const ask2 = async (path: string, init: RequestInit = {}): Promise<{ status: number; body: unknown }> => {
        const res = await fetch(`${w2.conduit.url}${path}`, init);
        return { status: res.status, body: await res.json() };
      };
      for (const caseId of ["c-unshared", "c-elsewhere", "c-no-such-case"]) {
        expect(await ask2(`/v1/investigations/${caseId}/boards`, as2), caseId).toEqual({ status: 404, body: NOT_FOUND_CASE });
        expect(await ask2(`/v1/investigations/${caseId}/boards/b-quay`, as2), caseId).toEqual({ status: 404, body: NOT_FOUND_CASE });
      }
      for (const id of ["b-blake", "b-elsewhere", "b-no-such-board"]) expect(await ask2(`${base}/${id}`, as2), id).toEqual({ status: 404, body: NOT_FOUND_BOARD });
      expect((await ask2(base, { method: "POST", ...as2 })).status).toBe(500); // a write that would pass: not modelled
      expect((await ask2(`${base}/b-quay`, { method: "DELETE", ...as2 })).status).toBe(500);
      const listed = (await ask2(base, as2)).body as { id: string }[];
      expect(listed.map((b) => b.id)).toEqual(ALEXS);
      // Blake's own private board is his to open, and not Alex's.
      const blake = await world({ as: BLAKE });
      expect((await fetch(`${blake.conduit.url}${base}/b-blake`, { headers: { Authorization: `Bearer ${blake.reader.token}` } })).status).toBe(200);
      // The opened board sends every field of `BoardOpened`, and nothing the reader may not see.
      const opened = (await ask2(`${base}/b-quay`, as2)).body as Record<string, unknown>;
      expect(Object.keys(opened).sort()).toEqual([...CENSUS.BoardOpened.drawn, ...CENSUS.BoardOpened.checked, ...CENSUS.BoardOpened.left].sort());
      expect(JSON.stringify(opened)).not.toMatch(/d-secret|l-high|l-secret/);
      expect("weight_components" in ((opened["edges"] as Json[])[0] as Json)).toBe(false);
      // Past the cap: the typed refusal, never a part of the board.
      const capped = await world({ cap: 1 });
      const refusal = await fetch(`${capped.conduit.url}${base}/b-quay`, { headers: { Authorization: `Bearer ${capped.reader.token}` } });
      expect(refusal.status).toBe(409);
      expect(((await refusal.json()) as { error: string }).error).toBe("limit_exceeded");
    });
  });
});
