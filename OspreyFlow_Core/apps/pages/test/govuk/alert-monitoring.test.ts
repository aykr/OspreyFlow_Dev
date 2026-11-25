/**
 * The alert monitoring figures as a GOV.UK page, a table and a plain SVG chart of the same figures (slice GR3a, build GR3; ADR-152
 * decisions 7, 8, 10 and 12, invariants I1, I2, I4, I7 and I15; FUNCTIONS row `reports-figures`; scenario AM; the owner's rulings of
 * 24 November 2026: charts are plain SVG with classes, no library, no inline style, each with a table of the same figures; a
 * non-viewer at the report route gets the answer a missing report gets).
 *
 * There is no React-first proof for this page (the React board, `AlertMonitoringBoard.tsx`, has no scenario in `spec/08`): each case's
 * id is a scenario of `spec/08_ACCEPTANCE_SCENARIOS.md` ("Scenario AM"), written first, and `tests/glass_trees/test_govuk_alert_monitoring_scenario.py`
 * holds the two in step. The Conduit is a fixture (`support/fakeReportConduit.ts`) that models the real report route's refusals as well
 * as its grants (rule 15): the right asked before the case, a case the person holds no level on answered as one that is not there,
 * every figure counted as the reader, the 409 past the bound, the held rows for Editors and above.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a figure missing from the table, or one the route did not send, or a table with no caption or scope                -> AM1
 *  - a bar that is not its figure, a chart with no text alternative, a chart after its table, a `style` attribute       -> AM2
 *  - a count of an alert the reader may not see, one fetch shown to everyone, held rows for a Viewer, a second route    -> AM3
 *  - a report past its bound drawn as a figure, or said without the way out                                              -> AM4
 *  - no alerts drawn as an empty chart                                                                                   -> AM5
 *  - a missing case, a non-viewer and a reader without `read_reports` answered differently, or the case id echoed        -> AM6
 *  - a Conduit that fails, or answers a body that is not figures, drawn as a figure                                      -> AM7
 *  - a script, a handler, an inline style, a tab stop above 0, a write answered, a policy with `unsafe-inline`           -> AM8
 *  - the page missing from the route list, the tree's switch, or the Default tree answering the path                     -> AM9
 *  - each planted fault of the checks above, run through the same function that finds nothing in the real page          -> AM11
 * AM10 (the Conduit's own two refusals) is the Python file's.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Express } from "express";
import { afterEach, describe, expect, it } from "vitest";

import { createApp } from "../../server/app.js";
import { PAGES } from "../../server/pageList.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { testClock } from "../support/clock.js";
import { fakeReportConduit } from "../support/fakeReportConduit.js";
import type { FakeReportConduit, Reader, WorldAlert } from "../support/fakeReportConduit.js";
import { request, signIn } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { bearer, providerFor, textOf } from "../support/studioWorld.js";

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

// ------------------------------------------------------------------------------------------------ the world

const CASE = "case-wing";
const EMPTY_CASE = "case-quiet";

/** What the case holds: the official alerts every reader below may see, and the ones only a secret reader may. */
function alertsOf(): WorldAlert[] {
  const official = (over: Partial<WorldAlert>): WorldAlert => ({ week: "2026-11-09", label: "typology", typology: "structuring", needs: "OFFICIAL", ...over });
  return [
    official({}),
    official({ closedAs: "false_positive", tookBand: "under a day" }),
    official({ closedAs: "true_positive", tookBand: "1 to 7 days" }),
    official({ label: "hotlists", typology: undefined }),
    official({ week: "2026-11-16" }),
    official({ week: "2026-11-16", closedAs: "false_positive", tookBand: "under a day" }),
    official({ week: "2026-11-16", typology: "rapid_movement" }),
    official({ week: "2026-11-16", typology: "rapid_movement" }),
    // Seven alerts of a typology that only the secret reader may see: they are in no figure of an official reader.
    ...Array.from({ length: 7 }, () => official({ week: "2026-11-16", typology: "circular_flow", needs: "SECRET" })),
  ];
}
const OFFICIAL_TOTAL = 8;
const SECRET_TOTAL = 15;

const readerOf = (over: Partial<Reader>): Reader => ({
  token: bearer(),
  id: "reader",
  clearance: "OFFICIAL",
  rights: ["read_reports"],
  cases: { [CASE]: "editor", [EMPTY_CASE]: "editor" },
  ...over,
});

interface Visit {
  conduit: FakeReportConduit;
  app: Express;
  cookie: string;
  csrf: string;
  token: string;
  get(path: string): ReturnType<ReturnType<typeof request>["get"]>;
}

const conduits: FakeReportConduit[] = [];
afterEach(async () => {
  while (conduits.length > 0) await conduits.pop()?.stop();
});

function appFor(conduit: FakeReportConduit, token: string, tree: "govuk" | "default" = "govuk", log: (m: string) => void = () => undefined): Express {
  return createApp({
    store: new MemorySessionStore({ clock: testClock() }),
    identityProvider: providerFor(token),
    sessionSecret: generateSecret(48),
    pages: PAGES,
    tree,
    forward: { conduitUrl: conduit.url, bodyMaxBytes: 1024, uploadMaxBytes: 1024, upstreamTimeoutSeconds: 2 },
    log,
  });
}

/** One Conduit, the world in it, and a signed-in visit for a reader of it. */
async function visitAs(reader: Reader, others: Reader[] = [], tree: "govuk" | "default" = "govuk"): Promise<Visit> {
  const conduit = await fakeReportConduit([reader, ...others]);
  conduits.push(conduit);
  conduit.world.set(CASE, alertsOf());
  conduit.world.set(EMPTY_CASE, []);
  return visitOn(conduit, reader, tree);
}

async function visitOn(conduit: FakeReportConduit, reader: Reader, tree: "govuk" | "default" = "govuk"): Promise<Visit> {
  const app = appFor(conduit, reader.token, tree);
  const signed = await signIn(app);
  return { conduit, app, cookie: signed.cookie, csrf: signed.csrf, token: reader.token, get: (path) => request(app).get(path).set("Cookie", signed.cookie) };
}

// ------------------------------------------------------------------------------------------------ reading a page

