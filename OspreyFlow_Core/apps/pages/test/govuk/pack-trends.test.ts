/**
 * Trends shown together: a pack's saved trends on one read-only page of the GOV.UK tree (slice GR4a; ADR-152 decisions 5, 6, 7, 10 and
 * 12, invariant I21; FUNCTIONS row `reports-figures`; scenario TS of `spec/08_ACCEPTANCE_SCENARIOS.md`, written first; the owner's
 * rulings of 25 November 2026). `tests/glass_trees/test_govuk_pack_trends_scenario.py` holds the scenario and this file in step: each
 * case's id is a row of the scenario.
 *
 * There is no React-first proof (the React workspace has no such page): the proof is the real service started for the GOV.UK tree, the
 * real page list and a fixture Conduit that answers and refuses as the real pack routes do (`packsConduit.ts`).
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a trend out of the pack's order, or without its title, period, counted-on day, marking, chart or table           -> TS1
 *  - a withheld item drawn as an empty chart, said with a count or a place, or not said at all (I21)                  -> TS2
 *  - a pack with no trend drawn as an empty chart, or a note, assessment, entity or alert drawn                         -> TS3
 *  - a reader without the right, or a pack with no publication, told anything but the unknown path's page              -> TS4
 *  - a pack in a case the reader cannot see, not in the case named, missing, or an address with no case or pack        -> TS5
 *  - no answer or a 5xx drawn as anything but "could not be read"; a 401 not said as an ended session                  -> TS6
 *  - a body missing a required field (each, from the generated type's own list) read as a zero or an empty chart       -> TS7
 *  - a field of the generated types neither drawn nor named as left out, or a left-out field drawn                    -> TS8
 *  - the working pack shown to a reader without its right, or the published version asked before the working pack      -> TS9
 *  - a call with the browser's headers, a query, a trend route (live figures), a write; an unsigned read              -> TS10
 *  - a form, a control, a skipped heading, a stop out of order                                                         -> TS11
 *  - a script, a handler, an inline style, a chart without a text alternative or its table                            -> TS12
 *  - an American spelling, the shared words written again, the session's words not the Studio's, the word "board"     -> TS13
 *  - the page in the Default tree, left out of the route list, the row without its ids or with a route                 -> TS14
 * Every planted fault is the real page (or the real file, or the real fixture) with one thing changed, run through the same function
 * that finds nothing in the real one (TS15, rule 15).
 */
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Express } from "express";
import { afterEach, describe, expect, it } from "vitest";
import { WITHHELD_ITEMS_SENTENCE, formatDay } from "@ospreyflow/glass-shared";
import type * as Real from "@ospreyflow/glass-shared";

import { createApp } from "../../server/app.js";
import { PAGES } from "../../server/pageList.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { readDraft, readPublished } from "../../server/views/packTrendsWords.js";
import type * as Stub from "../../server/types/glassShared.js";
import { refusalWords } from "../../server/views/studioWords.js";
import { testClock } from "../support/clock.js";
import { cookieFrom, csrfFromPage, request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { bearer, providerFor, textOf } from "../support/studioWorld.js";
import { READ_REPORTS, RECORD_ASSESSMENT, draftBody, figures, packItem, packsConduit, publishedBody, readableFor } from "./packsConduit.js";
import type { Canned, PacksConduit, Reader, StoredItem, StoredPack } from "./packsConduit.js";

// The compiled service is checked against `server/types/glassShared.d.ts`, not the package's source (`tsconfig.build.json`); this holds
// each declaration this page uses to the package's own type, so that a shape `packText.ts` changes and the stub still has as it was fails
// `npm run typecheck` (as `help.test.ts` does for the Help page's).
type Conforms<Real, Stub> = Real extends Stub ? true : never;
export const STUB_CONFORMS_TO_THE_PACKAGE: [
  Conforms<typeof Real.WITHHELD_ITEMS_SENTENCE, typeof Stub.WITHHELD_ITEMS_SENTENCE>,
  Conforms<typeof Real.formatDay, typeof Stub.formatDay>,
  Conforms<typeof Real.formatNumber, typeof Stub.formatNumber>,
  Conforms<typeof Real.periodKey, typeof Stub.periodKey>,
  Conforms<typeof Real.periodsOf, typeof Stub.periodsOf>,
  Conforms<typeof Real.trendSentence, typeof Stub.trendSentence>,
  Conforms<Stub.TrendFigures, Parameters<typeof Real.trendSentence>[0]>,
  // The other way, part by part (an `Omit` over these types keeps only their index signature, and would compare nothing): the stub is
  // no narrower than the package's type anywhere the page reads, so a widened field in the schema fails here too.
  Conforms<RealFigures["result"], Stub.TrendFigures["result"]>,
  Conforms<RealFigures["as_of"], Stub.TrendFigures["as_of"]>,
  Conforms<RealFigures["window_start"], Stub.TrendFigures["window_start"]>,
  Conforms<RealFigures["marking"], Stub.TrendFigures["marking"]>,
  Conforms<RealFigures["definition"]["title"], Stub.TrendFigures["definition"]["title"]>,
  Conforms<RealFigures["definition"]["source"], Stub.TrendFigures["definition"]["source"]>,
  Conforms<RealFigures["definition"]["measure"], Stub.TrendFigures["definition"]["measure"]>,
  Conforms<RealFigures["definition"]["measure_field"], Stub.TrendFigures["definition"]["measure_field"]>,
  Conforms<RealFigures["definition"]["interval"], Stub.TrendFigures["definition"]["interval"]>,
  Conforms<RealFigures["definition"]["weeks"], Stub.TrendFigures["definition"]["weeks"]>,
  Conforms<RealFigures["definition"]["group_by"], Stub.TrendFigures["definition"]["group_by"]>,
] = [true, true, true, true, true, true, true, true, true, true, true, true, true, true, true, true, true, true];
type RealFigures = Parameters<typeof Real.trendSentence>[0];

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CORE = join(PAGES_DIR, "..", "..");
const BUILD = join(CORE, "..", "OspreyFlow_Build");
const read = (...parts: string[]): string => readFileSync(join(...parts), "utf8");

const PATH = "/packs/trends";
const NOWHERE = "/nothing-is-served-here";
const CASE = "case-estuary";
const OTHER_CASE = "case-moorland";
const HIDDEN_CASE = "case-fenland";

// ------------------------------------------------------------------------------------------------ the world

const conduits: PacksConduit[] = [];
afterEach(async () => {
  while (conduits.length > 0) await conduits.pop()?.stop();
});

/** Three trends, stored in an order other than the one they were added in (added: ferry, toll, harbour; stored: harbour, ferry, toll). */
const HARBOUR = packItem({
  id: "item-harbour",
  kind: "trend",
  trend_id: "trend-harbour",
  added_at: "2026-11-02T12:00:00Z",
  trend: figures({ title: "Harbour meetings", points: [{ period_start: "2026-10-05T00:00:00Z", value: 3 }, { period_start: "2026-10-19T00:00:00Z", value: 5 }] }),
});
const FERRY = packItem({
  id: "item-ferry",
  kind: "trend",
  trend_id: "trend-ferry",
  added_at: "2026-11-02T10:00:00Z",
  marking: "OFFICIAL-SENSITIVE",
  trend: figures({
    title: "Ferry crossings",
    window_start: "2026-09-07T00:00:00Z",
    as_of: "2026-10-30T08:00:00Z",
    points: [{ period_start: "2026-09-14T00:00:00Z", value: 2 }],
  }),
});
const TOLL = packItem({
  id: "item-toll",
  kind: "trend",
  trend_id: "trend-toll",
  added_at: "2026-11-02T11:00:00Z",
  trend: figures({
    title: "Toll payments",
    definition: { measure: "sum", measure_field: "amount" },
    result: { measure: "sum", total: 1250, events: 4, unvalued: 1 },
    points: [{ period_start: "2026-10-12T00:00:00Z", value: 1250 }],
  }),
});
const NOTE = packItem({ id: "item-note", kind: "note", note: "A note that is not a trend." });

const STORED: StoredItem[] = [{ item: HARBOUR }, { item: FERRY }, { item: TOLL }];

function pack(over: Partial<StoredPack> = {}): StoredPack {
  return {
    id: "pack-estuary",
    case_id: CASE,
    title: "Estuary movements",
    created_by: "someone-synthetic",
    created_at: "2026-11-01T09:00:00Z",
    updated_at: "2026-11-02T12:00:00Z",
    items: STORED,
    ...over,
  };
}

interface World {
  app: Express;
  conduit: PacksConduit;
  token: string;
  cookie: string;
  csrf: string;
}

interface WorldOptions {
  /** The rights the signed-in person holds at the Conduit: the right to record assessments by default. */
  rights?: string[];
  /** The cases the person holds a level in: the pack's case, as a Viewer, by default. */
  cases?: Reader["cases"];
  packs?: StoredPack[];
  /** Hide the items with these ids from the signed-in person. */
  hide?: string[];
  draft_answer?: Canned;
  published_answer?: Canned;
  no_answer?: boolean;
  tree?: "govuk" | "default";
  conduitUrl?: string;
  unknownBearer?: boolean;
}

async function world(options: WorldOptions = {}): Promise<World> {
  const token = bearer();
  const hidden = (items: StoredItem[]): StoredItem[] =>
    items.map((s) => ((options.hide ?? []).includes(String(s.item["id"])) ? { ...s, hiddenFrom: [...(s.hiddenFrom ?? []), token] } : s));
  const packs = (options.packs ?? [pack()]).map((p) => ({
    ...p,
    items: hidden(p.items),
    ...(p.published ? { published: { ...p.published, items: hidden(p.published.items) } } : {}),
  }));
  const conduit = await packsConduit({
    readers: options.unknownBearer === true ? [] : [{ token, rights: options.rights ?? [RECORD_ASSESSMENT], cases: options.cases ?? { [CASE]: "viewer", [OTHER_CASE]: "viewer" } }],
    cases: [CASE, OTHER_CASE, HIDDEN_CASE],
    packs,
    ...(options.draft_answer ? { draft_answer: options.draft_answer } : {}),
    ...(options.published_answer ? { published_answer: options.published_answer } : {}),
    ...(options.no_answer ? { no_answer: true } : {}),
  });
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
  return { app, conduit, token, cookie, csrf: csrfFromPage(home.text) };
}

const getAs = (w: World, path: string) => request(w.app).get(path).set("Cookie", w.cookie);
const address = (caseId = CASE, packId = "pack-estuary"): string => `${PATH}?case=${encodeURIComponent(caseId)}&pack=${encodeURIComponent(packId)}`;
const trendsPage = (w: World, caseId?: string, packId?: string) => getAs(w, address(caseId, packId));
const calls = (c: PacksConduit): string[] => c.calls.map((call) => `${call.method} ${call.url}`);
const DRAFT_CALL = `GET /v1/investigations/${CASE}/packs/pack-estuary`;
const PUBLISHED_CALL = `GET /v1/investigations/${CASE}/packs/pack-estuary/published`;

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
/** The page with what changes on every request taken out: the script nonce and the anti-forgery token. */
const steady = (html: string): string => html.replace(/nonce="[^"]*"/g, 'nonce="N"').replace(/(name="csrf-token" content=|name="_csrf" value=)"[^"]*"/g, '$1"T"');

function mainOf(html: string): string {
  const found = /<main\b[^>]*>([\s\S]*?)<\/main>/.exec(strip(html));
  return found ? (found[1] as string) : "";
}

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
    stops.push({ tag, href: attr(attrs, "href"), text: textOf(m[3] ?? "") });
  }
  return stops;
}