const strip = (html: string): string => html.replace(/<!--[\s\S]*?-->/g, "");
const unescaped = (text: string): string => text.replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const attr = (tag: string, name: string): string | undefined => {
  const found = new RegExp(`\\s${name}="([^"]*)"`).exec(tag)?.[1];
  return found === undefined ? undefined : unescaped(found);
};
const mainOf = (html: string): string => (/<main\b[^>]*>([\s\S]*?)<\/main>/.exec(strip(html))?.[1] as string | undefined) ?? "";
const words = (html: string): string => textOf(mainOf(html)).replace(/&#39;/g, "'").replace(/\s+/g, " ").trim();
const sameFor = (html: string, csrf: string): string => html.split(csrf).join("CSRF").replace(/nonce="[^"]*"/g, 'nonce="N"');

interface Table {
  caption: string;
  heads: string[];
  scopes: (string | undefined)[];
  rows: { head: string; rowScope: string | undefined; cells: string[] }[];
}

function tablesOf(html: string): Table[] {
  return [...mainOf(html).matchAll(/<table\b[^>]*>([\s\S]*?)<\/table>/g)].map((t) => {
    const inner = t[1] as string;
    const head = /<thead\b[^>]*>([\s\S]*?)<\/thead>/.exec(inner)?.[1] ?? "";
    const heads = [...head.matchAll(/<th\b([^>]*)>([\s\S]*?)<\/th>/g)];
    const body = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/.exec(inner)?.[1] ?? "";
    return {
      caption: textOf(/<caption\b[^>]*>([\s\S]*?)<\/caption>/.exec(inner)?.[1] ?? ""),
      heads: heads.map((h) => textOf(h[2] as string)),
      scopes: heads.map((h) => attr(h[1] as string, "scope")),
      rows: [...body.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((r) => {
        const cells = [...(r[1] as string).matchAll(/<(th|td)\b([^>]*)>([\s\S]*?)<\/\1>/g)];
        return { head: textOf((cells[0]?.[3] as string | undefined) ?? ""), rowScope: cells[0]?.[1] === "th" ? attr(cells[0][2] as string, "scope") : undefined, cells: cells.slice(1).map((c) => textOf(c[3] as string)) };
      }),
    };
  });
}

interface Chart {
  /** The svg element's own attributes. */
  svg: string;
  title: string;
  desc: string;
  labels: string[];
  values: string[];
  bars: { cls: string | undefined; width: number | undefined; tag: string }[];
}

const chartsIn = (fragment: string): Chart[] =>
  [...fragment.matchAll(/<svg\b([^>]*)>([\s\S]*?)<\/svg>/g)].map((m) => {
    const inner = m[2] as string;
    const texts = [...inner.matchAll(/<text\b([^>]*)>([\s\S]*?)<\/text>/g)];
    return {
      svg: m[1] as string,
      title: textOf(/<title\b[^>]*>([\s\S]*?)<\/title>/.exec(inner)?.[1] ?? ""),
      desc: textOf(/<desc\b[^>]*>([\s\S]*?)<\/desc>/.exec(inner)?.[1] ?? ""),
      labels: texts.filter((t) => attr(t[1] as string, "class") === "figure-chart__label").map((t) => textOf(t[2] as string)),
      values: texts.filter((t) => attr(t[1] as string, "class") === "figure-chart__value").map((t) => textOf(t[2] as string)),
      bars: [...inner.matchAll(/<rect\b([^>]*)>/g)].map((r) => ({ cls: attr(r[1] as string, "class"), width: attr(r[1] as string, "width") === undefined ? undefined : Number(attr(r[1] as string, "width")), tag: r[0] })),
    };
  });

/** The widest a bar is drawn, in the chart's own units: the largest figure is this wide and the rest are in proportion. */
const WIDEST = 240;

/** Every fault in the pairing of a chart and its table, in words: the same function reads the real page and each planted one (AM2). */
function chartProblems(html: string): string[] {
  const page = strip(mainOf(html));
  const found: string[] = [];
  const sections = [...page.matchAll(/<section\b[^>]*>([\s\S]*?)<\/section>/g)].map((s) => s[1] as string);
  const drawn = sections.filter((s) => /<svg\b/.test(s));
  if (drawn.length === 0) found.push("the page draws no chart");
  for (const section of drawn) {
    const [chart] = chartsIn(section);
    const [table] = tablesOf(`<main>${section}</main>`);
    if (!chart) continue;
    if (!table) {
      found.push("a chart has no table of the same figures");
      continue;
    }
    if (section.indexOf("<svg") > section.indexOf("<table")) found.push(`the chart of ${table.caption} comes after its table: the table follows the chart`);
    if (!/\srole="img"/.test(chart.svg)) found.push(`the chart of ${table.caption} is not role="img"`);
    if (chart.title === "" || chart.desc === "") found.push(`the chart of ${table.caption} has no text alternative (a title and a description)`);
    if (!/\saria-labelledby="[^"]+"/.test(chart.svg)) found.push(`the chart of ${table.caption} does not name its title and description`);
    if (chart.bars.length !== table.rows.length) found.push(`the chart of ${table.caption} has ${chart.bars.length} bars for ${table.rows.length} rows`);
    const figures = table.rows.map((r) => Number((r.cells[0] ?? "").replace(/,/g, "")));
    const most = Math.max(1, ...figures);
    table.rows.forEach((row, i) => {
      if (chart.labels[i] !== row.head) found.push(`the chart's label ${JSON.stringify(chart.labels[i])} is not the table's ${JSON.stringify(row.head)}`);
      if (chart.values[i] !== row.cells[0]) found.push(`the chart says ${JSON.stringify(chart.values[i])} for ${row.head} where the table says ${JSON.stringify(row.cells[0])}`);
      const bar = chart.bars[i];
      if (!bar || bar.cls !== "figure-chart__bar") found.push(`the bar for ${row.head} has no class figure-chart__bar`);
      else if (bar.width === undefined || Math.abs(bar.width - Math.round(((figures[i] as number) / most) * WIDEST)) > 1) {
        found.push(`the bar for ${row.head} is ${String(bar.width)} wide, not in proportion to ${String(row.cells[0])}`);
      }
    });
  }
  return found;
}

/** Everything in a page that needs a script, an inline rule or a tab stop out of order (AM8; the Help page's own, shared in kind). */
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
  for (const l of page.matchAll(/<(?:link|img|iframe|object|embed|image|use)\b[^>]*\s(?:href|src|data|xlink:href)="([^"]*)"/g)) {
    if (/^(?:[a-z]+:)?\/\//i.test(l[1] as string)) found.push(`an address on another origin: ${l[1] as string}`);
  }
  return found;
}

/** The structure of the page: one banner, one main, the skip link first, one heading of the first level, captioned and scoped tables. */
function structureProblems(html: string): string[] {
  const page = strip(html);
  const found: string[] = [];
  if (!/<html\b[^>]*\slang="en-GB"/.test(page)) found.push('the page is not lang="en-GB"');
  if ([...page.matchAll(/<main\b/g)].length !== 1) found.push("the page has not exactly one main landmark");
  const first = /<(a|button)\b([^>]*)>/.exec(page);
  if (!first || attr(first[2] as string, "href") !== "#main") found.push("the first stop is not the skip link to the main landmark");
  const headings = [...mainOf(page).matchAll(/<h([1-6])\b/g)].map((m) => Number(m[1]));
  if (headings.filter((h) => h === 1).length !== 1) found.push("the main landmark has not exactly one heading of the first level");
  headings.forEach((level, i) => {
    if (level > (headings[i - 1] ?? 0) + 1) found.push(`a heading skips from level ${headings[i - 1] ?? 0} to ${level}`);
  });
  for (const t of tablesOf(page)) {
    if (t.caption === "") found.push("a table has no caption");
    if (t.heads.length === 0 || t.scopes.some((s) => s !== "col")) found.push('a table has a column header that is not a th scope="col"');
    if (t.rows.some((r) => r.rowScope !== "row")) found.push('a table row does not start with a th scope="row"');
  }
  return found;
}

/** The figures a page's tables carry, as `caption -> rows`, for a comparison with what the route sent. */
const figuresOnPage = (html: string): Record<string, string[][]> =>
  Object.fromEntries(tablesOf(html).map((t) => [t.caption, t.rows.map((r) => [r.head, ...r.cells])]));

interface Route {
  alerts_total: number;
  monitoring: {
    raised_by_rule: { week_start: string; label: string; typology?: string; count: number }[];
    closed_by_outcome: { week_start: string; label: string; count: number }[];
    time_to_close: { label: string; value: number }[];
    hotlist_matches: { week_start: string; count: number }[];
    open_by_source: { label: string; typology: string; age: string; count: number }[];
  };
  held: { held: number; released: number; rejected: number } | null;
}

/** What the route sends this reader, asked of the fixture directly with the reader's own bearer (never through the page). */
async function routeSays(conduit: FakeReportConduit, token: string, caseId: string, weeks = 12): Promise<Route> {
  const response = await fetch(`${conduit.url}/v1/investigations/${caseId}/reports?weeks=${weeks}`, { headers: { Authorization: `Bearer ${token}` } });
  conduit.calls.pop();
  if (response.status !== 200) throw new Error(`the fixture answered ${response.status}`);
  return (await response.json()) as Route;
}

/** The weeks the route sent, each with the sum of its rows: the table's rows, in order. */
function weeklyFrom(route: Route): [string, number][] {
  const weeks = new Map<string, number>();
  for (const w of route.monitoring.raised_by_rule) weeks.set(w.week_start, (weeks.get(w.week_start) ?? 0) + w.count);
  return [...weeks].sort(([a], [b]) => a.localeCompare(b));
}

const DAYS = new Intl.DateTimeFormat("en-GB", { dateStyle: "long", timeZone: "UTC" });
const day = (iso: string): string => DAYS.format(new Date(iso));

/** The open alerts' figures in step: the count in words is the sum of the table's cells, and each row has the four age bands (AM1, AM5). */
function openProblems(html: string): string[] {
  const found: string[] = [];
  const text = words(html);
  const said = /(\d[\d,]*) alerts? open/.exec(text);
  if (!said) return ["the page does not say how many alerts are open"];
  const table = tablesOf(html).find((t) => t.caption === "Open alerts by source and age");
  const rows = table?.rows ?? [];
  const sum = rows.reduce((n, r) => n + r.cells.reduce((m, c) => m + Number(c.replace(/,/g, "")), 0), 0);
  if (Number(said[1]?.replace(/,/g, "")) !== sum) found.push(`the page says ${said[1] as string} open where its table adds up to ${sum}`);
  if (table && table.heads.join("|") !== "Source|Under a day|1 to 7 days|7 to 30 days|Over 30 days") found.push(`the open alerts table's columns are ${table.heads.join("|")}`);
  for (const r of rows) if (r.cells.length !== 4) found.push(`the open alerts row ${r.head} has ${r.cells.length} figures, not one for each of the four ages`);
  return found;
}

const reportCalls = (conduit: FakeReportConduit): string[] => conduit.calls.map((c) => `${c.method} ${c.path}${c.query.size > 0 ? `?${c.query.toString()}` : ""}`);

// ------------------------------------------------------------------------------------------------ the page

describe("the alert monitoring figures (the govuk tree)", () => {
  it("AM1: draws the figures the route sends as captioned tables, with column headers, a row header, the period and the count", async () => {
    const official = readerOf({});
    const v = await visitAs(official);
    const res = await v.get(`/reports?case=${CASE}`);
    expect(res.status).toBe(200);
    expect(res.type).toMatch(/html/);
    expect(/<title>Alert monitoring · OspreyFlow<\/title>/.test(res.text)).toBe(true);
    expect(structureProblems(res.text)).toEqual([]);
    const route = await routeSays(v.conduit, official.token, CASE);
    const tables = figuresOnPage(res.text);
    // The week's total is the sum of its rows as the route sent them, in order of week; the page adds nothing of its own.
    // The open alerts, as the route counts them for this reader (every one it may see, whenever raised), in the order the route sent.
    expect(tables["Open alerts by source and age"]).toEqual([
      ["Hotlists", "0", "0", "1", "0"],
      ["Rapid movement", "0", "0", "2", "0"],
      ["Structuring", "0", "0", "2", "0"],
    ]);
    expect(route.monitoring.open_by_source).toEqual([
      { label: "hotlists", typology: "", age: "7 to 30 days", count: 1 },
      { label: "typology", typology: "rapid_movement", age: "7 to 30 days", count: 2 },
      { label: "typology", typology: "structuring", age: "7 to 30 days", count: 2 },
    ]);
    expect(tables["Alerts raised each week"]).toEqual(weeklyFrom(route).map(([week, n]) => [day(week), String(n)]));
    expect(tables["Alerts raised by rule"]).toEqual([
      ["Rapid movement", "2"],
      ["Structuring", "5"],
      ["Hotlists", "1"],
    ]);
    expect(tables["Alerts closed by outcome"]).toEqual([
      ["False positive", "2"],
      ["True match", "1"],
    ]);
    expect(tables["Alerts closed by time taken"]).toEqual(route.monitoring.time_to_close.map((c) => [c.label.charAt(0).toUpperCase() + c.label.slice(1), String(c.value)]));
    const text = words(res.text);
    expect(text).toContain("Counted for you: an alert concerning anything you cannot see is in no figure here.");
    expect(text).toContain(`${OFFICIAL_TOTAL} alerts raised in the last 12 weeks`);
    expect(text).toContain("1 match");
    expect(text).toContain("5 alerts open");
    expect(headingsOf(res.text)).toEqual(["Alert monitoring", "Alerts", "Raised each week", "Raised by rule", "Closed by outcome", "Time to close", "Hotlist matches", "Team view", "Held rows"]);
  });

  it("AM1: the period is the week of a link, and a value that is not a period is the default", async () => {
    const v = await visitAs(readerOf({}));
    const four = await v.get(`/reports?case=${CASE}&weeks=4`);
    expect(words(four.text)).toContain("in the last 4 weeks");
    const odd = await v.get(`/reports?case=${CASE}&weeks=7`);
    expect(words(odd.text)).toContain("in the last 12 weeks");
    const junk = await v.get(`/reports?case=${CASE}&weeks=abc`);
    expect(words(junk.text)).toContain("in the last 12 weeks");
    expect(reportCalls(v.conduit)).toEqual([
      `GET /v1/investigations/${CASE}/reports?weeks=4`,
      `GET /v1/investigations/${CASE}/reports?weeks=12`,
      `GET /v1/investigations/${CASE}/reports?weeks=12`,
    ]);
  });

  it("AM2: draws each figure as a plain SVG bar chart, each bar a rect with a class, a text alternative, and the table of the same figures after it", async () => {
    const v = await visitAs(readerOf({}));
    const html = (await v.get(`/reports?case=${CASE}`)).text;
    expect(chartProblems(html)).toEqual([]);
    const charts = chartsIn(mainOf(html));
    expect(charts.length).toBe(4);
    for (const chart of charts) {
      expect(chart.bars.every((b) => b.cls === "figure-chart__bar")).toBe(true);
      expect(chart.svg).toMatch(/\sclass="figure-chart"/);
      expect(chart.svg).not.toMatch(/\sstyle=/);
    }
    // The first chart's own bars: the weeks of the table, the larger week the widest.
    const first = charts[0] as Chart;
    expect(first.labels).toEqual([day("2026-11-09"), day("2026-11-16")]);
    expect(first.values).toEqual(["4", "4"]);
    expect(first.bars.map((b) => b.width)).toEqual([WIDEST, WIDEST]);
    expect(first.title).toBe("Bar chart: alerts raised each week");
    // No library, no script, no style and no outside address in the drawing.
    expect(mainOf(html)).not.toMatch(/<script|<style|\sstyle=|<foreignObject|<image|<use|\son[a-z]+=/i);
  });

  it("AM3: shows only the reader's own counts (test_the_alert_monitoring_page_shows_only_the_readers_own_counts)", async () => {
    // The leak test's worlds in miniature: one case, two readers of different clearance, and seven alerts that only the secret one may see.
    const official = readerOf({ id: "reader-official", clearance: "OFFICIAL" });
    const secret = readerOf({ id: "reader-secret", clearance: "SECRET" });
    const asOfficial = await visitAs(official, [secret]);
    const asSecret = await visitOn(asOfficial.conduit, secret);
    const seenByOfficial = (await asOfficial.get(`/reports?case=${CASE}`)).text;
    const seenBySecret = (await asSecret.get(`/reports?case=${CASE}`)).text;
    // Different readers, different counts, each the route's own for that reader.
    expect(words(seenByOfficial)).toContain(`${OFFICIAL_TOTAL} alerts raised`);
    expect(words(seenBySecret)).toContain(`${SECRET_TOTAL} alerts raised`);
    expect(leakProblems(seenByOfficial, ["Circular flow", String(SECRET_TOTAL)])).toEqual([]);
    expect(leakProblems(seenBySecret, ["Circular flow"])).toEqual(["the page shows \"Circular flow\""]);
    // Each page was asked for with its own reader's bearer, never a service identity or a token shared between the two.
    const tokens = asOfficial.conduit.calls.map((c) => c.authorization);
    expect(tokens).toEqual([`Bearer ${official.token}`, `Bearer ${secret.token}`]);
    // The page adds nothing of its own: every table is the route's answer for that reader.
    expect(figuresOnPage(seenByOfficial)["Alerts raised each week"]).toEqual(weeklyFrom(await routeSays(asOfficial.conduit, official.token, CASE)).map(([w, n]) => [day(w), String(n)]));
    expect(figuresOnPage(seenBySecret)["Alerts raised each week"]).toEqual(weeklyFrom(await routeSays(asOfficial.conduit, secret.token, CASE)).map(([w, n]) => [day(w), String(n)]));
    // A figure's chart carries nothing the table does not: the hidden typology is in no chart, label or description of the official page.
    expect(seenByOfficial.toLowerCase()).not.toContain("circular");
  });

  it("AM3: the held rows are drawn only when the route sends them, which it does for Editors and above", async () => {
    const editor = readerOf({ id: "editor", cases: { [CASE]: "editor" } });
    const viewer = readerOf({ id: "viewer", cases: { [CASE]: "viewer" } });
    const asEditor = await visitAs(editor, [viewer]);
    const asViewer = await visitOn(asEditor.conduit, viewer);
    const held = figuresOnPage((await asEditor.get(`/reports?case=${CASE}`)).text)["Held rows by what became of them"];
    expect(held).toEqual([
      ["Held", "2"],
      ["Released", "5"],
      ["Rejected", "1"],
    ]);
    const viewersPage = (await asViewer.get(`/reports?case=${CASE}`)).text;
    expect(words(viewersPage)).not.toContain("Held rows");
    expect(Object.keys(figuresOnPage(viewersPage))).not.toContain("Held rows by what became of them");
    expect(headingsOf(viewersPage)).not.toContain("Held rows");
  });

  it("AM4: a report past its bound is said in words with its numbers and the way out, and draws no figure (rule 2)", async () => {
    const secret = readerOf({ id: "reader-secret", clearance: "SECRET" });
    const official = readerOf({ id: "reader-official", clearance: "OFFICIAL" });
    const v = await visitAs(secret, [official]);
    v.conduit.bound = 10;
    const res = await v.get(`/reports?case=${CASE}`);
    expect(res.status).toBe(409);
    const text = words(res.text);
    expect(text).toContain("This report would count 15 alerts, past its limit of 10. Choose a shorter period.");
    expect(mainOf(res.text)).not.toMatch(/<svg|<table/);
    expect(text).not.toContain("Raised each week");
    expect(text).not.toContain("alerts open");
    // The way out is a link to each shorter period, and no other.
    const links = [...mainOf(res.text).matchAll(/<a\b([^>]*)>([^<]*)<\/a>/g)].map((m) => [attr(m[1] as string, "href"), m[2]]).filter(([href]) => String(href).startsWith("/reports"));
    expect(links).toEqual([[`/reports?case=${CASE}&weeks=4`, "Last 4 weeks"]]);
    // The bound is counted from what the reader sees: the official reader, under it, is answered with figures.
    const under = await visitOn(v.conduit, official);
    const figures = await under.get(`/reports?case=${CASE}`);
    expect(figures.status).toBe(200);
    expect(words(figures.text)).toContain(`${OFFICIAL_TOTAL} alerts raised`);
  });

  it("AM4: at the shortest period it says there is none shorter, and the customers' bound is said as customers", async () => {
    const secret = readerOf({ clearance: "SECRET" });
    const v = await visitAs(secret);
    v.conduit.bound = 10;
    const shortest = await v.get(`/reports?case=${CASE}&weeks=4`);
    expect(shortest.status).toBe(409);
    expect(words(shortest.text)).toContain("This is the shortest period.");
    v.conduit.bound = 1000;
    // The customers' bound does not move with the period (the route counts every verifying document the reader can see): the fake answers
    // it for every period, as the route does, so a link to a shorter period would answer the same.
    v.conduit.customersOver = { cap: 100, wouldBe: 120 };
    for (const query of [`case=${CASE}`, `case=${CASE}&weeks=4`]) {
      const customers = await v.get(`/reports?${query}`);
      expect(customers.status).toBe(409);
      const said = words(customers.text);
      expect(said).toContain("This report would count 120 customers, past its limit of 100.");
      // No way out that cannot work: no link to a period, and no "shorter period" said as one.
      const links = [...mainOf(customers.text).matchAll(/<a\b([^>]*)>([^<]*)<\/a>/g)].map((m) => attr(m[1] as string, "href")).filter((href) => String(href).startsWith("/reports"));
      expect(links).toEqual([]);
      expect(said).not.toContain("Choose a shorter period");
      expect(said).not.toContain("This is the shortest period");
      expect(said).toContain("A shorter period does not change this limit.");
      expect(mainOf(customers.text)).not.toMatch(/<svg|<table/);
    }
  });

  it("AM5: a case with no alerts in the period says so in words and draws no chart", async () => {
    // A Viewer: the route sends no held rows, so nothing at all is left to draw.
    const v = await visitAs(readerOf({ cases: { [EMPTY_CASE]: "viewer" } }));
    const res = await v.get(`/reports?case=${EMPTY_CASE}`);
    expect(res.status).toBe(200);
    const text = words(res.text);
    expect(text).toContain("0 alerts raised in the last 12 weeks");
    expect(text).toContain("No alerts were raised in this period.");
    expect(mainOf(res.text)).not.toMatch(/<svg|<table/);
    expect(structureProblems(res.text)).toEqual([]);
  });

  it("AM5: an Editor's case with no alerts says so and still draws the held rows the route sent, and no chart", async () => {
    // The route sends the held rows to Editors whatever the period holds (`app.py` `_case_report`): the page does not hide them.
    const v = await visitAs(readerOf({}));
    const res = await v.get(`/reports?case=${EMPTY_CASE}`);
    expect(words(res.text)).toContain("No alerts were raised in this period.");
    expect(figuresOnPage(res.text)).toEqual({
      "Held rows by what became of them": [
        ["Held", "2"],
        ["Released", "5"],
        ["Rejected", "1"],
      ],
    });
    expect(mainOf(res.text)).not.toMatch(/<svg/);
  });

  it("AM5: a period with nothing raised in it still draws what the route sent of closures, the team and held rows (a round-4 finding)", async () => {
    // The real route counts a closure by when it was decided and the team rows over every alert the reader may see, not by when the
    // alert was raised (`reports.py` `_monitoring_figures`, `_panel_figures`): so `raised_by_rule` is empty here while the rest is not.
    const viewer = readerOf({ id: "viewer", cases: { [CASE]: "viewer" } });
    const v = await visitAs(readerOf({}), [viewer]);
    const old = (over: Partial<WorldAlert>): WorldAlert => ({ week: "2026-01-05", label: "typology", typology: "structuring", needs: "OFFICIAL", ...over });
    v.conduit.world.set(CASE, [
      old({ closedAs: "true_positive", closedWeek: "2026-11-16", tookBand: "over 30 days" }),
      old({ closedAs: "false_positive", closedWeek: "2026-11-09", tookBand: "over 30 days" }),
      old({}),
      old({ closedAs: "false_positive", closedWeek: "2026-02-02", tookBand: "over 30 days" }),
      old({ label: "hotlists", typology: undefined }),
    ]);
    const route = await routeSays(v.conduit, v.token, CASE);
    expect(route.monitoring.raised_by_rule, "the fixture models a period with nothing raised in it").toEqual([]);
    expect(route.monitoring.closed_by_outcome.length).toBeGreaterThan(0);
    const html = (await v.get(`/reports?case=${CASE}`)).text;
    const text = words(html);
    expect(text).toContain("0 alerts raised in the last 12 weeks");
    expect(text).toContain("No alerts were raised in this period.");
    const tables = figuresOnPage(html);
    expect(Object.keys(tables)).not.toContain("Alerts raised each week");
    expect(Object.keys(tables)).not.toContain("Alerts raised by rule");
    expect(tables["Alerts closed by outcome"]).toEqual([
      ["False positive", "1"],
      ["True match", "1"],
    ]);
    expect(tables["Alerts closed by time taken"]).toEqual([
      ["Under a day", "0"],
      ["1 to 7 days", "0"],
      ["7 to 30 days", "0"],
      ["Over 30 days", "2"],
    ]);
    expect(tables["Team view by rule"]).toEqual([
      // Open and raised in January: older than a week, as the route counts it (`_panel_figures`).
      ["Structuring", "1", "0", "1", "50% of 2"],
      ["Hotlists", "1", "0", "1", "none closed"],
    ]);
    expect(tables["Held rows by what became of them"]).toEqual([
      ["Held", "2"],
      ["Released", "5"],
      ["Rejected", "1"],
    ]);
    // The same of a Viewer: the route sends no held rows, and the closures and the team are still drawn.
    const seen = await visitOn(v.conduit, viewer);
    const asViewer = figuresOnPage((await seen.get(`/reports?case=${CASE}`)).text);
    expect(Object.keys(asViewer)).toContain("Alerts closed by outcome");
    expect(Object.keys(asViewer)).not.toContain("Held rows by what became of them");
    expect(structureProblems(html)).toEqual([]);
  });

  it("AM1: draws the open alerts the route sent, as the count in words and a captioned table of source and age, before the rest", async () => {
    const v = await visitAs(readerOf({}));
    v.conduit.world.set(CASE, [
      { week: "2026-11-23", label: "typology", typology: "structuring", needs: "OFFICIAL" },
      { week: "2026-11-23", label: "typology", typology: "structuring", needs: "OFFICIAL", closedAs: "true_positive", tookBand: "under a day" },
      { week: "2026-11-16", createdOn: "2026-11-20", label: "typology", typology: "structuring", needs: "OFFICIAL" },
      { week: "2026-11-02", label: "monitors", needs: "OFFICIAL" },
      { week: "2026-09-28", label: "monitors", needs: "OFFICIAL" },
      { week: "2026-09-28", label: "monitors", needs: "OFFICIAL" },
      { week: "2026-09-28", label: "hotlists", needs: "OFFICIAL", closedAs: "false_positive", tookBand: "over 30 days" },
    ]);
    const route = await routeSays(v.conduit, v.token, CASE, 52);
    expect(route.monitoring.open_by_source.map((c) => `${c.label}:${c.typology}:${c.age}:${c.count}`)).toEqual([
      "monitors::7 to 30 days:1",
      "monitors::over 30 days:2",
      "typology:structuring:1 to 7 days:1",
      "typology:structuring:under a day:1",
    ]);
    const html = (await v.get(`/reports?case=${CASE}&weeks=52`)).text;
    expect(words(html)).toContain("5 alerts open");
    expect(figuresOnPage(html)["Open alerts by source and age"]).toEqual([
      ["Monitors", "0", "0", "1", "2"],
      ["Structuring", "1", "1", "0", "0"],
    ]);
    expect(openProblems(html)).toEqual([]);
    expect(structureProblems(html)).toEqual([]);
    // Its heading comes first, as the board's does, and the page is no more a chart than the team view is.
    expect(headingsOf(html).slice(0, 2)).toEqual(["Alert monitoring", "Alerts"]);
    expect(scriptsOffProblems(html)).toEqual([]);
  });

  it("AM1: with no alert open the page says 0 alerts open and draws no table of nothing", async () => {
    const v = await visitAs(readerOf({}));
    v.conduit.world.set(CASE, [{ week: "2026-11-09", label: "typology", typology: "structuring", needs: "OFFICIAL", closedAs: "true_positive", tookBand: "1 to 7 days" }]);
    expect((await routeSays(v.conduit, v.token, CASE)).monitoring.open_by_source).toEqual([]);
    const html = (await v.get(`/reports?case=${CASE}`)).text;
    expect(words(html)).toContain("0 alerts open");
    expect(Object.keys(figuresOnPage(html))).not.toContain("Open alerts by source and age");
    expect(openProblems(html)).toEqual([]);
  });

  it("AM5: a period with nothing raised in it still draws the open alerts the route sent, whatever their age", async () => {
    // The real route counts the open alerts over every alert the reader may see, not those raised in the period (`_panel_figures`).
    const viewer = readerOf({ id: "viewer", cases: { [CASE]: "viewer" } });
    const v = await visitAs(readerOf({}), [viewer]);
    const old = (over: Partial<WorldAlert>): WorldAlert => ({ week: "2026-01-05", label: "typology", typology: "structuring", needs: "OFFICIAL", ...over });
    v.conduit.world.set(CASE, [old({}), old({}), old({ label: "hotlists", typology: undefined }), old({ closedAs: "true_positive", closedWeek: "2026-11-16", tookBand: "over 30 days" })]);
    const route = await routeSays(v.conduit, v.token, CASE);
    expect(route.monitoring.raised_by_rule, "the fixture models a period with nothing raised in it").toEqual([]);
    expect(route.monitoring.open_by_source.length, "and open alerts in it").toBeGreaterThan(0);
    const html = (await v.get(`/reports?case=${CASE}`)).text;
    expect(words(html)).toContain("No alerts were raised in this period.");
    expect(words(html)).toContain("3 alerts open");
    expect(figuresOnPage(html)["Open alerts by source and age"]).toEqual([
      ["Hotlists", "0", "0", "0", "1"],
      ["Structuring", "0", "0", "0", "2"],
    ]);
    expect(openProblems(html)).toEqual([]);
    // A Viewer is sent them too: the route counts them for the reader and holds nothing back for a level.
    const seen = (await (await visitOn(v.conduit, viewer)).get(`/reports?case=${CASE}`)).text;
    expect(words(seen)).toContain("3 alerts open");
  });

  it("AM3: the open alerts are the reader's own: a count of open alerts only a secret reader may see is on no other page", async () => {
    const official = readerOf({ id: "reader-official", clearance: "OFFICIAL" });
    const secret = readerOf({ id: "reader-secret", clearance: "SECRET" });
    const asOfficial = await visitAs(official, [secret]);
    const asSecret = await visitOn(asOfficial.conduit, secret);
    const seenByOfficial = (await asOfficial.get(`/reports?case=${CASE}`)).text;
    const seenBySecret = (await asSecret.get(`/reports?case=${CASE}`)).text;
    expect(words(seenByOfficial)).toContain("5 alerts open");
    expect(words(seenBySecret)).toContain("12 alerts open");
    expect(figuresOnPage(seenBySecret)["Open alerts by source and age"]).toContainEqual(["Circular flow", "0", "0", "7", "0"]);
    expect(figuresOnPage(seenByOfficial)["Open alerts by source and age"]?.map((r) => r[0])).toEqual(["Hotlists", "Rapid movement", "Structuring"]);
    expect(leakProblems(seenByOfficial, ["Circular flow", "12 alerts open"])).toEqual([]);
  });

  it("AM1: the team view's Mine and Older than 7 days are the route's own counts under their own headings, and Mine is the reader's own", async () => {
    // Distinct, non-zero figures in every column, so a page that swapped two columns or put another figure under one is red (round 6, rule 15).
    const reader = readerOf({ id: "reader" });
    const colleague = readerOf({ id: "colleague" });
    const v = await visitAs(reader, [colleague]);
    const mk = (over: Partial<WorldAlert>): WorldAlert => ({ week: "2026-11-23", label: "typology", typology: "structuring", needs: "OFFICIAL", ...over });
    v.conduit.world.set(CASE, [
      mk({}), // no one on it, raised today
      mk({}),
      mk({ week: "2026-11-09" }), // no one on it, older than a week
      mk({ week: "2026-11-16", assignee: "reader" }), // the reader's own, seven days and nine hours old
      mk({ week: "2026-11-02", assignee: "reader" }),
      mk({ week: "2026-10-05", assignee: "colleague" }), // another person's: neither unassigned nor the reader's own
      mk({ week: "2026-10-05", assignee: "colleague" }),
      mk({ week: "2026-10-05", assignee: "colleague" }),
      mk({ week: "2026-11-09", closedAs: "false_positive", closedWeek: "2026-11-16", tookBand: "1 to 7 days", assignee: "reader" }),
    ]);
    const asReader = await v.get(`/reports?case=${CASE}`);
    expect((await routeSays(v.conduit, v.token, CASE)).monitoring).toMatchObject({
      team: [{ label: "typology", typology: "structuring", unassigned: 3, mine: 2, older_than_week: 6, closed: 1, not_of_interest: 1 }],
    });
    const team = tablesOf(asReader.text).find((t) => t.caption === "Team view by rule");
    expect(team?.heads).toEqual(["Rule", "Unassigned", "Mine", "Older than 7 days", "Closed as not of interest"]);
    expect(team?.rows).toEqual([expect.objectContaining({ head: "Structuring", cells: ["3", "2", "6", "100% of 1"] })]);
    // Another reader of the same case is sent their own "Mine": the three alerts on them.
    const asColleague = await visitOn(v.conduit, colleague);
    const theirs = tablesOf((await asColleague.get(`/reports?case=${CASE}`)).text).find((t) => t.caption === "Team view by rule");
    expect(theirs?.rows).toEqual([expect.objectContaining({ head: "Structuring", cells: ["3", "3", "6", "100% of 1"] })]);
  });

  it("AM5: a section with nothing to count says so, and a chart is never drawn with no bar", async () => {
    const v = await visitAs(readerOf({}));
    v.conduit.world.set(CASE, [{ week: "2026-11-09", label: "typology", typology: "structuring", needs: "OFFICIAL" }]);
    const html = (await v.get(`/reports?case=${CASE}`)).text;
    expect(words(html)).toContain("No alerts were closed in this period.");
    expect(chartsIn(mainOf(html)).every((c) => c.bars.length > 0)).toBe(true);
    expect(chartProblems(html)).toEqual([]);
  });

  it("AM5: a period whose alerts are all hotlist or monitor alerts is drawn from the figures the route sent, not said to have none", async () => {
    // The real route's `alerts_total` counts typology alerts only (the fake does the same): here it is 0 while three alerts were raised.
    const v = await visitAs(readerOf({}));
    v.conduit.world.set(CASE, [
      { week: "2026-11-09", label: "hotlists", needs: "OFFICIAL" },
      { week: "2026-11-16", label: "hotlists", needs: "OFFICIAL", closedAs: "true_positive", tookBand: "1 to 7 days" },
      { week: "2026-11-16", label: "monitors", needs: "OFFICIAL" },
    ]);
    const route = await routeSays(v.conduit, v.token, CASE);
    expect(route.alerts_total).toBe(0);
    const html = (await v.get(`/reports?case=${CASE}`)).text;
    const text = words(html);
    expect(text).toContain("3 alerts raised in the last 12 weeks");
    expect(text).not.toContain("No alerts were raised in this period.");
    expect(text).not.toContain("0 alerts raised");
    const tables = figuresOnPage(html);
    expect(tables["Alerts raised each week"]).toEqual([
      [day("2026-11-09"), "1"],
      [day("2026-11-16"), "2"],
    ]);
    expect(tables["Alerts raised by rule"]).toEqual([
      ["Hotlists", "2"],
      ["Monitors", "1"],
    ]);
    expect(tables["Alerts closed by outcome"]).toEqual([["True match", "1"]]);
    expect(text).toContain("2 matches");
    expect(chartProblems(html)).toEqual([]);
  });

  it("AM1: the headline is the sum of the raised-each-week table on the same page, for every kind of alert", async () => {
    const v = await visitAs(readerOf({}));
    const html = (await v.get(`/reports?case=${CASE}`)).text;
    const week = figuresOnPage(html)["Alerts raised each week"] as string[][];
    const sum = week.reduce((n, row) => n + Number((row[1] as string).replace(/,/g, "")), 0);
    expect(words(html)).toContain(`${sum} alerts raised in the last 12 weeks`);
    // The route's own `alerts_total` is the typology alerts alone, so it is one less than that here (the hotlist alert).
    expect((await routeSays(v.conduit, v.token, CASE)).alerts_total).toBe(sum - 1);
  });

  it("AM6: a missing case, no case, a non-viewer and a reader without read_reports are the one page, the same status and the same words", async () => {
    const reader = readerOf({ id: "reader" });
    const noRight = readerOf({ id: "no-right", rights: [] });
    const outsider = readerOf({ id: "outsider", cases: {} });
    const v = await visitAs(reader, [noRight, outsider]);
    const asNoRight = await visitOn(v.conduit, noRight);
    const asOutsider = await visitOn(v.conduit, outsider);
    const missing = await v.get("/reports?case=case-that-is-not-there");
    const none = await v.get("/reports");
    const nonViewer = await asOutsider.get(`/reports?case=${CASE}`);
    const withoutRight = await asNoRight.get(`/reports?case=${CASE}`);
    const withoutRightMissing = await asNoRight.get("/reports?case=case-that-is-not-there");
    const answers = [
      sameFor(missing.text, v.csrf),
      sameFor(none.text, v.csrf),
      sameFor(nonViewer.text, asOutsider.csrf),
      sameFor(withoutRight.text, asNoRight.csrf),
      sameFor(withoutRightMissing.text, asNoRight.csrf),
    ];
    for (const res of [missing, none, nonViewer, withoutRight, withoutRightMissing]) expect(res.status).toBe(404);
    expect(new Set(answers).size).toBe(1);
    expect(words(missing.text)).toContain("This case is not one you can open.");
    // What the Conduit said to each is what the real route says, and the page flattens it: 404 for a case the person holds no level on, 403 for the right.
    expect(asOutsider.conduit.calls.map((c) => c.path)).toContain(`/v1/investigations/${CASE}/reports`);
    // The case asked for is never echoed, and neither is what the Conduit said.
    for (const text of answers) {
      expect(text).not.toContain("case-that-is-not-there");
      expect(text).not.toMatch(/right_required|investigation_not_found|read_reports|Not Found/);
    }
    // No Conduit call for a request that names no case.
    expect(v.conduit.calls.filter((c) => c.authorization === `Bearer ${reader.token}`).map((c) => c.path)).toEqual(["/v1/investigations/case-that-is-not-there/reports"]);
  });

  // ADR-152 invariant I15's second test, by the name the owner's approved correction gives it (the page is the alert monitoring figures,
  // the one a dashboard-viewing reader opens): a reader without `read_reports` is answered exactly as a report that is not there is.
  it("test_the_dashboard_page_answers_a_reader_without_read_reports_as_a_missing_report", async () => {
    const reader = readerOf({ id: "reader" });
    const noRight = readerOf({ id: "no-right", rights: [] });
    const v = await visitAs(reader, [noRight]);
    const asNoRight = await visitOn(v.conduit, noRight);
    // The Conduit refuses the right first (403, naming it) and says a case there is not 404 (the real route's two refusals).
    const missing = await v.get("/reports?case=case-that-is-not-there");
    const withoutRight = await asNoRight.get(`/reports?case=${CASE}`);
    const withoutRightMissing = await asNoRight.get("/reports?case=case-that-is-not-there");
    expect(asNoRight.conduit.calls.filter((c) => c.authorization === `Bearer ${noRight.token}`).map((c) => c.path)).toEqual([
      `/v1/investigations/${CASE}/reports`,
      "/v1/investigations/case-that-is-not-there/reports",
    ]);
    // The same status (404, never 403), and the same words and markup (apart from the session's own token and nonce).
    expect(missing.status).toBe(404);
    for (const res of [withoutRight, withoutRightMissing]) expect(res.status).toBe(404);
    const same = sameFor(missing.text, v.csrf);
    expect(sameFor(withoutRight.text, asNoRight.csrf)).toBe(same);
    expect(sameFor(withoutRightMissing.text, asNoRight.csrf)).toBe(same);
    expect(words(withoutRight.text)).toContain("This case is not one you can open.");
    // Nothing on it tells the two apart: no right named, no Conduit error code, no case echoed, no figure or chart.
    for (const text of [withoutRight.text, withoutRightMissing.text]) {
      expect(text).not.toMatch(/right_required|investigation_not_found|read_reports|reports right|Forbidden|Not Found|[Pp]ermission/);
      expect(text).not.toContain("case-that-is-not-there");
      expect(mainOf(text)).not.toMatch(/<svg|<table/);
    }
  });

  it("AM6: an unsigned request is sent to sign-in and learns nothing of the page", async () => {
    const v = await visitAs(readerOf({}));
    const res = await request(v.app).get(`/reports?case=${CASE}`);
    expect(res.status).toBe(302);
    expect(res.headers["location"]).toBe("/session/sign-in");
    expect(textOf(res.text)).not.toContain("Alert monitoring");
    expect(v.conduit.calls).toEqual([]);
  });

  it("AM7: a Conduit that fails, answers a body that is not figures, or cannot be reached says so and draws no figure", async () => {
    const v = await visitAs(readerOf({}));
    const unreadable = "The figures could not be read just now. Nothing has changed. Try again in a few minutes.";
    v.conduit.failing.add("/reports");
    const failing = await v.get(`/reports?case=${CASE}`);
    expect(failing.status).toBe(502);
    expect(words(failing.text)).toContain(unreadable);
    expect(failing.text).not.toContain("Internal Server Error");
    expect(mainOf(failing.text)).not.toMatch(/<svg|<table/);
    v.conduit.failing.clear();
    for (const body of ["not json at all", JSON.stringify({ alerts_total: 3 }), JSON.stringify({ alerts_total: "3", monitoring: {} }), JSON.stringify({ alerts_total: 3, monitoring: {} }), JSON.stringify([1, 2])]) {
      v.conduit.next = { status: 200, body };
      const odd = await v.get(`/reports?case=${CASE}`);
      expect(odd.status, body).toBe(502);
      expect(words(odd.text)).toContain(unreadable);
      expect(mainOf(odd.text)).not.toMatch(/<svg|<table/);
    }
    // A refused bearer is no figure either, and the word the Conduit used is not shown.
    v.conduit.next = { status: 401, body: JSON.stringify({ detail: "Not authenticated" }) };
    const refused = await v.get(`/reports?case=${CASE}`);
    expect(refused.status).toBe(502);
    expect(refused.text).not.toContain("Not authenticated");
    await v.conduit.stop();
    conduits.splice(conduits.indexOf(v.conduit), 1);
    const gone = await v.get(`/reports?case=${CASE}`);
    expect(gone.status).toBe(502);
    expect(words(gone.text)).toContain(unreadable);
  });

  it("AM8: is complete with scripts off, sends no style, script or handler, and the policy names none; the tab order is the page's own", async () => {
    const v = await visitAs(readerOf({}));
    const res = await v.get(`/reports?case=${CASE}`);
    expect(scriptsOffProblems(res.text)).toEqual([]);
    const policy = String(res.headers["content-security-policy"]);
    expect(policy).not.toContain("unsafe-inline");
    expect(policy).not.toContain("unsafe-eval");
    expect(policy).toMatch(/default-src 'self'/);
    // The stops, in the page's own order: the skip link, the layout's sign-out, the periods but the one drawn, the way back.
    const stops = [...strip(res.text).matchAll(/<(a|button)\b([^>]*)>([\s\S]*?)<\/\1>/g)].map((m) => `${attr(m[2] as string, "href") ?? "button"} ${textOf(m[3] as string)}`);
    expect(stops).toEqual([
      "#main Skip to main content",
      "button Sign out",
      `/reports?case=${CASE}&weeks=4 Last 4 weeks`,
      `/reports?case=${CASE}&weeks=26 Last 26 weeks`,
      `/reports?case=${CASE}&weeks=52 Last 52 weeks`,
      "/ Back to Home",
    ]);
    expect(mainOf(res.text)).toContain('aria-current="page"');
    // The page adds no action beyond links: no form but sign-out, no input, no select.
    expect([...strip(res.text).matchAll(/<form\b/g)].length).toBe(1);
    expect(mainOf(res.text)).not.toMatch(/<(?:form|input|select|textarea|button)\b/);
  });

  it("AM8: answers GET alone: a write with the anti-forgery token is a path nothing serves", async () => {
    const v = await visitAs(readerOf({}));
    for (const method of ["post", "put", "patch", "delete"] as const) {
      const res = await request(v.app)[method](`/reports?case=${CASE}`).set("Cookie", v.cookie).type("form").send({ _csrf: v.csrf });
      expect(res.status, method).toBe(404);
    }
    expect(v.conduit.calls).toEqual([]);
  });

  it("AM9: asks the Conduit for one route and nothing else, as the person, and is in the route list and the page list as the GOV.UK tree's", async () => {
    const official = readerOf({});
    const v = await visitAs(official);
    await v.get(`/reports?case=${CASE}`);
    expect(reportCalls(v.conduit)).toEqual([`GET /v1/investigations/${CASE}/reports?weeks=12`]);
    expect(v.conduit.calls.some((c) => c.path.includes("dashboards"))).toBe(false);
    expect(v.conduit.calls.every((c) => c.authorization === `Bearer ${official.token}`)).toBe(true);
    const page = PAGES.find((p) => p.id === "reports-figures");
    expect(page).toMatchObject({ id: "reports-figures", path: "/reports", methods: ["GET"], trees: ["govuk"] });
    const list = readFileSync(join(PAGES_DIR, "tree-govuk", "routes.yaml"), "utf8");
    expect(list).toMatch(/^ {2}- \/reports$/m);
    // The case's id is encoded as one piece: it cannot change the route the person's token is sent to.
    await v.get(`/reports?case=${encodeURIComponent("x/../../v1/reports/dashboards")}`);
    expect(v.conduit.calls.at(-1)?.path).toBe("/v1/investigations/x%2F..%2F..%2Fv1%2Freports%2Fdashboards/reports");
    expect(v.conduit.calls.some((c) => c.path === "/v1/reports/dashboards")).toBe(false);
  });

  it("AM9: the Default tree has no such page: signed in or not, /reports is a path nothing serves", async () => {
    const v = await visitAs(readerOf({}), [], "default");
    const signedIn = await v.get(`/reports?case=${CASE}`);
    expect(signedIn.status).toBe(404);
    expect(words(signedIn.text)).not.toContain("Alert monitoring");
    expect((await request(v.app).get(`/reports?case=${CASE}`)).status).toBe(404);
    expect(v.conduit.calls).toEqual([]);
  });
});

// ------------------------------------------------------------------------------------------------ a strict reader and a census (AM7, AM1)
//
// The owner's ruling of 25 November 2026 (GR3a's round 7): the page's reading of the report is exactly the figures' shape. A body that
// lacks a field the route always sends is "the figures could not be read", never a zero; and every field of the generated type is either
// drawn by the page or named as left out in spec/08 (`test_govuk_alert_monitoring_scenario.py` holds this list and that paragraph in step).
// The list of cases is made from the generated type's own field list, so a field added to the model is a case with no one writing it.

/** The fields of `ReportFigures` that the page does not draw, by name (a nested one as `Interface.field`): spec/08, scenario AM, "Fields of the report the page leaves out". */
const LEFT_OUT = ["generated_at", "alerts_total", "alerts_by_week", "open_by_age", "outcomes", "kyc", "pole", "drawing"];

interface Field {
  name: string;
  optional: boolean;
  /** The type with every alias spelt out: `LabelledWeekCount[]`, `HeldFigures | null`, `number`, a union of quoted words. */
  type: string;
}

const GENERATED = readFileSync(join(PAGES_DIR, "..", "..", "packages", "schemas", "generated", "ReportFigures.ts"), "utf8");
const ALIASES = new Map([...GENERATED.matchAll(/^export type (\w+) = (.+);$/gm)].map((m) => [m[1] as string, m[2] as string]));
const spelt = (type: string): string =>
  type
    .split(" | ")
    .map((part) => {
      let out = part;
      while (ALIASES.has(out)) out = ALIASES.get(out) as string;
      return out;
    })
    .join(" | ");
const INTERFACES = new Map(
  [...GENERATED.matchAll(/^export interface (\w+) \{\n([\s\S]*?)\n\}/gm)].map((m) => [
    m[1] as string,
    [...(m[2] as string).matchAll(/^ {2}(\w+)(\?)?: ([^;]+);$/gm)].map((f): Field => ({ name: f[1] as string, optional: f[2] === "?", type: spelt(f[3] as string) })),
  ]),
);
const fieldsOf = (iface: string): Field[] => INTERFACES.get(iface) ?? [];

function childOf(type: string): { iface: string; list: boolean } | undefined {
  const found = /^(\w+)(\[\])?$/.exec(type.split(" | ").filter((part) => part !== "null").join(" | "));
  return found && INTERFACES.has(found[1] as string) ? { iface: found[1] as string, list: found[2] !== undefined } : undefined;
}

const keyOf = (iface: string, field: string): string => (iface === "ReportFigures" ? field : `${iface}.${field}`);

interface Spot {
  iface: string;
  field: Field;
  /** Where the holders of the field are in the body: keys, and `*` for each item of a list. */
  at: string[];
}

/** Every field the page reads, by walking the generated type: the fields it leaves out are not walked into. */
function spotsOf(iface = "ReportFigures", at: string[] = []): Spot[] {
  return fieldsOf(iface).flatMap((field): Spot[] => {
    const child = childOf(field.type);
    const here: Spot = { iface, field, at };
    return child && !(iface === "ReportFigures" && LEFT_OUT.includes(field.name)) ? [here, ...spotsOf(child.iface, [...at, field.name, ...(child.list ? ["*"] : [])])] : [here];
  });
}

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

function holdersAt(root: unknown, at: string[]): Record<string, unknown>[] {
  let level: unknown[] = [root];
  for (const key of at) level = level.flatMap((o) => (key === "*" ? (Array.isArray(o) ? o : []) : isObject(o) && key in o ? [o[key]] : []));
  return level.filter(isObject);
}

const clone = (body: unknown): unknown => JSON.parse(JSON.stringify(body));
const pathOf = (spot: Spot): string => ["ReportFigures", ...spot.at, spot.field.name].join(".").replace(/^ReportFigures\./, "");

/** A value to put in a field of the sample so that, if the page draws it, the page changes: another figure, another word, another date. */
function another(value: unknown, field: Field): unknown {
  if (typeof value === "number") return value + 7;
  if (typeof value !== "string") return undefined;
  const words = [...field.type.matchAll(/"([^"]+)"/g)].map((m) => m[1] as string);
  if (words.length > 0) return words.find((w) => w !== value) ?? value;
  if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
    const later = new Date(`${value.slice(0, 10)}T00:00:00Z`);
    later.setUTCDate(later.getUTCDate() + 21);
    return later.toISOString().slice(0, 10) + value.slice(10);
  }
  return `${value}x`;
}

/** A value of a type built from the type alone, for a field the sample leaves empty or null. */
function made(type: string): unknown {
  const child = childOf(type);
  if (child) {
    const one = Object.fromEntries(fieldsOf(child.iface).map((f) => [f.name, made(f.type)]));
    return child.list ? [one] : one;
  }
  const words = [...type.matchAll(/"([^"]+)"/g)].map((m) => m[1] as string);
  if (words.length > 0) return words[0];
  return type === "number" ? 3 : "2026-11-02";
}

describe("the figures the page reads are the figures the route always sends (the owner's ruling of 25 November 2026)", () => {
  const spots = spotsOf();
  const unreadable = "The figures could not be read just now. Nothing has changed. Try again in a few minutes.";

  /** One visit, the route's own answer for it, and a way to have the page draw any body in place of it. */
  async function sample(): Promise<{ body: Record<string, unknown>; page: (body: unknown) => Promise<{ status: number; html: string }> }> {
    const v = await visitAs(readerOf({}));
    const body = (await routeSays(v.conduit, v.token, CASE)) as unknown as Record<string, unknown>;
    const page = async (sent: unknown): Promise<{ status: number; html: string }> => {
      v.conduit.next = { status: 200, body: JSON.stringify(sent) };
      const res = await v.get(`/reports?case=${CASE}`);
      return { status: res.status, html: sameFor(res.text, v.csrf) };
    };
    return { body, page };
  }

  const refused = (answer: { status: number; html: string }): boolean => answer.status === 502 && words(answer.html).includes(unreadable) && !/<svg|<table/.test(mainOf(answer.html));

  it("AM7: the list of fields is the generated type's own, and walks into every list and object the page reads", () => {
    expect(spots.length).toBeGreaterThan(30);
    expect(fieldsOf("ReportFigures").map((f) => f.name)).toEqual(expect.arrayContaining(["period_weeks", "monitoring", "held"]));
    // Every name of the left-out list is a field of the generated type, so a field renamed in the model cannot leave a stale name here.
    for (const key of LEFT_OUT) expect(spots.some((s) => keyOf(s.iface, s.field.name) === key), key).toBe(true);
    // A field the page reads and the type marks optional is still required here: the route sends every field, a default included.
    expect(fieldsOf("ReportFigures").find((f) => f.name === "monitoring")?.optional).toBe(true);
  });

  for (const spot of spots) {
    const key = keyOf(spot.iface, spot.field.name);
    const leftOut = LEFT_OUT.includes(key);
    // What the page reads, or the type itself requires, is required; what neither does is not (a page that refused it would be refusing figures it never draws).
    const required = !leftOut || !spot.field.optional;
    it(`AM7: a body with no ${pathOf(spot)} is ${required ? "not the figures: a page of words with 502 and no figure" : "still the figures: the page does not read it"}`, async () => {
      const { body, page } = await sample();
      const holders = holdersAt(body, spot.at).filter((h) => spot.field.name in h);
      expect(holders.length, `the route's answer for the sample holds no ${pathOf(spot)} to remove`).toBeGreaterThan(0);
      const without = clone(body);
      for (const h of holdersAt(without, spot.at)) delete h[spot.field.name];
      const answer = await page(without);
      if (required) expect(refused(answer), `status ${answer.status}`).toBe(true);
      else expect(answer.status).toBe(200);
    });
  }

  const keys = [...new Set(spots.map((s) => keyOf(s.iface, s.field.name)))].filter((key) => {
    const spot = spots.find((s) => keyOf(s.iface, s.field.name) === key) as Spot;
    return LEFT_OUT.includes(key) || childOf(spot.field.type) === undefined;
  });
  for (const key of keys) {
    const leftOut = LEFT_OUT.includes(key);
    it(`AM1: ${key} is ${leftOut ? "left out by the page (named in spec/08)" : "drawn by the page"}`, async () => {
      const { body, page } = await sample();
      const baseline = await page(body);
      expect(baseline.status).toBe(200);
      const changed = clone(body) as Record<string, unknown>;
      let planted = 0;
      for (const spot of spots.filter((s) => keyOf(s.iface, s.field.name) === key)) {
        for (const h of holdersAt(changed, spot.at)) {
          const value = h[spot.field.name];
          const empty = value === null || (Array.isArray(value) && value.length === 0);
          const next = empty ? made(spot.field.type) : another(value, spot.field);
          if (next !== undefined) {
            h[spot.field.name] = next;
            planted += 1;
          }
        }
      }
      expect(planted, `nothing of ${key} could be changed in the sample`).toBeGreaterThan(0);
      const drawn = (await page(changed)).html !== baseline.html;
      expect(drawn, leftOut ? `${key} is named as left out and the page draws it: take it off the list and out of spec/08` : `${key} is neither drawn by the page nor named as left out in spec/08`).toBe(!leftOut);
    });
  }
});