const headings = (html: string): { level: number; text: string }[] =>
  [...strip(html).matchAll(/<h([1-6])\b([^>]*)>([\s\S]*?)<\/h\1>/g)].map((m) => ({ level: Number(m[1]), text: textOf(m[3] as string) }));

interface DrawnTable {
  caption: string;
  columns: string[];
  rows: { head: string; cells: string[] }[];
}

function tableIn(block: string): DrawnTable | undefined {
  const found = /<table\b[^>]*>([\s\S]*?)<\/table>/.exec(block);
  if (!found) return undefined;
  const inner = found[1] as string;
  const caption = textOf(/<caption\b[^>]*>([\s\S]*?)<\/caption>/.exec(inner)?.[1] ?? "");
  const head = /<thead\b[^>]*>([\s\S]*?)<\/thead>/.exec(inner)?.[1] ?? "";
  const columns = [...head.matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/g)].map((m) => textOf(m[1] as string));
  const body = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/.exec(inner)?.[1] ?? "";
  const rows = [...body.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((row) => {
    const cells = [...(row[1] as string).matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/g)].map((c) => textOf(c[1] as string));
    return { head: cells[0] ?? "", cells: cells.slice(1) };
  });
  return { caption, columns, rows };
}

interface DrawnChart {
  classes: string;
  label: string;
  bars: { cls: string; height: number }[];
  /** Whether the chart comes before its table in the trend's block. */
  beforeTable: boolean;
}

function chartIn(block: string): DrawnChart | undefined {
  const found = /<svg\b([^>]*)>([\s\S]*?)<\/svg>/.exec(block);
  if (!found) return undefined;
  const attrs = found[1] as string;
  const inner = found[2] as string;
  const labelId = attr(attrs, "aria-labelledby");
  const label = labelId ? textOf(new RegExp(`<title\\b[^>]*id="${labelId}"[^>]*>([\\s\\S]*?)</title>`).exec(inner)?.[1] ?? "") : "";
  const bars = [...inner.matchAll(/<rect\b([^>]*)>/g)].map((r) => ({ cls: attr(r[1] as string, "class") ?? "", height: Number(attr(r[1] as string, "height")) }));
  const tableAt = block.search(/<table\b/);
  return { classes: attr(attrs, "class") ?? "", label, bars, beforeTable: tableAt === -1 || block.search(/<svg\b/) < tableAt };
}

interface DrawnTrend {
  title: string;
  lines: string[];
  chart: DrawnChart | undefined;
  table: DrawnTable | undefined;
}

/** Each trend the page draws, in the page's order: its heading, its lines of words, its chart and its table. */
function trendsOf(html: string): DrawnTrend[] {
  return [...mainOf(html).matchAll(/<section\b[^>]*class="pack-trend"[^>]*>([\s\S]*?)<\/section>/g)].map((m) => {
    const block = m[1] as string;
    return {
      title: textOf(/<h2\b[^>]*>([\s\S]*?)<\/h2>/.exec(block)?.[1] ?? ""),
      lines: [...block.matchAll(/<p\b[^>]*>([\s\S]*?)<\/p>/g)].map((p) => textOf(p[1] as string)),
      chart: chartIn(block),
      table: tableIn(block),
    };
  });
}

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
  if (!first || first.href !== `#${mainId}` || !/skip to main content/i.test(first.text)) found.push(`the first stop is not the skip link to the main landmark`);
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
    for (const row of body ? (body[1] as string).matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g) : []) {
      const firstCell = /<(th|td)\b([^>]*)>/.exec(row[1] as string);
      if (!firstCell || firstCell[1] !== "th" || attr(firstCell[2] as string, "scope") !== "row") found.push('a table row does not start with a th scope="row"');
    }
  }
  const forms = [...page.matchAll(/<form\b([^>]*)>/g)].map((f) => `${attr(f[1] as string, "method") ?? ""} ${attr(f[1] as string, "action") ?? ""}`);
  if (forms.some((f) => f !== "post /session/sign-out")) found.push(`a form that is not the sign-out: ${forms.join("; ")}`);
  if (/<(form|button|input|select|textarea)\b/.test(mainOf(page))) found.push("the main landmark holds a control or a form");
  return found;
}

/** Every thing that needs a script, an inline rule or a tab stop out of order, and every chart that is not plain SVG with classes and a
 * text alternative followed by its table (TS12). */
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
  if (/\s(?:fill|stroke|color)\s*=/i.test(page)) found.push("a colour written on an element, not by a class");
  for (const t of page.matchAll(/\stabindex="(-?\d+)"/g)) if (Number(t[1]) > 0) found.push(`a tab stop of ${t[1] as string}`);
  for (const trend of trendsOf(page)) {
    if (!trend.chart) {
      found.push(`the trend ${JSON.stringify(trend.title)} has no chart`);
      continue;
    }
    if (trend.chart.classes === "" || trend.chart.bars.some((b) => b.cls === "")) found.push(`the chart of ${JSON.stringify(trend.title)} is not drawn by classes`);
    if (trend.chart.label === "") found.push(`the chart of ${JSON.stringify(trend.title)} has no text alternative`);
    if (!trend.table || !trend.chart.beforeTable) found.push(`the chart of ${JSON.stringify(trend.title)} is not followed by its table`);
  }
  return found;
}

/** The chart and its table say the same figures: a bar for each row, each bar's height in proportion to the row's last cell. */
function sameFiguresProblems(trend: DrawnTrend): string[] {
  const found: string[] = [];
  if (!trend.chart || !trend.table) return [`${trend.title}: no chart or no table`];
  const totals = trend.table.rows.map((r) => Number((r.cells[r.cells.length - 1] ?? "").replace(/,/g, "")));
  if (trend.chart.bars.length !== totals.length) found.push(`${trend.title}: ${trend.chart.bars.length} bars for ${totals.length} rows`);
  const most = Math.max(0, ...totals);
  const tallest = Math.max(0, ...trend.chart.bars.map((b) => b.height));
  trend.chart.bars.forEach((bar, i) => {
    const want = most === 0 ? 0 : ((totals[i] ?? 0) / most) * tallest;
    if (Math.abs(bar.height - want) > 0.05) found.push(`${trend.title}: bar ${i} is ${bar.height} high for a figure of ${String(totals[i])}`);
  });
  return found;
}

const refusalProblems = (refused: { status: number; text: string }, unknown: { status: number; text: string }): string[] =>
  refused.status === unknown.status && withoutNonce(refused.text) === withoutNonce(unknown.text) ? [] : ["the refusal is not the page of a path nothing serves"];

const UNREADABLE = "The trends could not be read just now";

/** What the page must never show: the Conduit's words, a right's name, an identifier, an item that is not a trend. */
const NEVER = ["right_required", RECORD_ASSESSMENT, READ_REPORTS, "investigation_not_found", "no such pack in this case", "this pack has no publication", "item-harbour", "trend-harbour", "pack-estuary", CASE, "someone-synthetic", "A note that is not a trend."];
const leakProblems = (html: string): string[] => NEVER.filter((said) => textOf(mainOf(html)).includes(said) || strip(mainOf(html)).includes(said)).map((said) => `the page shows ${JSON.stringify(said)}`);

// ------------------------------------------------------------------------------------------------ the sources

const SOURCES = ["server/packTrends.ts", "server/views/packTrendsWords.ts", "tree-govuk/pack-trends.njk"];
const sourcesOfThePage = (): { name: string; text: string }[] => SOURCES.map((name) => ({ name, text: read(PAGES_DIR, name) }));
const withoutComments = (text: string): string => text.replace(/\/\*[\s\S]*?\*\/|\/\/.*$|\{#[\s\S]*?#\}/gm, "");
const AMERICAN = /\b(?:color|colors|organization|organizations|center|centers|authorize|authorized|behavior|license|licenses|analyze|favorite|catalog)\b/i;
const americanSpellings = (text: string): string[] => [...text.matchAll(new RegExp(AMERICAN.source, "gi"))].map((m) => m[0]);
const boardProblems = (texts: { name: string; text: string }[]): string[] => texts.filter((s) => /board/i.test(withoutComments(s.text))).map((s) => `${s.name} says "board"`);

/** The shared words the page must import and never write again (`packText.ts`). */
const SHARED_WORDS = [WITHHELD_ITEMS_SENTENCE, "had no ", "not in the sum", "Some items of this pack"];
const copiesOfSharedWords = (texts: { name: string; text: string }[]): string[] =>
  texts.flatMap((s) => SHARED_WORDS.filter((w) => withoutComments(s.text).includes(w)).map((w) => `${s.name} writes again ${JSON.stringify(w)}`));

// ------------------------------------------------------------------------------------------------ the generated types (TS7, TS8)

/** Every field of an interface of a generated file, and whether the type marks it required (no `?`). */
function fieldsOf(file: string, name: string): { field: string; required: boolean }[] {
  const text = read(CORE, "packages", "schemas", "generated", file);
  const found = new RegExp(`export interface ${name} \\{\\n([\\s\\S]*?)\\n\\}`).exec(text);
  if (!found) throw new Error(`${file} has no interface ${name}`);
  return [...(found[1] as string).matchAll(/^  ([a-z_]+)(\??): /gm)].map((m) => ({ field: m[1] as string, required: m[2] !== "?" }));
}

/** Where each interface the page reads sits in a body, and which body: the cases are made from these and the generated lists. */
type Body = Record<string, unknown>;
type Locate = (body: Body) => Body;
const at = (body: Body, ...path: (string | number)[]): Body => path.reduce<unknown>((o, k) => (o as Record<string | number, unknown>)[k], body) as Body;
const TYPES: { name: string; file: string; body: "draft" | "published"; locate: Locate }[] = [
  { name: "PackDraft", file: "PackDraft.ts", body: "draft", locate: (b) => b },
  { name: "ReportPack", file: "PackDraft.ts", body: "draft", locate: (b) => at(b, "pack") },
  { name: "PublishedPack", file: "PublishedPack.ts", body: "published", locate: (b) => b },
  { name: "PackItem", file: "PackDraft.ts", body: "draft", locate: (b) => at(b, "items", 0) },
  { name: "TrendFigures", file: "PackDraft.ts", body: "draft", locate: (b) => at(b, "items", 0, "trend") },
  { name: "TrendDefinitionInput", file: "PackDraft.ts", body: "draft", locate: (b) => at(b, "items", 0, "trend", "definition") },
  { name: "TrendResult", file: "PackDraft.ts", body: "draft", locate: (b) => at(b, "items", 0, "trend", "result") },
  { name: "TrendPoint", file: "PackDraft.ts", body: "draft", locate: (b) => at(b, "items", 0, "trend", "result", "points", 0) },
];

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const PUBLISHED_PACK = pack({ published: { version: 2, published_at: "2026-11-03T15:00:00Z", published_by: "someone-synthetic", published_by_name: "Sam Synthetic", items: STORED } });
const baseBody = (which: "draft" | "published"): Body => (which === "draft" ? draftBody(pack(), "t") : publishedBody(PUBLISHED_PACK, "t"));

/** How a body is drawn, for the strict reader and the census: through the real page, or through a view alone (a planted one). */
type Render = (which: "draft" | "published", body: Body) => Promise<{ status: number; text: string }>;

const throughThePage: Render = async (which, body) => {
  const w = which === "draft" ? await world({ draft_answer: { status: 200, body } }) : await world({ rights: [READ_REPORTS], packs: [PUBLISHED_PACK], published_answer: { status: 200, body } });
  const res = await trendsPage(w);
  return { status: res.status, text: steady(res.text) };
};

const throughAView =
  (draft: (body: unknown) => unknown, published: (body: unknown) => unknown): Render =>
  async (which, body) => {
    const view = (which === "draft" ? draft : published)(body);
    return view === undefined ? { status: 502, text: UNREADABLE } : { status: 200, text: JSON.stringify(view) };
  };

/** Each required field of each interface, left out of a body that is otherwise whole: the page must say it could not read it (TS7). */
async function strictProblems(render: Render): Promise<string[]> {
  const found: string[] = [];
  for (const type of TYPES) {
    for (const { field, required } of fieldsOf(type.file, type.name)) {
      if (!required) continue;
      const body = clone(baseBody(type.body));
      delete type.locate(body)[field];
      const res = await render(type.body, body);
      if (res.status !== 502 || !res.text.includes(UNREADABLE)) found.push(`${type.name}.${field} left out was drawn (${res.status})`);
    }
  }
  return found;
}

/** The left-out fields, by name, from scenario TS's own sentence. */
function leftOut(): Set<string> {
  const spec = read(BUILD, "spec", "08_ACCEPTANCE_SCENARIOS.md");
  const section = spec.slice(spec.indexOf("## Scenario TS"), spec.indexOf("\n## ", spec.indexOf("## Scenario TS") + 1));
  const sentence = /\*\*Left out, by field name\*\*([^\n]*)/.exec(section)?.[1] ?? "";
  return new Set([...sentence.matchAll(/`([A-Za-z]+\.[a-z_]+)`/g)].map((m) => m[1] as string));
}

/** For each drawn field, a change a reader would see; `setup` puts both bodies where the field shows (a sum, a series). */
interface Change {
  setup?: (b: Body) => void;
  change: (b: Body) => void;
}
const trendOf = (b: Body): Body => at(b, "items", 0, "trend");
const asSum = (b: Body): void => {
  at(trendOf(b), "definition")["measure"] = "sum";
  at(trendOf(b), "definition")["measure_field"] = "amount";
  at(trendOf(b), "result")["measure"] = "sum";
};
const withSeries = (b: Body): void => {
  const result = at(trendOf(b), "result");
  result["series"] = ["north", "south"];
  result["points"] = [
    { period_start: "2026-10-05T00:00:00Z", series: "north", value: 1 },
    { period_start: "2026-10-05T00:00:00Z", series: "south", value: 2 },
  ];
};
const DRAWN: Record<string, Change> = {
  "PackDraft.pack": { change: (b) => void (at(b, "pack")["title"] = "Another pack") },
  "PackDraft.items": { change: (b) => void (b["items"] as unknown[]).reverse() },
  "PackDraft.withheld": { change: (b) => void (b["withheld"] = true) },
  "PackDraft.marking": { change: (b) => void (b["marking"] = "SECRET") },
  "ReportPack.title": { change: (b) => void (at(b, "pack")["title"] = "Another pack") },
  "PublishedPack.title": { change: (b) => void (b["title"] = "Another pack") },
  "PublishedPack.version": { change: (b) => void (b["version"] = 3) },
  "PublishedPack.published_at": { change: (b) => void (b["published_at"] = "2026-11-09T15:00:00Z") },
  "PublishedPack.items": { change: (b) => void (b["items"] as unknown[]).reverse() },
  "PublishedPack.withheld": { change: (b) => void (b["withheld"] = true) },
  "PublishedPack.marking": { change: (b) => void (b["marking"] = "SECRET") },
  "PackItem.kind": { change: (b) => void (at(b, "items", 0)["kind"] = "note") },
  "PackItem.marking": { change: (b) => void (at(b, "items", 0)["marking"] = "SECRET") },
  "PackItem.trend": { change: (b) => void (at(b, "items", 0)["trend"] = figures({ title: "Another trend", points: [] })) },
  "TrendFigures.definition": { change: (b) => void (at(trendOf(b), "definition")["title"] = "Another trend") },
  "TrendFigures.result": { change: (b) => void (at(trendOf(b), "result")["events"] = 99) },
  "TrendFigures.as_of": { change: (b) => void (trendOf(b)["as_of"] = "2026-11-09T09:00:00Z") },
  "TrendFigures.window_start": { change: (b) => void (trendOf(b)["window_start"] = "2026-09-28T00:00:00Z") },
  "TrendDefinitionInput.title": { change: (b) => void (at(trendOf(b), "definition")["title"] = "Another trend") },
  "TrendDefinitionInput.source": { change: (b) => void (at(trendOf(b), "definition")["source"] = "alerts") },
  "TrendDefinitionInput.measure_field": { setup: asSum, change: (b) => void (at(trendOf(b), "definition")["measure_field"] = "weight") },
  "TrendDefinitionInput.weeks": { change: (b) => void (at(trendOf(b), "definition")["weeks"] = 8) },
  "TrendResult.interval": { change: (b) => void (at(trendOf(b), "result")["interval"] = "month") },
  "TrendResult.measure": { change: (b) => void (at(trendOf(b), "result")["measure"] = "sum") },
  "TrendResult.points": { change: (b) => void (at(trendOf(b), "result")["points"] = []) },
  "TrendResult.series": { setup: withSeries, change: (b) => void (at(trendOf(b), "result")["series"] = ["south", "north"]) },
  "TrendResult.total": { setup: asSum, change: (b) => void (at(trendOf(b), "result")["total"] = 4321) },
  "TrendResult.events": { change: (b) => void (at(trendOf(b), "result")["events"] = 42) },
  "TrendResult.unvalued": { setup: asSum, change: (b) => void (at(trendOf(b), "result")["unvalued"] = 6) },
  "TrendPoint.period_start": { change: (b) => void (at(trendOf(b), "result", "points", 0)["period_start"] = "2026-10-12T00:00:00Z") },
  "TrendPoint.series": { setup: withSeries, change: (b) => void (at(trendOf(b), "result", "points", 0)["series"] = "east") },
  "TrendPoint.value": { change: (b) => void (at(trendOf(b), "result", "points", 0)["value"] = 17) },
};

/** A change to a left-out field: another value of the same kind, or a value where there was none. */
function otherValue(value: unknown): unknown {
  if (typeof value === "string") return `${value}-changed`;
  if (typeof value === "number") return value + 1;
  if (typeof value === "boolean") return !value;
  if (Array.isArray(value)) return value.length > 0 ? [] : ["changed"];
  if (value === null || value === undefined) return "changed";
  return {};
}

/** Every field of every interface is drawn (its change shows) or named as left out (its change does not): the census (TS8). */
async function censusProblems(render: Render, named: Set<string> = leftOut()): Promise<string[]> {
  const found: string[] = [];
  for (const type of TYPES) {
    for (const { field } of fieldsOf(type.file, type.name)) {
      const key = `${type.name}.${field}`;
      const drawn = DRAWN[key];
      if (named.has(key) && drawn) {
        found.push(`${key} is both drawn and named as left out`);
        continue;
      }
      if (!named.has(key) && !drawn) {
        found.push(`${key} is neither drawn nor named as left out`);
        continue;
      }
      const before = clone(baseBody(type.body));
      drawn?.setup?.(before);
      const after = clone(before);
      if (drawn) drawn.change(after);
      else type.locate(after)[field] = otherValue(type.locate(after)[field]);
      const [a, b] = [await render(type.body, before), await render(type.body, after)];
      if (a.status !== 200) found.push(`${key}: the body before the change was not drawn (${a.status})`);
      if (drawn && a.text === b.text) found.push(`${key} is not drawn: changing it does not change the page`);
      if (!drawn && b.status === 200 && a.text !== b.text) found.push(`${key} is named as left out, but changing it changes the page`);
    }
  }
  return found;
}

// ------------------------------------------------------------------------------------------------ the page

describe("trends shown together (the govuk tree)", () => {
  it("TS1: shows the pack's trends in the pack's stored order, each with its title, period, counted-on day, marking, figures, a chart and the same figures' table", async () => {
    const w = await world();
    const res = await trendsPage(w);
    expect(res.status).toBe(200);
    const drawn = trendsOf(res.text);
    // The stored order, not the order they were added in (ferry, toll, harbour) nor any sort of the titles.
    expect(drawn.map((t) => t.title)).toEqual(["Harbour meetings", "Ferry crossings", "Toll payments"]);
    const harbour = drawn[0] as DrawnTrend;
    expect(harbour.lines).toEqual(["From 5 October 2026 to 1 November 2026", `Counted on ${formatDay("2026-11-01T09:00:00Z")}`, "Marking: OFFICIAL", "8 events in 4 weeks"]);
    expect(drawn[1]?.lines).toContain("Marking: OFFICIAL-SENSITIVE");
    expect(drawn[1]?.lines).toContain("From 7 September 2026 to 30 October 2026");
    expect(drawn[2]?.lines).toContain("Sum of amount: 1,250 over 4 events in 4 weeks; 1 event had no amount and is not in the sum");
    // Every week of the window is a row and a bar, the empty ones too.
    expect(harbour.table?.columns).toEqual(["Week starting", "Count"]);
    expect(harbour.table?.rows).toEqual([
      { head: "5 October 2026", cells: ["3"] },
      { head: "12 October 2026", cells: ["0"] },
      { head: "19 October 2026", cells: ["5"] },
      { head: "26 October 2026", cells: ["0"] },
    ]);
    expect(harbour.table?.caption).toBe("The figures of Harbour meetings");
    expect(drawn[2]?.table?.columns).toEqual(["Week starting", "Sum of amount"]);
    for (const trend of drawn) expect(sameFiguresProblems(trend), trend.title).toEqual([]);
    expect(harbour.chart?.label).toBe("Harbour meetings: one bar for each of 4 weeks, from 5 October 2026 to 26 October 2026; the tallest bar is 5.");
    // A trend counted by series: a column for each series, in the result's order, and the total the bar draws.
    const series = clone(HARBOUR);
    const result = at(series, "trend", "result");
    result["series"] = ["north", "south"];
    result["points"] = [
      { period_start: "2026-10-05T00:00:00Z", series: "north", value: 1 },
      { period_start: "2026-10-05T00:00:00Z", series: "south", value: 2 },
      { period_start: "2026-10-19T00:00:00Z", series: "south", value: 4 },
    ];
    const s = await world({ packs: [pack({ items: [{ item: series }] })] });
    const byseries = trendsOf((await trendsPage(s)).text)[0] as DrawnTrend;
    expect(byseries.table?.columns).toEqual(["Week starting", "north", "south", "Total"]);
    expect(byseries.table?.rows[0]).toEqual({ head: "5 October 2026", cells: ["1", "2", "3"] });
    expect(byseries.table?.rows[2]).toEqual({ head: "19 October 2026", cells: ["0", "4", "4"] });
    expect(sameFiguresProblems(byseries)).toEqual([]);
    // The working pack is said as such, and its highest marking.
    const top = textOf(mainOf(res.text));
    expect(top).toContain("Pack: Estuary movements");
    expect(top).toContain("The working pack, as it stands now.");
    expect(top).toContain("Highest marking shown: OFFICIAL-SENSITIVE");
  });

  it("TS2: a middle item the reader can no longer read is said once as withheld, with no figure, title, count or place, and never as an empty chart (I21)", async () => {
    const w = await world({ hide: ["item-ferry"] });
    const res = await trendsPage(w);
    expect(res.status).toBe(200);
    const drawn = trendsOf(res.text);
    expect(drawn.map((t) => t.title)).toEqual(["Harbour meetings", "Toll payments"]);
    const text = textOf(mainOf(res.text));
    expect(text.split(WITHHELD_ITEMS_SENTENCE).length - 1).toBe(1);
    expect(text).not.toContain("Ferry crossings");
    expect(text).not.toContain("OFFICIAL-SENSITIVE");
    expect(text).not.toMatch(/\b(?:one|two|1|2) items?\b.*not shown|withheld item \d|second|middle/i);
    // No chart or table that stands for the withheld one: one of each for each trend drawn.
    expect([...mainOf(res.text).matchAll(/<svg\b/g)].length).toBe(2);
    expect([...mainOf(res.text).matchAll(/<table\b/g)].length).toBe(2);
    // The sentence comes before the trends, not in a place among them.
    expect(mainOf(res.text).indexOf(WITHHELD_ITEMS_SENTENCE)).toBeLessThan(mainOf(res.text).indexOf('class="pack-trend"'));
    // Nothing withheld: no sentence.
    expect(textOf(mainOf((await trendsPage(await world())).text))).not.toContain(WITHHELD_ITEMS_SENTENCE);
    // Every trend withheld: the sentence, and no chart.
    const all = await trendsPage(await world({ hide: ["item-harbour", "item-ferry", "item-toll"] }));
    expect(textOf(mainOf(all.text))).toContain(WITHHELD_ITEMS_SENTENCE);
    expect(textOf(mainOf(all.text))).toContain("This pack has no trends to show you.");
    expect(mainOf(all.text)).not.toMatch(/<svg\b|<table\b/);
  });

  it("test_trends_shown_together_show_a_trend_its_viewer_can_no_longer_read_as_withheld_not_as_missing_data", async () => {
    // I21 (ADR-152), by the name the decision log gives it. The page says the trends it holds back are withheld, once, in the shared words,
    // above the trends; and never draws an empty chart (an svg with no bar), an empty table or a placeholder in a withheld item's place.
    const withheldPageProblems = (html: string, trendsShown: number): string[] => {
      const main = mainOf(html);
      const found: string[] = [];
      const said = textOf(main).split(WITHHELD_ITEMS_SENTENCE).length - 1;
      if (said !== 1) found.push(`the withheld sentence is said ${said} times, not once`);
      const charts = [...main.matchAll(/<svg\b[\s\S]*?<\/svg>/g)].map((m) => m[0]);
      if (charts.length !== trendsShown) found.push(`${charts.length} charts for ${trendsShown} trends shown`);
      if (charts.some((c) => !/<rect\b/.test(c))) found.push("a chart with no bar: an empty chart");
      const tables = [...main.matchAll(/<table\b[\s\S]*?<\/table>/g)].map((m) => m[0]);
      if (tables.length !== trendsShown) found.push(`${tables.length} tables for ${trendsShown} trends shown`);
      if (tables.some((t) => !/<td\b/.test(t))) found.push("a table with no figure: an empty table");
      if (main.indexOf(WITHHELD_ITEMS_SENTENCE) > main.indexOf('class="pack-trend"')) found.push("the withheld sentence is not above the trends");
      if (/Ferry crossings/.test(main)) found.push("the withheld trend's title is drawn");
      return found;
    };
    const w = await world({ hide: ["item-ferry"] });
    const page = (await trendsPage(w)).text;
    expect(withheldPageProblems(page, 2)).toEqual([]);
    // The same, for a published version: its withheld item is said the same way.
    const version = await trendsPage(await world({ packs: [pack({ items: [], published: { version: 1, published_at: "2026-11-03T15:00:00Z", published_by: "someone-synthetic", items: [{ item: HARBOUR }, { item: FERRY }, { item: TOLL }] } })], rights: [READ_REPORTS], hide: ["item-ferry"] }));
    expect(version.status).toBe(200);
    expect(withheldPageProblems(version.text, 2)).toEqual([]);
    // Planted into the real page: a page that drops the sentence, one that draws an empty chart in the withheld one's place, one that stands a
    // placeholder or a second sentence among the trends, and one that draws the withheld trend's figures.
    const plant = (pattern: RegExp, by: string): string => {
      expect(pattern.test(page), `the plant's anchor ${String(pattern)} is in the page`).toBe(true);
      return page.replace(pattern, by);
    };
    const sentence = /<p class="pack-trends__withheld">[^<]*<\/p>/;
    expect(withheldPageProblems(plant(sentence, ""), 2)).toContain("the withheld sentence is said 0 times, not once");
    expect(withheldPageProblems(plant(/<section class="pack-trend"/, '<svg class="pack-trend__chart"></svg><section class="pack-trend"'), 2).join()).toContain("an empty chart");
    expect(withheldPageProblems(plant(/<section class="pack-trend"/, `<p>${WITHHELD_ITEMS_SENTENCE}</p><section class="pack-trend"`), 2).join()).toContain("said 2 times");
    expect(withheldPageProblems(plant(/<section class="pack-trend"/, '<table><caption>x</caption></table><section class="pack-trend"'), 2).join()).toContain("an empty table");
    expect(withheldPageProblems(plant(sentence, "").replace("</main>", `<p>${WITHHELD_ITEMS_SENTENCE}</p></main>`), 2).join()).toContain("not above the trends");
  });

  it("TS3: a pack with no trend item says so, links back, and draws no chart, no table and nothing of its other items", async () => {
    const others = [
      { item: NOTE },
      { item: packItem({ id: "item-assessment", kind: "assessment", assessment: { judgement_id: "j-a", statement: "An assessment that is not a trend.", probability_band: "likely", supporting: [], contradicting: [], author: "someone-synthetic", created_at: "2026-11-01T09:00:00Z" } }) },
      { item: packItem({ id: "item-entity", kind: "entity", entity: { node_id: "n-a", entity_type: "Person", name: "An entity that is not a trend", caption: "Its caption" } }) },
    ];
    for (const items of [others, []]) {
      const res = await trendsPage(await world({ packs: [pack({ items })] }));
      expect(res.status).toBe(200);
      const text = textOf(mainOf(res.text));
      expect(text).toContain("This pack has no trends to show you.");
      expect(mainOf(res.text)).not.toMatch(/<svg\b|<table\b/);
      for (const said of ["A note that is not a trend.", "An assessment that is not a trend.", "An entity that is not a trend", "Its caption"]) expect(text).not.toContain(said);
      expect(focusable(res.text).map((s) => s.href)).toContain("/");
    }
    // A trend among other items: only the trend is drawn.
    const mixed = await trendsPage(await world({ packs: [pack({ items: [{ item: NOTE }, { item: HARBOUR }] })] }));
    expect(trendsOf(mixed.text).map((t) => t.title)).toEqual(["Harbour meetings"]);
    expect(textOf(mainOf(mixed.text))).not.toContain("A note that is not a trend.");
  });

  it("TS4: a reader with neither right, or with the reports right for a pack never published, gets the page of a path nothing serves", async () => {
    for (const rights of [[], ["run_analysis"], ["create_case", "export"]]) {
      const w = await world({ rights });
      const refused = await trendsPage(w);
      expect(refused.status, rights.join()).toBe(404);
      expect(refusalProblems(refused, await getAs(w, NOWHERE)), rights.join()).toEqual([]);
      expect(leakProblems(refused.text)).toEqual([]);
      expect(calls(w.conduit), rights.join()).toEqual([DRAFT_CALL, PUBLISHED_CALL]);
    }
    const unpublished = await world({ rights: [READ_REPORTS] });
    const refused = await trendsPage(unpublished);
    expect(refusalProblems(refused, await getAs(unpublished, NOWHERE))).toEqual([]);
    expect(calls(unpublished.conduit)).toEqual([DRAFT_CALL, PUBLISHED_CALL]);
    // Any other refusal of the working pack's read: the same page, whatever its words, and the published version is not asked.
    for (const [status, body] of [[404, { detail: "Not Found" }], [409, { detail: "a conflict, in words" }], [422, { detail: [{ msg: "field required" }] }]] as const) {
      const v = await world({ draft_answer: { status, body } });
      const res = await trendsPage(v);
      expect(refusalProblems(res, await getAs(v, NOWHERE)), String(status)).toEqual([]);
      expect(res.text).not.toContain("a conflict, in words");
      expect(calls(v.conduit), String(status)).toEqual([DRAFT_CALL]);
    }
  });

  it("TS5: a pack in a case the reader cannot see, a pack not in the case named, a pack that does not exist, or no case or pack: the same 404", async () => {
    const hidden = await world({ packs: [pack({ case_id: HIDDEN_CASE })] });
    for (const [label, path] of [
      ["a case the reader cannot see", address(HIDDEN_CASE)],
      ["a pack not in the case named", address(OTHER_CASE)],
      ["a pack that does not exist", address(CASE, "pack-nowhere")],
      ["a case that does not exist", address("case-nowhere")],
      ["no case", `${PATH}?pack=pack-estuary`],
      ["no pack", `${PATH}?case=${CASE}`],
      ["neither", PATH],
      ["two cases", `${PATH}?case=${CASE}&case=${OTHER_CASE}&pack=pack-estuary`],
    ] as const) {
      const res = await getAs(hidden, path);
      expect(res.status, label).toBe(404);
      expect(refusalProblems(res, await getAs(hidden, NOWHERE)), label).toEqual([]);
      expect(leakProblems(res.text), label).toEqual([]);
    }
    // The pack is there, in the hidden case, for someone who holds a level in it: the same address answers.
    const member = await world({ packs: [pack({ case_id: HIDDEN_CASE })], cases: { [HIDDEN_CASE]: "viewer" } });
    expect((await getAs(member, address(HIDDEN_CASE))).status).toBe(200);
    // An address with no case or no pack asks the Conduit nothing.
    const bare = await world();
    await getAs(bare, `${PATH}?pack=pack-estuary`);
    await getAs(bare, PATH);
    expect(bare.conduit.calls).toEqual([]);
  });

  it("TS6: no answer or a 5xx is 'could not be read', with no part of a chart or table; a 401 says to sign in again", async () => {
    const cases: [string, WorldOptions][] = [
      ["no answer", { no_answer: true }],
      ["a 503", { draft_answer: { status: 503, body: { detail: "Service Unavailable" } } }],
      ["a 500 in text", { draft_answer: { status: 500, body: "<html>an error page</html>" } }],
      ["a 200 in text", { draft_answer: { status: 200, body: "<html>not JSON</html>" } }],
      ["the published read failing", { rights: [READ_REPORTS], packs: [PUBLISHED_PACK], published_answer: { status: 502, body: {} } }],
    ];
    for (const [label, options] of cases) {
      const res = await trendsPage(await world(options));
      expect(res.status, label).toBe(502);
      expect(textOf(mainOf(res.text)), label).toContain(UNREADABLE);
      expect(mainOf(res.text), label).not.toMatch(/<svg\b|<table\b/);
      expect(res.text, label).not.toContain("Harbour meetings");
    }
    const away = await trendsPage(await world({ conduitUrl: await closedAddress() }));
    expect(away.status).toBe(502);
    expect(textOf(mainOf(away.text))).toContain(UNREADABLE);
    const ended = await trendsPage(await world({ unknownBearer: true }));
    expect(ended.status).toBe(401);
    expect(textOf(mainOf(ended.text))).toContain(refusalWords(401, undefined, ""));
    expect(textOf(mainOf(ended.text))).not.toContain(UNREADABLE);
    expect(mainOf(ended.text)).not.toMatch(/<svg\b|<table\b/);
  });

  it("TS7: a body missing any field the generated types require, or holding one of the wrong shape, could not be read: never a zero", async () => {
    // The cases come from the generated files' own field lists: a field the schema adds later is a case here.
    const required = TYPES.flatMap((t) => fieldsOf(t.file, t.name).filter((f) => f.required).map((f) => `${t.name}.${f.field}`));
    expect(required.length).toBeGreaterThan(25);
    expect(await strictProblems(throughThePage)).toEqual([]);
    const shapes: [string, (b: Body) => void][] = [
      ["a total that is text", (b) => void (at(trendOf(b), "result")["total"] = "1250")],
      ["a value that is text", (b) => void (at(trendOf(b), "result", "points", 0)["value"] = "3")],
      ["withheld that is text", (b) => void (b["withheld"] = "no")],
      ["items that is an object", (b) => void (b["items"] = {})],
      ["a kind no item has", (b) => void (at(b, "items", 0)["kind"] = "chart")],
      ["an interval no trend has", (b) => void (at(trendOf(b), "result")["interval"] = "day")],
      ["a trend item with no figures", (b) => void (at(b, "items", 0)["trend"] = null)],
      ["a day that is not a day", (b) => void (trendOf(b)["as_of"] = "soon")],
      ["a series that is a number", (b) => void (at(trendOf(b), "result", "points", 0)["series"] = 4)],
      ["weeks that is text", (b) => void (at(trendOf(b), "definition")["weeks"] = "four")],
      ["a body that is a list", (b) => void Object.keys(b).forEach((k) => delete b[k])],
    ];
    for (const [label, change] of shapes) {
      const body = clone(baseBody("draft"));
      change(body);
      const res = await throughThePage("draft", label === "a body that is a list" ? ([] as unknown as Body) : body);
      expect(res.status, label).toBe(502);
      expect(res.text, label).toContain(UNREADABLE);
      expect(textOf(mainOf(res.text)), label).not.toMatch(/\b0 events\b|Harbour meetings/);
    }
  }, 120_000);

  it("TS8: every field of the generated types is drawn or named in the scenario as left out: the field census", async () => {
    const named = leftOut();
    expect(named.size).toBeGreaterThan(20);
    expect(await censusProblems(throughThePage)).toEqual([]);
  }, 120_000);

  it("TS9: a holder of the right to record assessments sees the working pack; a reader of reports alone sees the newest published version", async () => {
    const published = pack({
      items: [{ item: HARBOUR }, { item: FERRY }, { item: TOLL }],
      published: { version: 2, published_at: "2026-11-03T15:00:00Z", published_by: "someone-synthetic", items: [{ item: TOLL }, { item: HARBOUR }] },
    });
    const editor = await world({ packs: [published], rights: [RECORD_ASSESSMENT, READ_REPORTS] });
    const working = await trendsPage(editor);
    expect(trendsOf(working.text).map((t) => t.title)).toEqual(["Harbour meetings", "Ferry crossings", "Toll payments"]);
    expect(textOf(mainOf(working.text))).toContain("The working pack, as it stands now.");
    expect(calls(editor.conduit)).toEqual([DRAFT_CALL]);
    const reader = await world({ packs: [published], rights: [READ_REPORTS] });
    const version = await trendsPage(reader);
    expect(version.status).toBe(200);
    expect(trendsOf(version.text).map((t) => t.title)).toEqual(["Toll payments", "Harbour meetings"]);
    expect(textOf(mainOf(version.text))).toContain("Published version 2, on 3 November 2026.");
    expect(textOf(mainOf(version.text))).not.toContain("The working pack");
    expect(calls(reader.conduit)).toEqual([DRAFT_CALL, PUBLISHED_CALL]);
    // A published version's withheld item is said the same way.
    const hiddenThere = await trendsPage(await world({ packs: [published], rights: [READ_REPORTS], hide: ["item-toll"] }));
    expect(trendsOf(hiddenThere.text).map((t) => t.title)).toEqual(["Harbour meetings"]);
    expect(textOf(mainOf(hiddenThere.text))).toContain(WITHHELD_ITEMS_SENTENCE);
  });

  it("TS10: asks the Conduit as the person and nothing of the browser's, on the pack routes alone: no trend route, no query, no write", async () => {
    const w = await world();
    const res = await getAs(w, `${address()}&limit=1&token=abc&live=1`)
      .set("Origin", "https://browser.example.test")
      .set("Referer", "https://browser.example.test/somewhere")
      .set("X-CSRF-Token", w.csrf)
      .set("X-Forwarded-For", "203.0.113.7");
    expect(res.status).toBe(200);
    expect(calls(w.conduit)).toEqual([DRAFT_CALL]);
    const allowed = new Set(["authorization", "accept", "host", "connection", "user-agent", "accept-language", "accept-encoding", "sec-fetch-mode"]);
    for (const call of w.conduit.calls) {
      expect(call.headers["authorization"]).toBe(`Bearer ${w.token}`);
      expect(Object.keys(call.headers).filter((name) => !allowed.has(name))).toEqual([]);
      expect(call.url).not.toMatch(/trends|\?/);
    }
    // An identifier that is not a plain name is sent as one segment: it cannot change the route.
    const odd = await world();
    await getAs(odd, address(CASE, "../../trends/x"));
    expect(calls(odd.conduit)).toEqual([`GET /v1/investigations/${CASE}/packs/..%2F..%2Ftrends%2Fx`]);
    const bare = await world();
    const unsigned = await request(bare.app).get(address());
    expect(unsigned.status).toBe(302);
    expect(unsigned.headers["location"]).toBe("/session/sign-in");
    expect(unsigned.text).not.toContain("Harbour meetings");
    for (const method of ["post", "put", "patch", "delete"] as const) {
      const sent = await request(bare.app)[method](address()).set("Cookie", bare.cookie).set("X-CSRF-Token", bare.csrf).type("form").send({ _csrf: bare.csrf });
      expect(sent.status, method).toBe(404);
    }
    expect(bare.conduit.calls).toEqual([]);
    expect(PAGES.find((p) => p.path === PATH)?.methods).toEqual(["GET"]);
  });

  it("TS11: has the structure a reader moves by, no control but the sign-out, and the stops in the page's order: skip link, sign-out, Home", async () => {
    for (const options of [{}, { hide: ["item-ferry"] }, { packs: [pack({ items: [] })] }, { draft_answer: { status: 503, body: {} } }] as WorldOptions[]) {
      const res = await trendsPage(await world(options));
      expect(structureProblems(res.text), JSON.stringify(options)).toEqual([]);
      const stops = focusable(res.text);
      expect(stops.map((s) => s.text)).toEqual(["Skip to main content", "Sign out", "Back to Home"]);
      expect(stops.map((s) => s.href)).toEqual(["#main", undefined, "/"]);
    }
    const res = await trendsPage(await world());
    expect(headings(mainOf(res.text))).toEqual([
      { level: 1, text: "Trends shown together" },
      { level: 2, text: "Harbour meetings" },
      { level: 2, text: "Ferry crossings" },
      { level: 2, text: "Toll payments" },
    ]);
  });

  it("TS12: is whole with scripts off: no script but the data block, no handler or inline style, each chart plain SVG with classes, a text alternative and its table", async () => {
    const res = await trendsPage(await world());
    expect(scriptsOffProblems(res.text)).toEqual([]);
    expect(trendsOf(res.text)).toHaveLength(3);
    expect(res.headers["content-security-policy"]).not.toMatch(/unsafe-inline|unsafe-eval/);
    for (const options of [{ packs: [pack({ items: [] })] }, { draft_answer: { status: 503, body: {} } }] as WorldOptions[]) {
      expect(scriptsOffProblems((await trendsPage(await world(options))).text)).toEqual([]);
    }
  });

  it("TS13: the page's words are British English and its own, the shared words are imported, the session's words are the Studio's, and nothing says board", () => {
    const sources = sourcesOfThePage();
    expect(americanSpellings(sources.map((s) => s.text).join("\n"))).toEqual([]);
    expect(copiesOfSharedWords(sources)).toEqual([]);
    expect(boardProblems(sources)).toEqual([]);
    const words = read(PAGES_DIR, "server", "views", "packTrendsWords.ts");
    expect(words).toMatch(/WITHHELD_ITEMS_SENTENCE[\s\S]*trendSentence|trendSentence[\s\S]*WITHHELD_ITEMS_SENTENCE/);
    expect(words).toContain("@ospreyflow/glass-shared");
    expect(withoutComments(read(PAGES_DIR, "server", "packTrends.ts"))).toContain("refusalWords");
    expect(/board/i.test(PATH)).toBe(false);
  });
});

// ------------------------------------------------------------------------------------------------ the switch and the lists

function listedRoutes(text: string): string[] {
  const lines = text.split("\n").filter((l) => !/^\s*(#|$)/.test(l));
  expect(lines[0]).toBe("routes:");
  return lines.slice(1).map((l) => /^\s+-\s+"?(\/[^"\s]*)"?\s*$/.exec(l)?.[1] ?? `NOT A ROUTE: ${l}`);
}

function figuresRow(functionsText: string): { scenario: string; route: string } | undefined {
  const found = /- id: reports-figures\n(?:    .*\n)*?    scenario: "([^"]*)"\n    route: "([^"]*)"/.exec(functionsText);
  return found ? { scenario: found[1] as string, route: found[2] as string } : undefined;
}

function listProblems(routesText: string, functionsText: string): string[] {
  const found: string[] = [];
  if (!listedRoutes(routesText).includes(PATH)) found.push(`${PATH} is not in the route list`);
  const row = figuresRow(functionsText);
  if (!row) return [...found, "the reports-figures row of FUNCTIONS.yaml has no scenario and route"];
  const wanted = Array.from({ length: 15 }, (_, i) => `TS${i + 1}`);
  if (row.scenario.split(",").map((s) => s.trim()).join() !== wanted.join()) found.push(`the reports-figures row's scenario is ${JSON.stringify(row.scenario)}`);
  if (row.route !== "") found.push(`the reports-figures row has the route ${JSON.stringify(row.route)} while the function is not complete`);
  return found;
}

describe("the tree that serves the page, and the lists that name it", () => {
  it("TS14: the govuk tree serves it; the Default tree answers it as a path nothing serves and asks nothing; the lists name it", async () => {
    expect((await trendsPage(await world({ tree: "govuk" }))).status).toBe(200);
    const other = await world({ tree: "default" });
    for (const signed of [true, false]) {
      const there = signed ? await trendsPage(other) : await request(other.app).get(address());
      const nowhere = signed ? await getAs(other, NOWHERE) : await request(other.app).get(NOWHERE);
      expect(there.status).toBe(404);
      expect(refusalProblems(there, nowhere)).toEqual([]);
    }
    expect(other.conduit.calls).toEqual([]);
    const page = PAGES.find((p) => p.path === PATH);
    expect([page?.id, page?.trees]).toEqual(["reports-figures", ["govuk"]]);
    expect(listProblems(read(PAGES_DIR, "tree-govuk", "routes.yaml"), read(PAGES_DIR, "FUNCTIONS.yaml"))).toEqual([]);
  });
});

// ------------------------------------------------------------------------------------------------ planted faults (rule 15)

/** The real words module with one change, imported from a folder of its own: the plant is in the real file's own code. */
async function plantedViews(change: (source: string) => string): Promise<{ readDraft: (b: unknown) => unknown; readPublished: (b: unknown) => unknown }> {
  const real = read(PAGES_DIR, "server", "views", "packTrendsWords.ts");
  const planted = change(real);
  expect(planted, "the plant changed the file").not.toBe(real);
  const folder = mkdtempSync(join(tmpdir(), "gr4a-planted-"));
  try {
    const file = join(folder, "planted.ts");
    writeFileSync(file, planted.replace('"@ospreyflow/glass-shared"', JSON.stringify(join(CORE, "packages", "glass-shared", "src", "index.ts"))));
    return (await import(/* @vite-ignore */ file)) as { readDraft: (b: unknown) => unknown; readPublished: (b: unknown) => unknown };
  } finally {
    rmSync(folder, { recursive: true, force: true });
  }
}

const replaceOnce = (anchor: string, by: string) => (source: string): string => {
  expect(source.includes(anchor), `the plant's anchor ${JSON.stringify(anchor)} is in the file`).toBe(true);
  return source.replace(anchor, by);
};

/** The titles a view draws, in its order, and whether it says some were withheld. */
const viewTitles = (view: unknown): string[] => ((view as { trends?: { title: string }[] } | undefined)?.trends ?? []).map((t) => t.title);
const orderProblems = (view: (b: unknown) => unknown): string[] => {
  const body = draftBody(pack(), "t");
  const want = (body["items"] as Body[]).filter((i) => i["kind"] === "trend").map((i) => String(at(i, "trend", "definition")["title"]));
  return JSON.stringify(viewTitles(view(body))) === JSON.stringify(want) ? [] : [`the view draws ${JSON.stringify(viewTitles(view(body)))}, not ${JSON.stringify(want)}`];
};
const withheldProblems = (view: (b: unknown) => unknown): string[] => {
  const body = draftBody(pack({ items: [{ item: HARBOUR }, { item: FERRY, hiddenFrom: ["t"] }, { item: TOLL }] }), "t");
  const drawn = view(body) as { withheld?: boolean; trends?: unknown[] } | undefined;
  const found: string[] = [];
  if (drawn?.withheld !== true) found.push("the view does not say some items are withheld");
  if ((drawn?.trends ?? []).length !== 2) found.push(`the view draws ${(drawn?.trends ?? []).length} trends for two readable ones`);
  return found;
};
const kindProblems = (view: (b: unknown) => unknown): string[] => {
  const body = draftBody(pack({ items: [{ item: NOTE }, { item: HARBOUR }] }), "t");
  return JSON.stringify(view(body)).includes("A note that is not a trend.") || viewTitles(view(body)).length !== 1 ? ["the view draws an item that is not a trend"] : [];
};

describe("each check above is red against the real page, file or fixture with one thing changed", () => {
  it("TS15: the real view passes the order, withheld and kind checks, and each planted change in its own loop is found", async () => {
    expect(orderProblems(readDraft)).toEqual([]);
    expect(withheldProblems(readDraft)).toEqual([]);
    expect(kindProblems(readDraft)).toEqual([]);
    const reversed = await plantedViews(replaceOnce("const trends: TrendView[] = [];", "const trends: TrendView[] = [];\n  items.reverse();"));
    expect(orderProblems(reversed.readDraft)).not.toEqual([]);
    const sorted = await plantedViews(replaceOnce("return { kind: \"trends\",", "trends.sort((a, b) => a.title.localeCompare(b.title));\n  return { kind: \"trends\","));
    expect(orderProblems(sorted.readDraft)).not.toEqual([]);
    const unsaid = await plantedViews(replaceOnce("withheld: body[\"withheld\"]", "withheld: false && body[\"withheld\"]"));
    expect(withheldProblems(unsaid.readDraft)).not.toEqual([]);
    const everyKind = await plantedViews(replaceOnce("if (item.kind !== \"trend\") continue;", "if (item.kind !== \"trend\") { trends.push({ title: String(item[\"note\"]) } as TrendView); continue; }"));
    expect(kindProblems(everyKind.readDraft)).not.toEqual([]);
  });

  it("TS15: the strict reader's check finds a missing field read as a zero, and the census finds a left-out field drawn and a field undrawn", async () => {
    const real = throughAView(readDraft, readPublished);
    expect(await strictProblems(real)).toEqual([]);
    expect(await censusProblems(real)).toEqual([]);
    // A missing total read as a zero, in the real reader.
    const lenient = await plantedViews(replaceOnce('isNumber(result["total"])', '(result["total"] === undefined || isNumber(result["total"]))'));
    expect(await strictProblems(throughAView(lenient.readDraft, lenient.readPublished))).toContain("TrendResult.total left out was drawn (200)");
    // A field the scenario names as left out, drawn: the person who added the item.
    const addedBy = await plantedViews(replaceOnce("trends.push(trendView(figures, item.marking));", "trends.push(trendView(figures, `${item.marking} ${String(item[\"added_by\"])}`));"));
    expect(await censusProblems(throughAView(addedBy.readDraft, addedBy.readPublished))).toContain("PackItem.added_by is named as left out, but changing it changes the page");
    // A field the census reads as drawn but the view drops: the published version's number.
    const noVersion = await plantedViews(replaceOnce("published(version,", "published(0,"));
    expect(await censusProblems(throughAView(noVersion.readDraft, noVersion.readPublished))).toContain("PublishedPack.version is not drawn: changing it does not change the page");
    // A field the scenario stops naming: neither drawn nor left out.
    const fewer = leftOut();
    fewer.delete("PackItem.added_by");
    expect(await censusProblems(real, fewer)).toContain("PackItem.added_by is neither drawn nor named as left out");
  }, 120_000);

  it("TS15: the structure, scripts-off, same-figures and refusal checks find each fault the real page does not have", async () => {
    const res = await trendsPage(await world());
    const page = res.text;
    expect(scriptsOffProblems(page)).toEqual([]);
    expect(structureProblems(page)).toEqual([]);
    const plant = (pattern: RegExp, by: string): string => {
      expect(pattern.test(page), `the plant's anchor ${String(pattern)} is in the page`).toBe(true);
      return page.replace(pattern, by);
    };
    expect(scriptsOffProblems(plant(/<rect\b/, '<rect style="fill:red"'))).toContain("an inline style attribute");
    expect(scriptsOffProblems(plant(/<rect\b/, '<rect fill="#c00"'))).toContain("a colour written on an element, not by a class");
    expect(scriptsOffProblems(plant(/<\/main>/, '<script src="/x.js"></script></main>'))).not.toEqual([]);
    expect(scriptsOffProblems(plant(/<svg\b[\s\S]*?<\/svg>/, ""))).toContain('the trend "Harbour meetings" has no chart');
    expect(scriptsOffProblems(plant(/<title id="[^"]*">[^<]*<\/title>/, ""))).toContain('the chart of "Harbour meetings" has no text alternative');
    expect(scriptsOffProblems(plant(/<table\b[\s\S]*?<\/table>/, ""))).toContain('the chart of "Harbour meetings" is not followed by its table');
    expect(structureProblems(plant(/<h2\b([^>]*)>([^<]*)<\/h2>/, "<h3$1>$2</h3>"))).toContain('the heading "Harbour meetings" skips from level 1 to 3');
    expect(structureProblems(plant(/<\/main>/, '<form method="post" action="/v1/x"><button>Arrange</button></form></main>'))).not.toEqual([]);
    expect(structureProblems(plant(/scope="row"/, ""))).not.toEqual([]);
    const harbour = trendsOf(page)[0] as DrawnTrend;
    expect(sameFiguresProblems(harbour)).toEqual([]);
    const wrongBar = { ...harbour, chart: { ...(harbour.chart as DrawnChart), bars: (harbour.chart as DrawnChart).bars.map((b, i) => (i === 1 ? { ...b, height: 40 } : b)) } };
    expect(sameFiguresProblems(wrongBar)).not.toEqual([]);
    const lostBar = { ...harbour, chart: { ...(harbour.chart as DrawnChart), bars: (harbour.chart as DrawnChart).bars.slice(1) } };
    expect(sameFiguresProblems(lostBar)).not.toEqual([]);
    // A refusal that says the Conduit's words, or that is not the unknown path's page.
    const w = await world({ rights: [] });
    const unknown = await getAs(w, NOWHERE);
    expect(refusalProblems({ status: 403, text: unknown.text }, unknown)).not.toEqual([]);
    expect(refusalProblems({ status: 404, text: unknown.text.replace("That page could not be found.", "right_required") }, unknown)).not.toEqual([]);
    expect(leakProblems(unknown.text.replace("</main>", "<p>record_assessment</p></main>"))).not.toEqual([]);
    // The words checks: an American spelling, the shared sentence written again, the word board.
    expect(americanSpellings("the bar's color")).toEqual(["color"]);
    expect(copiesOfSharedWords([{ name: "x.ts", text: `const s = "${WITHHELD_ITEMS_SENTENCE}";` }])).not.toEqual([]);
    expect(boardProblems([{ name: "x.njk", text: '<div class="trend-board">' }])).not.toEqual([]);
    // The list check: the path left out of the route list, the row given a route.
    const routesText = read(PAGES_DIR, "tree-govuk", "routes.yaml");
    const functionsText = read(PAGES_DIR, "FUNCTIONS.yaml");
    expect(listProblems(routesText.replace(`  - ${PATH}\n`, ""), functionsText)).not.toEqual([]);
    expect(listProblems(routesText, functionsText.replace(/(- id: reports-figures\n(?:    .*\n)*?    route: )""/, `$1"${PATH}"`))).not.toEqual([]);
  });

  it("TS15: the fixture Conduit refuses what the real pack routes refuse, in their order, and decides withheld from its world", async () => {
    const token = "fixture-token";
    const c = await packsConduit({
      readers: [
        { token, rights: [RECORD_ASSESSMENT], cases: { [CASE]: "viewer" } },
        { token: "reports-only", rights: [READ_REPORTS], cases: { [CASE]: "viewer" } },
      ],
      cases: [CASE, OTHER_CASE],
      packs: [pack({ items: [{ item: HARBOUR }, { item: FERRY, hiddenFrom: [token] }] })],
    });
    conduits.push(c);
    const ask = async (path: string, init: { method?: string; token?: string | null } = {}) => {
      const headers: Record<string, string> = init.token === null ? {} : { Authorization: `Bearer ${init.token ?? token}` };
      const res = await fetch(`${c.url}${path}`, { method: init.method ?? "GET", headers });
      return { status: res.status, body: (await res.json()) as unknown };
    };
    const P = `/v1/investigations/${CASE}/packs/pack-estuary`;
    expect(await ask(P, { token: null })).toEqual({ status: 401, body: { detail: "Not authenticated" } });
    expect(await ask(P, { token: "someone-else" })).toEqual({ status: 401, body: { detail: "Not authenticated" } });
    expect(await ask(`${P}?access_token=${token}`, { token: null })).toEqual({ status: 401, body: { detail: "Not authenticated" } });
    expect(await ask(P, { token: "reports-only" })).toEqual({ status: 403, body: { detail: { error: "right_required", right: RECORD_ASSESSMENT } } });
    expect(await ask(`${P}/published`)).toEqual({ status: 403, body: { detail: { error: "right_required", right: READ_REPORTS } } });
    expect(await ask(`/v1/investigations/${OTHER_CASE}/packs/pack-estuary`)).toEqual({ status: 404, body: { error: "investigation_not_found" } });
    expect(await ask(`/v1/investigations/case-nowhere/packs/pack-estuary`)).toEqual({ status: 404, body: { error: "investigation_not_found" } });
    expect(await ask(`/v1/investigations/${CASE}/packs/pack-nowhere`)).toEqual({ status: 404, body: { detail: "no such pack in this case" } });
    expect(await ask(`${P}/published`, { token: "reports-only" })).toEqual({ status: 404, body: { detail: "this pack has no publication" } });
    expect(await ask(P, { method: "DELETE" })).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
    expect(await ask(`${P}/order`, { method: "PUT" })).toEqual({ status: 403, body: { detail: "Editor access to this investigation is required" } });
    expect(await ask(`/v1/investigations/${CASE}/trends/trend-harbour/figures`)).toEqual({ status: 404, body: { detail: "Not Found" } });
    // The router answers before the bearer: a method a path does not serve is 405 for anyone.
    expect((await ask(P, { method: "PATCH", token: null })).status).toBe(405);
    // Withheld is decided from the world, as the store's query does: a yes or no, the rest in order.
    const granted = await ask(P);
    expect(granted.status).toBe(200);
    const body = granted.body as Body;
    expect((body["items"] as Body[]).map((i) => i["id"])).toEqual(["item-harbour"]);
    expect(body["withheld"]).toBe(true);
    expect(readableFor([{ item: HARBOUR }], token)).toEqual({ items: [HARBOUR], withheld: false });
    // Every field of PackDraft's and PackItem's models is in what it sends (so the census and the strict reader see the real shape).
    for (const { field } of fieldsOf("PackDraft.ts", "PackDraft")) expect(Object.keys(body), field).toContain(field);
    for (const { field } of fieldsOf("PackDraft.ts", "ReportPack")) expect(Object.keys(at(body, "pack")), field).toContain(field);
    for (const { field } of fieldsOf("PackDraft.ts", "PackItem")) expect(Object.keys(at(body, "items", 0)), field).toContain(field);
    for (const { field } of fieldsOf("PackDraft.ts", "TrendFigures")) expect(Object.keys(at(body, "items", 0, "trend")), field).toContain(field);
    for (const { field } of fieldsOf("PackDraft.ts", "TrendResult")) expect(Object.keys(at(body, "items", 0, "trend", "result")), field).toContain(field);
    for (const { field } of fieldsOf("PackDraft.ts", "TrendDefinitionInput")) expect(Object.keys(at(body, "items", 0, "trend", "definition")), field).toContain(field);
    for (const { field } of fieldsOf("PublishedPack.ts", "PublishedPack")) expect(Object.keys(publishedBody(PUBLISHED_PACK, token)), field).toContain(field);
  });
});