// ------------------------------------------------------------------------------------------------ the checks can fail (AM11, rule 15)

const headingsOf = (html: string): string[] => [...mainOf(html).matchAll(/<h[1-6]\b[^>]*>([\s\S]*?)<\/h[1-6]>/g)].map((m) => textOf(m[1] as string));

/** Words a page must not show to a reader who may not see them: each one found, in words. */
function leakProblems(html: string, hidden: string[]): string[] {
  return hidden.filter((h) => textOf(mainOf(html)).includes(h)).map((h) => `the page shows ${JSON.stringify(h)}`);
}

describe("each check is red against the real page with one thing changed (AM11)", () => {
  async function realPage(): Promise<string> {
    const v = await visitAs(readerOf({}));
    return (await v.get(`/reports?case=${CASE}`)).text;
  }

  const firstValue = (html: string): string => /<text class="figure-chart__value"[^>]*>([^<]*)<\/text>/.exec(html)?.[0] as string;

  const plants: [string, (html: string) => string, (html: string) => string[], RegExp][] = [
    ["a chart that says 5 where its table says 4", (h) => h.replace(firstValue(h), firstValue(h).replace(/>4</, ">5<")), chartProblems, /the chart says "5" for/],
    ["a bar a third as wide as its figure", (h) => h.replace(`width="${WIDEST}"`, 'width="80"'), chartProblems, /not in proportion/],
    ["a bar with no class", (h) => h.replace('<rect class="figure-chart__bar"', "<rect"), chartProblems, /has no class figure-chart__bar/],
    ["a table row dropped", (h) => h.replace(/<tr><th scope="row">[^<]*<\/th><td>4<\/td><\/tr>/, ""), chartProblems, /bars for/],
    ["a chart with no title", (h) => h.replace(/(<svg\b[^>]*>\s*)<title\b[^>]*>[^<]*<\/title>/, "$1"), chartProblems, /no text alternative/],
    ["a chart that is not an image to a reader", (h) => h.replace(' role="img"', ""), chartProblems, /not role="img"/],
    ["a chart that comes after its table", (h) => h.replace(/(<section\b[^>]*>)([\s\S]*?)(<svg[\s\S]*?<\/svg>)([\s\S]*?)(<table[\s\S]*?<\/table>)/, "$1$2$5$3$4"), chartProblems, /comes after its table/],
    ["an inline style on a bar", (h) => h.replace('<rect class="figure-chart__bar"', '<rect style="fill:#f00" class="figure-chart__bar"'), scriptsOffProblems, /inline style attribute/],
    ["a script in the page", (h) => h.replace("</main>", "<script>run()</script></main>"), scriptsOffProblems, /not a data block/],
    ["a handler on a link", (h) => h.replace("<main", '<main onclick="x()"'), scriptsOffProblems, /event-handler/],
    ["a chart that fetches a font from another address", (h) => h.replace("<svg", '<svg><image href="https://cdn.example/x.svg"/><svg'), scriptsOffProblems, /another origin/],
    ["a table with no caption", (h) => h.replace(/<caption\b[^>]*>[^<]*<\/caption>/, ""), structureProblems, /no caption/],
    ["a column header with no scope", (h) => h.replace('<th scope="col">', "<th>"), structureProblems, /scope="col"/],
    ["a row header with no scope", (h) => h.replace('<th scope="row">', "<th>"), structureProblems, /scope="row"/],
    ["a second heading of the first level", (h) => h.replace("</main>", "<h1>Again</h1></main>"), structureProblems, /exactly one heading of the first level/],
    ["a skipped heading level", (h) => h.replace(/<h2\b/, "<h4"), structureProblems, /skips from level/],
    ["an open alerts count that is not its table", (h) => h.replace(/<tr><th scope="row">Hotlists<\/th><td>0<\/td><td>0<\/td><td>1<\/td>/, '<tr><th scope="row">Hotlists</th><td>0</td><td>0</td><td>4</td>'), openProblems, /adds up to/],
    ["a hidden rule in the official reader's page", (h) => h.replace("</main>", "<p>Circular flow 7</p></main>"), (h) => leakProblems(h, ["Circular flow"]), /Circular flow/],
  ];

  for (const [label, plant, check, expected] of plants) {
    it(`AM11: ${label}`, async () => {
      const html = await realPage();
      expect(check(html), "the check is not clean on the real page, so a plant proves nothing").toEqual([]);
      const planted = plant(html);
      expect(planted, "the plant changed nothing").not.toBe(html);
      expect(check(planted).join("\n")).toMatch(expected);
    });
  }
});
