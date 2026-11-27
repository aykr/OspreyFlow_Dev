/**
 * The reader's cases and one case's page with its brief and its history, read-only, on the GOV.UK tree (slices GR1a and GR1e; ADR-152
 * decisions 1, 4, 5, 6, 7 and 12; FUNCTIONS row `cases-and-views`; scenario CS of `spec/08_ACCEPTANCE_SCENARIOS.md`, written first).
 * `tests/glass_trees/test_govuk_cases_scenario.py` holds the scenario and this file in step: each case's id is a row of the scenario.
 *
 * There is no React-first proof (the React list is a menu and the React brief an editor): the proof is the real service started for the
 * GOV.UK tree, the real page list and a fixture Conduit that refuses what the real routes refuse (`casesConduit.ts`).
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a case missing, added, out of order, a column other than the five, a name that is not a link to its page   -> CS1
 *  - an empty list drawn as a table, or as headings with no rows                                                 -> CS2
 *  - a closed tab's case left out, or not said                                                                    -> CS3
 *  - a fact of the case not drawn, a requirement out of order, a status in other words, an attachment's title    -> CS4
 *  - an empty brief drawn as an empty list                                                                        -> CS5
 *  - no level, another unit, no such case told apart, or told in other words than an unknown path's             -> CS6
 *  - the brief's 403 passed through, or said as "no access"                                                      -> CS7
 *  - the case read twice in one render, the browser's headers sent on, a write from a read, an unsigned read     -> CS8
 *  - a failed read drawn as an empty table or brief, an ended session not said                                   -> CS9
 *  - a missing required field read as empty                                                                       -> CS10
 *  - a field neither drawn nor named as left out, a left-out field that changes the page                         -> CS11
 *  - a form, a control, a skipped heading, a stop out of order                                                    -> CS12
 *  - a script, a handler, an inline style                                                                         -> CS13
 *  - the page in the Default tree, left out of the route list, the shared words written again                    -> CS14
 *  - a step missing, added, out of order, without its time, a brief edit said as restorable, a restore offered  -> CS16
 *  - a label in the page's own words, a label the route cannot send drawn                                       -> CS17
 *  - an empty history drawn as an empty table                                                                    -> CS18
 *  - a size or count of anything in the history                                                                  -> CS19
 *  - a step's identifier on the page                                                                             -> CS20
 *  - the history's refusal passed through, or told apart from a path nothing serves                             -> CS21
 *  - the history read twice in one render, or by the list                                                        -> CS22
 *  - a missing or wrong field of a step read as a default                                                        -> CS23
 *  - a failed history read drawn as an empty history, an ended session not said                                  -> CS24
 *  - a contents link missing, out of order, or to no part                                                        -> CS25
 * Every planted fault is the real page (or the real view, or the real file) with one thing changed, run through the same function that
 * finds nothing in the real one (CS15, rule 15).
 */
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Express } from "express";
import { afterEach, describe, expect, it } from "vitest";
import type * as Real from "@ospreyflow/glass-shared";
import { DOMAIN_PACKS, LEVEL_WORDS, POLE_LABEL, utcStampOf } from "@ospreyflow/glass-shared";

import { createApp } from "../../server/app.js";
import { PAGES } from "../../server/pageList.js";
import type * as Stub from "../../server/types/glassShared.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { CASES_WORDS, CENSUS, NOT_SENT, REQUIRED, caseView, listView } from "../../server/views/casesWords.js";
import { refusalWords } from "../../server/views/studioWords.js";
import { testClock } from "../support/clock.js";
import { cookieFrom, csrfFromPage, request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { bearer, providerFor, textOf } from "../support/studioWorld.js";
import { NOT_FOUND_CASE, SHOWN_LABELS, UNKNOWN_BEARER, briefOf, casesConduit, historyOf, investigationOf, listingOf, rightRefusal } from "./casesConduit.js";
import type { Case, CasesConduit, CasesConduitOptions, Reader } from "./casesConduit.js";

// The compiled service is checked against `server/types/glassShared.d.ts`; this holds each declaration the cases page added to the
// package's own type, so that a shape the package changes and the stub still has as it was fails `npm run typecheck`.
type Conforms<R, S> = R extends S ? true : never;
export const CASES_STUB_CONFORMS_TO_THE_PACKAGE: [
  Conforms<typeof Real.DOMAIN_PACKS, typeof Stub.DOMAIN_PACKS>,
  Conforms<typeof Real.POLE_LABEL, typeof Stub.POLE_LABEL>,
  Conforms<typeof Real.domainLabels, typeof Stub.domainLabels>,
  Conforms<typeof Real.caseLabel, typeof Stub.caseLabel>,
  Conforms<typeof Real.utcStampOf, typeof Stub.utcStampOf>,
] = [true, true, true, true, true];

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CORE = join(PAGES_DIR, "..", "..");
const read = (...parts: string[]): string => readFileSync(join(...parts), "utf8");

const PATH = "/cases";
const NOWHERE = "/nothing-is-served-here";
const pageOf = (id: string): string => `${PATH}?case=${encodeURIComponent(id)}`;

// ------------------------------------------------------------------------------------------------ the world

const conduits: CasesConduit[] = [];
afterEach(async () => {
  while (conduits.length > 0) await conduits.pop()?.stop();
});

const UNIT = "harbour-unit";

/** The cases of the fixture's store, in an order no sort gives: not by raw name either way ("", Wharf, Quay), not by label either way
 * (Untitled, Wharf, Quay), and not by when they were made either way (September, August, November). The real store sends newest first;
 * a page that sorted, on any of these, would show (each is planted at the real view: the slice's report). */
const CASES: Case[] = [
  {
    id: "c-toll",
    name: "",
    created_at: "2026-09-14T07:45:00Z",
    created_by: "acct-casey",
    owning_unit: UNIT,
    domains: ["niem", "stix"],
    datasets: [
      { id: "ds-gate", name: "Gate camera log" },
      { id: "ds-tolls", name: "Toll receipts" },
    ],
    brief: {
      priority: "",
      requirements: [{ id: "r-toll", text: "Which lorries pass the toll twice in an hour?", status: "open", answered_at: null, attachments: [] }],
    },
    history: [{ id: "h-toll", label: "Seeded", created_at: "2026-09-14T08:00:00Z" }],
  },
  {
    id: "c-harbour",
    name: "Wharf watch",
    created_at: "2026-08-01T09:05:00Z",
    created_by: "acct-blake",
    owning_unit: UNIT,
    domains: ["fibo"],
    datasets: [{ id: "ds-quay", name: "Quay ledger" }],
    brief: {
      priority: "Who moves the cargo at night?",
      requirements: [
        {
          id: "r-berth",
          text: "Which vessels berth after dark?",
          status: "answered",
          answered_at: "2026-11-01T10:30:00Z",
          attachments: [
            { kind: "trend", id: "t-berths", title: "Berths after dark" },
            { kind: "assessment", id: "a-hidden", title: "Withheld assessment", readers: ["somebody-else"] },
            { kind: "view", id: "v-quay", title: "Quay view" },
          ],
        },
        { id: "r-sign", text: "Who signs the manifests?", status: "open", answered_at: null, attachments: [{ kind: "pattern", id: "p-sign", title: "Signatures" }] },
      ],
    },
    // Five steps in the store's order (`seq`), one a brief edit and one an old numbered label the route sends as `Changed`. Neither by
    // label (either way) nor newest first is this order, so a page that sorted would show.
    history: [
      { id: "h-seed", label: "Seeded", created_at: "2026-08-01T09:10:00Z" },
      { id: "h-expand", label: "Expanded", created_at: "2026-08-02T11:20:00Z" },
      { id: "h-brief", label: "Edited the brief", created_at: "2026-08-03T08:00:00Z" },
      { id: "h-old", label: "Removed 3 nodes", created_at: "2026-08-04T15:45:00Z" },
      { id: "h-links", label: "Showed links among the view", created_at: "2026-08-05T17:30:00Z" },
    ],
  },
  {
    id: "c-ferry",
    name: "Quay routes",
    created_at: "2026-11-20T16:00:00Z",
    created_by: "acct-alex",
    owning_unit: UNIT,
    domains: [],
    datasets: [],
    brief: { priority: "", requirements: [] },
  },
  // Not the reader's: another unit's (a grant on it does not count), and one of the unit's nobody shared with the reader.
  { id: "c-elsewhere", name: "Elsewhere case", created_at: "2026-10-05T09:00:00Z", created_by: "acct-drew", owning_unit: "other-unit", domains: [], datasets: [], brief: { priority: "Not yours", requirements: [] } },
  { id: "c-unshared", name: "Unshared case", created_at: "2026-10-06T09:00:00Z", created_by: "acct-drew", owning_unit: UNIT, domains: [], datasets: [], brief: { priority: "Not yours", requirements: [] } },
];
const LEVELS: Reader["levels"] = { "c-toll": "editor", "c-harbour": "author", "c-ferry": "viewer", "c-elsewhere": "author" };
const MINE = ["c-toll", "c-harbour", "c-ferry"];

interface World {
  app: Express;
  conduit: CasesConduit;
  reader: Reader;
  cookie: string;
  csrf: string;
}

interface WorldOptions extends Partial<Omit<CasesConduitOptions, "readers">> {
  rights?: string[];
  levels?: Reader["levels"];
  hidden?: string[];
  tree?: "govuk" | "default";
  conduitUrl?: string;
  unknownBearer?: boolean;
}

async function world(options: WorldOptions = {}): Promise<World> {
  const token = bearer();
  const reader: Reader = { token, unit: UNIT, rights: options.rights ?? ["investigate"], levels: options.levels ?? LEVELS, hidden: options.hidden ?? ["c-ferry"] };
  const { rights: _r, levels: _l, hidden: _h, tree: _t, conduitUrl: _c, unknownBearer: _u, ...answers } = options;
  const conduit = await casesConduit({ readers: options.unknownBearer === true ? [] : [reader], cases: options.cases ?? CASES, ...answers });
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
  return { app, conduit, reader, cookie, csrf: csrfFromPage(home.text) };
}

const getAs = (w: World, path: string) => request(w.app).get(path).set("Cookie", w.cookie);
const calls = (c: CasesConduit): string[] => c.calls.map((call) => `${call.method} ${call.url}`);

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

interface ListRow {
  head: string;
  href: string | undefined;
  cells: string[];
}

function tableOf(html: string): { caption: string; columns: string[]; rows: ListRow[] } | undefined {
  const found = /<table\b[^>]*>([\s\S]*?)<\/table>/.exec(mainOf(html));
  if (!found) return undefined;
  const inner = found[1] as string;
  const caption = textOf(/<caption\b[^>]*>([\s\S]*?)<\/caption>/.exec(inner)?.[1] ?? "");
  const head = /<thead\b[^>]*>([\s\S]*?)<\/thead>/.exec(inner)?.[1] ?? "";
  const columns = [...head.matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/g)].map((m) => textOf(m[1] as string));
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
}

/** Every fault in a page's structure, in words: the same function reads the real page and each planted one (CS12). */
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

/** Every thing in a page that needs a script, an inline rule or a tab stop out of order (CS13). */
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

/** Words and identifiers the page must never show: the Conduit's refusals, a right's name, an attachment's title or id, an account id. */
const NEVER = ["investigation_not_found", "right_required", "investigate", "Withheld assessment", "Berths after dark", "Quay view", "Signatures", "t-berths", "v-quay", "p-sign", "a-hidden", "acct-", "ds-quay", "r-berth", UNIT, "not have access", "h-seed", "h-brief", "Removed 3 nodes", "history_step"];
const neverProblems = (html: string): string[] => NEVER.filter((word) => strip(html).includes(word)).map((word) => `the page shows ${JSON.stringify(word)}`);

// ------------------------------------------------------------------------------------------------ what the page should draw

const levelName = (level: string): string => LEVEL_WORDS[level as keyof typeof LEVEL_WORDS].name;
const domainsSaid = (c: Case): string => {
  const held = DOMAIN_PACKS.filter((p) => c.domains.includes(p.name));
  return held.length > 0 ? held.map((p) => p.label).join(", ") : POLE_LABEL;
};
const nameSaid = (c: Case): string => (c.name.trim() !== "" ? c.name : `Untitled case · created ${utcStampOf(c.created_at)}`);

/** Every fault in the list as drawn against what was sent: the same function reads the real page and each planted one (CS1, CS15). */
function listProblems(html: string, sent: Case[], hidden: string[]): string[] {
  const table = tableOf(html);
  if (!table) return ["the list has no table"];
  const found: string[] = [];
  if (table.caption !== CASES_WORDS.caption) found.push(`the caption is ${JSON.stringify(table.caption)}`);
  if (JSON.stringify(table.columns) !== JSON.stringify(CASES_WORDS.columns)) found.push(`the columns are ${JSON.stringify(table.columns)}`);
  if (table.rows.length !== sent.length) found.push(`${table.rows.length} rows were drawn for ${sent.length} cases sent`);
  sent.forEach((c, i) => {
    const row = table.rows[i];
    if (!row) return;
    if (row.head !== nameSaid(c)) found.push(`row ${i} is ${JSON.stringify(row.head)}, not ${JSON.stringify(nameSaid(c))}`);
    if (row.href !== pageOf(c.id)) found.push(`row ${i}'s link is ${JSON.stringify(row.href)}, not ${pageOf(c.id)}`);
    const closed = row.cells[0]?.includes(CASES_WORDS.closed) ?? false;
    if (closed !== hidden.includes(c.id)) found.push(`row ${i} ${closed ? "says" : "does not say"} its tab is closed`);
    const want = [levelName(LEVELS[c.id] as string), domainsSaid(c), c.datasets.length > 0 ? c.datasets.map((d) => d.name).join(" ") : CASES_WORDS.noDatasets, utcStampOf(c.created_at)];
    if (JSON.stringify(row.cells.slice(1)) !== JSON.stringify(want)) found.push(`row ${i}'s cells are ${JSON.stringify(row.cells.slice(1))}, not ${JSON.stringify(want)}`);
  });
  return found;
}

/** The text a case's page must hold, in order, for the case and its brief as this reader may read it (CS4). */
function caseWordsInOrder(c: Case, reader: Reader): string[] {
  const brief = briefOf(c, reader) as { priority: string; requirements: { text: string; status: string; answered_at: string | null; attachments: { kind: string }[] }[] };
  const out = [nameSaid(c), CASES_WORDS.level, levelName(LEVELS[c.id] as string), CASES_WORDS.domains, domainsSaid(c), CASES_WORDS.datasets];
  out.push(...(c.datasets.length > 0 ? c.datasets.map((d) => d.name) : [CASES_WORDS.noDatasets]), CASES_WORDS.made, utcStampOf(c.created_at), CASES_WORDS.brief);
  if (brief.priority === "" && brief.requirements.length === 0) return [...out, CASES_WORDS.noBrief];
  out.push(CASES_WORDS.priority, brief.priority === "" ? CASES_WORDS.noPriority : brief.priority, CASES_WORDS.requirements);
  if (brief.requirements.length === 0) return [...out, CASES_WORDS.noRequirements];
  for (const r of brief.requirements) {
    out.push(r.text, r.status === "answered" ? CASES_WORDS.answered : CASES_WORDS.open);
    if (r.answered_at !== null) out.push(CASES_WORDS.answeredOn(utcStampOf(r.answered_at)));
    for (const a of r.attachments) out.push(CASES_WORDS.kinds[a.kind as keyof typeof CASES_WORDS.kinds]);
  }
  return out;
}

function inOrderProblems(text: string, words: string[]): string[] {
  let at = 0;
  for (const word of words) {
    const next = text.indexOf(word, at);
    if (next === -1) return [`${JSON.stringify(word)} is not on the page after ${JSON.stringify(text.slice(Math.max(0, at - 40), at))}`];
    at = next + word.length;
  }
  return [];
}

/** The Brief part of a case's page: from its heading to the next part's (the History, GR1e). The page's contents are a list of their own,
 * before it, and are not the brief's. A page with no Brief heading is all brief, so a plant that drops the heading is still read. */
function briefPartOf(html: string): string {
  const main = mainOf(html);
  const start = main.search(/<h2\b[^>]*\sid="brief"/);
  const end = main.search(/<h2\b[^>]*\sid="history"/);
  return start === -1 ? main : main.slice(start, end > start ? end : main.length);
}

/** What an empty brief must be (CS5): said in words, with no list and no heading of the brief's parts. */
const emptyBriefProblems = (html: string): string[] => {
  const found: string[] = [];
  if (!mainText(html).includes(CASES_WORDS.noBrief)) found.push("the empty brief is not said in words");
  if (/<ol|<ul/.test(briefPartOf(html))) found.push("the empty brief is drawn as a list");
  if (mainText(html).includes(CASES_WORDS.priority)) found.push("the empty brief is drawn with its parts' headings");
  return found;
};

/** What a failed read of the list must be (CS9): the words, as an alert, and no table or part of one. */
const failedListProblems = (html: string): string[] => {
  const found: string[] = [];
  if (!/<p role="alert">[^<]*could not be read/.test(mainOf(html))) found.push("the failure is not said as an alert");
  if (/<table|<th\b|<caption/.test(mainOf(html))) found.push("a failed read draws a table or part of one");
  return found;
};

/** The calls one render of a case's page must make, and no others (CS8). */
const caseCalls = (id: string): string[] => [
  `GET /v1/investigations/${encodeURIComponent(id)}`,
  `GET /v1/investigations/${encodeURIComponent(id)}/brief`,
  `GET /v1/investigations/${encodeURIComponent(id)}/history`,
  "GET /v1/investigations",
];
const callProblems = (made: string[], want: string[]): string[] => (JSON.stringify(made) === JSON.stringify(want) ? [] : [`the page asked ${JSON.stringify(made)}, not ${JSON.stringify(want)}`]);

// ------------------------------------------------------------------------------------------------ the sources

const SOURCES = ["server/cases.ts", "server/views/casesWords.ts", "tree-govuk/cases.njk", "tree-govuk/new-case.njk"];
const sourcesOfThePage = (): { name: string; text: string }[] => SOURCES.map((name) => ({ name, text: read(PAGES_DIR, name) }));
const withoutComments = (text: string): string => text.replace(/\/\*[\s\S]*?\*\/|\/\/.*$|\{#[\s\S]*?#\}/gm, "");
/** The page does not choose what is drawn: no call in its code removes, cuts, sorts or turns a row round (decision 5). The census's own
 * `NOT_SENT` filter (a list of field names, not of rows) is the one `.filter` the words module holds, and is named. */
const CHOOSING = /\.(?:filter|slice|splice|sort|toSorted|reverse|toReversed|shift|pop)\s*\(|\b(?:continue|break)\s*;|\|\s*(?:sort|reverse|first|last|batch|slice|reject|select|selectattr|rejectattr)\b/;
const choosingProblems = (sources: { name: string; text: string }[]): string[] =>
  sources
    .map((s) => ({ ...s, text: withoutComments(s.text).replace(".filter((field) => !NOT_SENT.includes(field))", "") }))
    .filter((s) => CHOOSING.test(s.text))
    .map((s) => `${s.name} chooses what is drawn: ${CHOOSING.exec(s.text)?.[0] ?? ""}`);
const AMERICAN = /\b(?:color|colors|organization|organizations|center|centers|authorize|authorized|behavior|license|licenses|analyze|favorite|catalog)\b/i;
/** Sentences of the shared package the page must import, never write again. */
const SHARED_SENTENCES = [POLE_LABEL, ...DOMAIN_PACKS.map((p) => p.label), ...Object.values(LEVEL_WORDS).map((l) => l.says), "Untitled case"];

// ------------------------------------------------------------------------------------------------ the bodies, for the census and the reader

const harbour = CASES[1] as Case;
const sampleReader: Reader = { token: "t", unit: UNIT, rights: ["investigate"], levels: LEVELS, hidden: [] };
const listBody = (): Record<string, unknown>[] => MINE.map((id) => listingOf(CASES.find((c) => c.id === id) as Case, sampleReader));
const caseBody = (): Record<string, unknown> => investigationOf(harbour);
const briefBody = (): { priority: string; requirements: Record<string, unknown>[] } => briefOf(harbour, sampleReader) as never;
const historyBody = (): Record<string, unknown>[] => historyOf(harbour);

/** A different valid value for each field of each model: a drawn field must change the page with it, a left-out field must not. */
const OTHER: Record<string, Record<string, unknown>> = {
  InvestigationListing: { id: "c-renamed", name: "Renamed in the list", level: "viewer", created_at: "2025-01-03T04:05:00Z", created_by: "acct-other", domains: ["stix"], tab_hidden: true, datasets: ["Another ledger"], dataset_ids: ["ds-another"] },
  Investigation: { id: "c-other", name: "Renamed case", created_at: "2025-01-03T04:05:00Z", created_by: "acct-other", owning_unit: "another-unit", domains: ["stix"], domains_chosen: true },
  CaseBrief: { priority: "A different priority", requirements: [] },
  BriefRequirement: { id: "r-other", text: "A different requirement", status: "open", answered_at: "2025-01-03T04:05:00Z", attachments: [] },
  BriefAttachment: { id: "t-other", kind: "pattern", title: "A different title" },
  HistoryStepSummary: { id: "h-other", label: "Removed", created_at: "2025-01-03T04:05:00Z", restorable: false },
};

interface Bodies {
  list: unknown;
  case: unknown;
  brief: unknown;
  history: unknown;
}
const bodies = (): Bodies => ({ list: listBody(), case: caseBody(), brief: briefBody(), history: historyBody() });

/** The bodies with one field of one model changed (or removed, `value` undefined): for the listing, harbour's row; for a requirement
 * and an attachment, the first of harbour's brief; for a step, harbour's first. */
function withField(model: string, field: string, value: unknown): Bodies {
  const b = bodies();
  const set = (target: Record<string, unknown>): void => {
    if (value === undefined) delete target[field];
    else target[field] = value;
  };
  const brief = b.brief as { requirements: { attachments: Record<string, unknown>[] }[] } & Record<string, unknown>;
  if (model === "InvestigationListing") set((b.list as Record<string, unknown>[])[1] as Record<string, unknown>);
  if (model === "Investigation") set(b.case as Record<string, unknown>);
  if (model === "CaseBrief") set(brief);
  if (model === "BriefRequirement") set(brief.requirements[0] as never);
  if (model === "BriefAttachment") set(brief.requirements[0]?.attachments[0] as never);
  if (model === "HistoryStepSummary") set((b.history as Record<string, unknown>[])[0] as Record<string, unknown>);
  return b;
}

/** Both pages as the real service draws them from these bodies (the fixture serves them through its real refusals). */
async function drawn(b: Bodies): Promise<{ list: string; case: string; listStatus: number; caseStatus: number }> {
  const w = await world({ list_answer: { status: 200, body: b.list }, case_answer: { status: 200, body: b.case }, brief_answer: { status: 200, body: b.brief }, history_answer: { status: 200, body: b.history } });
  const list = await getAs(w, PATH);
  const one = await getAs(w, pageOf("c-harbour"));
  return { list: mainOf(list.text), case: mainOf(one.text), listStatus: list.status, caseStatus: one.status };
}

type Census = Record<string, { readonly drawn: readonly string[]; readonly left: readonly string[] }>;

/** Every field a census says is drawn that changes nothing, and every field it says is left out that changes a page, when the field's
 * value changes (CS11): the same function reads the real census and each planted one (CS15). */
async function censusProblems(census: Census): Promise<string[]> {
  const found: string[] = [];
  const base = await drawn(bodies());
  if (base.listStatus !== 200 || base.caseStatus !== 200) return [`the pages answered ${base.listStatus} and ${base.caseStatus}`];
  for (const [model, { drawn: drawnFields, left }] of Object.entries(census)) {
    const fields = [...drawnFields, ...left];
    if (JSON.stringify(Object.keys(OTHER[model] ?? {}).sort()) !== JSON.stringify([...fields].sort())) found.push(`the census of ${model} is not the fields the test can change`);
    for (const field of fields) {
      if (NOT_SENT.includes(field)) continue;
      const changed = await drawn(withField(model, field, (OTHER[model] as Record<string, unknown>)[field]));
      const moved = changed.list !== base.list || changed.case !== base.case;
      if (drawnFields.includes(field) && !moved) found.push(`${model}.${field} is drawn but changes nothing`);
      if (!drawnFields.includes(field) && moved) found.push(`${model}.${field} is left out but changes the page`);
    }
  }
  return found;
}

// ------------------------------------------------------------------------------------------------ the cases

describe("the cases page on the GOV.UK tree (scenario CS)", () => {
  it("CS1: the list is a table of the reader's cases in the order sent, each name a link to its page, with level, domains, datasets and when made", async () => {
    const w = await world();
    const res = await getAs(w, PATH);
    expect(res.status).toBe(200);
    const sent = MINE.map((id) => CASES.find((c) => c.id === id) as Case);
    expect(listProblems(res.text, sent, ["c-ferry"])).toEqual([]);
    expect(headings(mainOf(res.text))[0]).toEqual({ level: 1, text: CASES_WORDS.listTitle });
    // Not the other unit's case, though the reader holds a grant on it, and not the unshared one: the Conduit's list, nothing added.
    expect(mainText(res.text)).not.toMatch(/Elsewhere case|Unshared case/);
    expect(neverProblems(res.text)).toEqual([]);
    // A reader holding no right is sent no dataset (the route's rule): each row says none shown, never that the case reads none.
    const unrighted = await world({ rights: [] });
    const rows = tableOf((await getAs(unrighted, PATH)).text)?.rows ?? [];
    expect(rows.map((r) => r.cells[3])).toEqual(["None shown", "None shown", "None shown"]);
    expect(CASES_WORDS.noDatasets).toBe("None shown");
  });

  it("CS2: a reader with no case is told so in one sentence, with no table, caption or column header", async () => {
    const w = await world({ levels: {} });
    const res = await getAs(w, PATH);
    expect(res.status).toBe(200);
    expect(mainText(res.text)).toContain(CASES_WORDS.noCases);
    expect(mainOf(res.text)).not.toMatch(/<table|<caption|<th\b/);
    expect(CASES_WORDS.noCases).toBe("You have no cases to show.");
  });

  it("CS3: a case whose tab the reader closed is listed in its place with the words, and an open tab says nothing", async () => {
    const w = await world({ hidden: ["c-harbour"] });
    const table = tableOf((await getAs(w, PATH)).text);
    expect(table?.rows.map((r) => r.head)).toEqual(MINE.map((id) => nameSaid(CASES.find((c) => c.id === id) as Case)));
    expect(table?.rows.map((r) => r.cells[0]?.includes("You closed this case's tab"))).toEqual([false, true, false]);
  });

  it("CS4: one case's page draws its facts, then the brief in the Conduit's order, statuses in the React brief's words, attachments by kind", async () => {
    const w = await world();
    const res = await getAs(w, pageOf("c-harbour"));
    expect(res.status).toBe(200);
    expect(headings(mainOf(res.text))[0]).toEqual({ level: 1, text: "Wharf watch" });
    expect(inOrderProblems(mainText(res.text), caseWordsInOrder(harbour, w.reader))).toEqual([]);
    // The attachment the reader may not read is not sent, and so not drawn: two kinds under the first requirement, not three.
    expect(mainText(res.text)).not.toContain(CASES_WORDS.kinds.assessment);
    expect(CASES_WORDS.kinds).toEqual({ trend: "A saved trend", pattern: "A saved pattern", assessment: "An assessment", view: "A canvas view" });
    expect([CASES_WORDS.open, CASES_WORDS.answered]).toEqual(["Open", "Answered"]);
    expect(neverProblems(res.text)).toEqual([]);
    const untitled = await getAs(w, pageOf("c-toll"));
    expect(inOrderProblems(mainText(untitled.text), caseWordsInOrder(CASES[0] as Case, w.reader))).toEqual([]);
  });

  it("CS5: an empty brief is said in words, and never drawn as an empty list", async () => {
    const w = await world();
    const ferry = await getAs(w, pageOf("c-ferry"));
    expect(emptyBriefProblems(ferry.text)).toEqual([]);
    expect(mainText(ferry.text)).toContain("This case has no brief yet.");
    expect(briefPartOf(ferry.text)).not.toMatch(/<ol|<ul/);
    expect(mainText(ferry.text)).not.toContain(CASES_WORDS.priority);
    const toll = await getAs(w, pageOf("c-toll"));
    expect(mainText(toll.text)).toContain("No priority information requirement is set.");
    const w2 = await world({ brief_answer: { status: 200, body: { priority: "Only a priority", requirements: [] } } });
    const only = await getAs(w2, pageOf("c-harbour"));
    expect(mainText(only.text)).toContain("No information requirements yet.");
    expect(briefPartOf(only.text)).not.toMatch(/<ol/);
  });

  it("CS6: no level, another unit, no such case, an empty or repeated case: the very page of a path nothing serves, and nothing more is asked", async () => {
    const w = await world();
    const unknown = await getAs(w, NOWHERE);
    expect(unknown.status).toBe(404);
    for (const id of ["c-unshared", "c-elsewhere", "c-no-such-case"]) {
      w.conduit.calls.splice(0);
      const res = await getAs(w, pageOf(id));
      expect(refusalProblems(res, unknown), id).toEqual([]);
      expect(calls(w.conduit), id).toEqual([`GET /v1/investigations/${id}`]);
    }
    for (const query of ["?case=", "?case=c-harbour&case=c-ferry", "?case=c-harbour&case=", "?case=.", "?case=..", "?case=%2E%2E", "?case=c-harbour%2Fbrief", "?case=c-harbour%2Fviews"]) {
      w.conduit.calls.splice(0);
      const res = await getAs(w, `${PATH}${query}`);
      expect(refusalProblems(res, unknown), query).toEqual([]);
      expect(calls(w.conduit), query).toEqual([]);
    }
  });

  it("CS6: a slash in `case` is the same page and asks nothing: the Conduit's server decodes it, so it would reach another route", async () => {
    const w = await world();
    const unknown = await getAs(w, NOWHERE);
    // Written encoded and bare: the service reads both as the same value. Each of the first four is another route of the real Conduit.
    for (const query of ["?case=c-harbour%2Fbrief", "?case=c-harbour/brief", "?case=c-harbour%2Fviews", "?case=..%2Fdatasets", "?case=c-harbour%2F", "?case=%2F"]) {
      w.conduit.calls.splice(0);
      const res = await getAs(w, `${PATH}${query}`);
      expect.soft(calls(w.conduit), query).toEqual([]);
      expect.soft(refusalProblems(res, unknown), query).toEqual([]);
    }
  });

  it("CS6: any other refusal of the case's read (a 403 for a level too low, a 409, a 422) is the same page, and the brief is not asked", async () => {
    for (const status of [403, 409, 422]) {
      const w = await world({ case_answer: { status, body: { detail: "this needs the viewer level on the case" } } });
      const unknown = await getAs(w, NOWHERE);
      w.conduit.calls.splice(0);
      const res = await getAs(w, pageOf("c-harbour"));
      expect(refusalProblems(res, unknown), String(status)).toEqual([]);
      expect(calls(w.conduit), String(status)).toEqual([caseCalls("c-harbour")[0]]);
    }
  });

  it("CS7: the brief's refusal (a 403 for want of the right to investigate, or any 4xx but a 401) is the same 404 page, and the list is not asked", async () => {
    const w = await world({ rights: [] });
    const unknown = await getAs(w, NOWHERE);
    const res = await getAs(w, pageOf("c-harbour"));
    expect(refusalProblems(res, unknown)).toEqual([]);
    expect(calls(w.conduit)).toEqual(caseCalls("c-harbour").slice(0, 2));
    for (const status of [403, 404, 409, 422]) {
      const w2 = await world({ brief_answer: { status, body: rightRefusal("investigate") } });
      const res2 = await getAs(w2, pageOf("c-harbour"));
      expect(refusalProblems(res2, await getAs(w2, NOWHERE)), String(status)).toEqual([]);
    }
  });

  it("CS8: the Conduit is asked as the person, the case exactly once per render, nothing of the browser's, no write, nothing unsigned", async () => {
    const w = await world();
    await getAs(w, PATH).set("Origin", "http://example.invalid").set("Referer", "http://example.invalid/x");
    // The list, then the rights that say whether New case is offered (slice GR1b).
    expect(calls(w.conduit)).toEqual(["GET /v1/investigations", "GET /v1/me/rights"]);
    w.conduit.calls.splice(0);
    await getAs(w, pageOf("c-harbour")).set("Origin", "http://example.invalid");
    expect(callProblems(calls(w.conduit), caseCalls("c-harbour"))).toEqual([]);
    for (const call of w.conduit.calls) {
      expect(call.headers["authorization"]).toBe(`Bearer ${w.reader.token}`);
      for (const header of ["cookie", "origin", "referer", "x-csrf-token", "x-forwarded-for"]) expect(call.headers[header], header).toBeUndefined();
    }
    w.conduit.calls.splice(0);
    const unsigned = await request(w.app).get(pageOf("c-harbour"));
    expect(unsigned.status).toBe(302);
    expect(unsigned.headers["location"]).toBe("/session/sign-in");
    const unknown = await getAs(w, NOWHERE);
    for (const method of ["post", "put", "patch", "delete"] as const) {
      const res = await request(w.app)[method](pageOf("c-harbour")).set("Cookie", w.cookie).set("X-CSRF-Token", w.csrf).type("form").send({ _csrf: w.csrf });
      expect(res.status, method).toBe(unknown.status);
    }
    expect(calls(w.conduit)).toEqual([]);
  });

  it("CS9: a failed read draws nothing of the cases or the brief (502); an ended session says to sign in again (401)", async () => {
    const failures: WorldOptions[] = [
      { list_answer: { status: 500, body: { detail: "boom" } } },
      { list_answer: { status: 200, body: "not json" } },
      { list_no_answer: true },
      { conduitUrl: await closedAddress() },
    ];
    for (const options of failures) {
      const w = await world(options);
      const res = await getAs(w, PATH);
      expect(res.status, JSON.stringify(options)).toBe(502);
      expect(mainOf(res.text)).not.toMatch(/<table|<th\b/);
      expect(mainText(res.text)).toContain(CASES_WORDS.unreadableList);
      expect(failedListProblems(res.text)).toEqual([]);
    }
    const caseFailures: WorldOptions[] = [
      { case_answer: { status: 503, body: { detail: "down" } } },
      { case_no_answer: true },
      { brief_answer: { status: 500, body: { detail: "boom" } } },
      { brief_no_answer: true },
      { list_answer: { status: 502, body: { detail: "boom" } } },
      // The case's own read answered, but the list does not hold it: never drawn without its level.
      { list_answer: { status: 200, body: [] } },
      { conduitUrl: await closedAddress() },
    ];
    for (const options of caseFailures) {
      const w = await world(options);
      const res = await getAs(w, pageOf("c-harbour"));
      expect(res.status, JSON.stringify(options)).toBe(502);
      expect(mainText(res.text)).toContain(CASES_WORDS.unreadableCase);
      expect(mainText(res.text)).not.toContain(CASES_WORDS.priority);
      expect(mainText(res.text)).not.toContain("Wharf watch");
    }
    const ended = refusalWords(401, undefined, "");
    for (const options of [{ unknownBearer: true }, { brief_answer: { status: 401, body: { detail: "Not authenticated" } } }, { list_answer: { status: 401, body: { detail: "Not authenticated" } } }] as WorldOptions[]) {
      const w = await world(options);
      for (const path of [PATH, pageOf("c-harbour")]) {
        const res = await getAs(w, path);
        if (path === PATH && options.brief_answer) continue;
        expect(res.status, `${path} ${JSON.stringify(options)}`).toBe(401);
        expect(mainText(res.text)).toContain(unescape(ended));
      }
    }
  });

  it("CS10: a body missing any field the route's model sends, or of the wrong shape, is the could-not-be-read page, never empty", async () => {
    expect(listView(listBody())).toBeDefined();
    expect(caseView("c-harbour", caseBody(), briefBody(), historyBody(), listBody())).toBeDefined();
    const models = Object.keys(REQUIRED) as (keyof typeof REQUIRED)[];
    expect(models.sort()).toEqual(["BriefAttachment", "BriefRequirement", "CaseBrief", "HistoryStepSummary", "Investigation", "InvestigationListing"]);
    let tried = 0;
    for (const model of models) {
      for (const field of REQUIRED[model]) {
        const b = withField(model, field, undefined);
        const view = model === "InvestigationListing" ? listView(b.list) : caseView("c-harbour", b.case, b.brief, b.history, b.list);
        expect(view, `${model}.${field} removed`).toBeUndefined();
        if (model === "InvestigationListing") expect(caseView("c-harbour", b.case, b.brief, b.history, b.list), `${model}.${field} removed, case page`).toBeUndefined();
        tried += 1;
      }
    }
    expect(tried).toBe(29);
    // Every field of every model of a shape no field of these models has (an object): the type check of each field, one case a field.
    // (Found by planting: with one field's type check taken out, presence alone still passed every case above.)
    for (const model of models) {
      for (const field of REQUIRED[model]) {
        const b = withField(model, field, { wrong: true });
        const view = model === "InvestigationListing" ? listView(b.list) : caseView("c-harbour", b.case, b.brief, b.history, b.list);
        expect(view, `${model}.${field} of the wrong shape`).toBeUndefined();
      }
    }
    // Wrong shapes, one field at a time.
    const wrong: [string, string, unknown][] = [
      ["InvestigationListing", "level", "owner"],
      ["InvestigationListing", "tab_hidden", "yes"],
      ["InvestigationListing", "datasets", [1]],
      ["InvestigationListing", "domains", ["pole"]],
      ["Investigation", "name", null],
      ["Investigation", "domains", "fibo"],
      ["CaseBrief", "requirements", {}],
      ["CaseBrief", "priority", 7],
      ["BriefRequirement", "status", "closed"],
      ["BriefRequirement", "answered_at", 0],
      ["BriefAttachment", "kind", "document"],
      ["InvestigationListing", "created_at", "yesterday"],
      ["Investigation", "created_at", "not a time"],
      ["BriefRequirement", "answered_at", "soon"],
    ];
    for (const [model, field, value] of wrong) {
      const b = withField(model, field, value);
      expect(model === "InvestigationListing" ? listView(b.list) : caseView("c-harbour", b.case, b.brief, b.history, b.list), `${model}.${field} = ${JSON.stringify(value)}`).toBeUndefined();
    }
    for (const top of [null, {}, "x", [null]]) {
      expect(listView(top)).toBeUndefined();
      expect(caseView("c-harbour", top, briefBody(), historyBody(), listBody())).toBeUndefined();
      expect(caseView("c-harbour", caseBody(), top, historyBody(), listBody())).toBeUndefined();
      expect(caseView("c-harbour", caseBody(), briefBody(), top, listBody())).toBeUndefined();
    }
    // And through the service: one missing field of each model is the 502 page.
    for (const [model, field] of [["InvestigationListing", "level"], ["Investigation", "domains"], ["CaseBrief", "priority"], ["BriefRequirement", "status"], ["BriefAttachment", "kind"]] as const) {
      const pages = await drawn(withField(model, field, undefined));
      expect(model === "InvestigationListing" ? pages.listStatus : pages.caseStatus, `${model}.${field}`).toBe(502);
    }
  });

  it("CS11: every field of the six models is drawn or named as left out; a drawn field changes the page and a left-out one does not", async () => {
    expect(await censusProblems(CENSUS)).toEqual([]);
  }, 30_000);

  it("CS12: both pages are whole in structure, read-only, and their stops come in order", async () => {
    const w = await world();
    const list = await getAs(w, PATH);
    const one = await getAs(w, pageOf("c-harbour"));
    expect(structureProblems(list.text)).toEqual([]);
    expect(structureProblems(one.text)).toEqual([]);
    const hrefs = (html: string): (string | undefined)[] => focusable(html).map((s) => s.href ?? s.text);
    expect(hrefs(list.text)).toEqual(["#main", "Sign out", ...MINE.map(pageOf), "/"]);
    expect(hrefs(one.text)).toEqual(["#main", "Sign out", ...CONTENTS, "/cases/boards?case=c-harbour", PATH, "/"]);
    expect(focusable(one.text).map((s) => s.text).slice(2)).toEqual([...CASES_WORDS.contents.map((c) => c.text), CASES_WORDS.boards, CASES_WORDS.toCases, CASES_WORDS.back]);
    expect(headings(mainOf(one.text)).map((h) => h.level)).toEqual([1, 2, 2, 2, 3, 3, 2]);
  });

  it("CS13: with scripts off both pages are whole: no script but the data block, no handler, no inline style", async () => {
    const w = await world();
    for (const path of [PATH, pageOf("c-harbour"), pageOf("c-ferry")]) {
      const res = await getAs(w, path);
      expect(scriptsOffProblems(res.text), path).toEqual([]);
      expect(res.text).toMatch(/<script type="application\/json" id="page-data"[^>]*>\{"page":"cases"\}<\/script>/);
    }
  });

  it("CS14: the GOV.UK tree serves the page and the Default tree does not; the lists name it; its words are its own and British", async () => {
    for (const tree of ["default"] as const) {
      const w = await world({ tree });
      const unknown = await getAs(w, NOWHERE);
      for (const path of [PATH, pageOf("c-harbour")]) {
        const res = await getAs(w, path);
        expect(res.status, path).toBe(404);
        expect(withoutNonce(res.text)).toBe(withoutNonce(unknown.text));
      }
      expect(calls(w.conduit)).toEqual([]);
    }
    const page = PAGES.find((p) => p.path === PATH);
    expect(page?.id).toBe("cases-and-views");
    expect(page?.trees).toEqual(["govuk"]);
    expect(page?.methods).toEqual(["GET", "POST"]);
    expect(read(PAGES_DIR, "tree-govuk", "routes.yaml")).toMatch(/^ {2}- \/cases$/m);
    const sources = sourcesOfThePage();
    for (const s of sources) {
      expect([...withoutComments(s.text).matchAll(new RegExp(AMERICAN.source, "gi"))].map((m) => m[0]), s.name).toEqual([]);
      for (const sentence of SHARED_SENTENCES) expect(s.text.includes(sentence), `${s.name} writes again ${JSON.stringify(sentence)}`).toBe(false);
    }
    expect(choosingProblems(sources)).toEqual([]);
    const build = read(PAGES_DIR, "scripts", "build.mjs");
    expect(build).toContain('join(root, "server", "views", "casesWords.ts")');
  });

  describe("CS15: each check is red against the real page with one thing changed", () => {
    it("CS15: the list's check fails for a case added, a row skipped, the rows sorted, a closed tab left out, headings with no rows", async () => {
      const w = await world();
      const real = (await getAs(w, PATH)).text;
      const sent = MINE.map((id) => CASES.find((c) => c.id === id) as Case);
      expect(listProblems(real, sent, ["c-ferry"])).toEqual([]);
      const rowsOf = (html: string): string[] => [...(/<tbody>([\s\S]*?)<\/tbody>/.exec(html)?.[1] ?? "").matchAll(/<tr>[\s\S]*?<\/tr>/g)].map((m) => m[0]);
      const rows = rowsOf(real);
      expect(rows).toHaveLength(3);
      const withRows = (next: string[]): string => real.replace(rows.join("\n"), next.join("\n"));
      const plants: [string, string][] = [
        // A case of another unit added by the page from a second read: a row of the real page, renamed, put after the others.
        ["a case added from a second read", withRows([...rows, (rows[0] as string).replace(/Untitled case[^<]*/, "Elsewhere case")])],
        ["a row skipped", withRows([rows[0] as string, rows[2] as string])],
        ["the rows sorted by name", withRows([rows[2] as string, rows[1] as string, rows[0] as string])],
        ["a closed tab's row left out", withRows([rows[0] as string, rows[1] as string])],
        ["a closed tab not said", real.replace(CASES_WORDS.closed.replace("'", "&#39;"), "")],
        ["headings with no rows", withRows([])],
      ];
      for (const [label, html] of plants) {
        expect(html, label).not.toBe(real);
        expect(listProblems(html, sent, ["c-ferry"]).length + structureProblems(html).length, label).toBeGreaterThan(0);
      }
    });

    it("CS15: the case page's check fails for a status in other words, a title drawn, an empty brief as an empty list", async () => {
      const w = await world();
      const real = (await getAs(w, pageOf("c-harbour"))).text;
      const want = caseWordsInOrder(harbour, w.reader);
      expect(inOrderProblems(mainText(real), want)).toEqual([]);
      expect(inOrderProblems(mainText(real.replace(">Answered<", ">Done<")), want).length).toBeGreaterThan(0);
      expect(inOrderProblems(mainText(real.replace(">Open<", ">open<")), want).length).toBeGreaterThan(0);
      expect(neverProblems(real.replace(CASES_WORDS.kinds.trend, `${CASES_WORDS.kinds.trend}: Berths after dark`)).length).toBeGreaterThan(0);
      const ferry = (await getAs(w, pageOf("c-ferry"))).text;
      expect(emptyBriefProblems(ferry)).toEqual([]);
      expect(emptyBriefProblems(ferry.replace("<p>This case has no brief yet.</p>", "<ol></ol>"))).not.toEqual([]);
      expect(emptyBriefProblems(ferry.replace("<p>This case has no brief yet.</p>", "<p>This case has no brief yet.</p><h3>Priority information requirement</h3>"))).not.toEqual([]);
    });

    it("CS15: the refusal's check fails for a 'you do not have access' sentence, the 403 passed through, the Conduit's words", async () => {
      const w = await world();
      const unknown = await getAs(w, NOWHERE);
      const refused = await getAs(w, pageOf("c-unshared"));
      expect(refusalProblems(refused, unknown)).toEqual([]);
      expect(refusalProblems({ status: 404, text: refused.text.replace("That page could not be found.", "You do not have access to this case.") }, unknown)).not.toEqual([]);
      expect(refusalProblems({ status: 403, text: refused.text }, unknown)).not.toEqual([]);
      expect(refusalProblems({ status: 404, text: refused.text.replace("</main>", "<p>investigation_not_found</p></main>") }, unknown)).not.toEqual([]);
      expect(neverProblems(refused.text.replace("</main>", "<p>You do not have access</p></main>"))).not.toEqual([]);
    });

    it("CS15: the calls' check fails for the case read twice; the failed-read check for an empty table; the reader for a missing field", async () => {
      expect(callProblems([caseCalls("c-harbour")[0] as string, ...caseCalls("c-harbour")], caseCalls("c-harbour"))).not.toEqual([]);
      const w = await world({ list_answer: { status: 500, body: {} } });
      const failed = (await getAs(w, PATH)).text;
      const emptyTable = failed.replace(CASES_WORDS.unreadableList.replace(/'/g, "&#39;"), `<table><caption>${CASES_WORDS.caption}</caption><thead><tr><th scope="col">Case</th></tr></thead><tbody></tbody></table>`);
      expect(failedListProblems(failed)).toEqual([]);
      expect(failedListProblems(emptyTable)).not.toEqual([]);
      expect(failedListProblems(failed.replace('<p role="alert">', "<p>"))).not.toEqual([]);
      expect(structureProblems(emptyTable)).toContain("a table has no row");
      // A reader that took a missing field as empty: the real view given a default for it draws, where the real one refuses.
      const lenient = (body: unknown): unknown => listView((body as Record<string, unknown>[]).map((row) => ({ datasets: [], ...row })));
      const b = withField("InvestigationListing", "datasets", undefined);
      expect(listView(b.list)).toBeUndefined();
      expect(lenient(b.list)).toBeDefined();
    });

    it("CS15: the census fails for a drawn field that changes nothing, the structure for a control or a link out of order, scripts off for a script", async () => {
      const w = await world();
      const real = (await getAs(w, PATH)).text;
      expect(structureProblems(real.replace("</h1>", '</h1><form method="get" action="/cases"><button>Go</button></form>'))).not.toEqual([]);
      expect(structureProblems(real.replace("<caption", "<caption hidden").replace(/<caption[^>]*>[^<]*<\/caption>/, ""))).not.toEqual([]);
      expect(structureProblems(real.replace('scope="row"', ""))).not.toEqual([]);
      expect(structureProblems(real.replace("</h1>", "</h1><h3>Skipped</h3>"))).not.toEqual([]);
      const hrefs = focusable(real.replace('<a class="skip-link" href="#main">Skip to main content</a>', "")).map((s) => s.href);
      expect(hrefs[0]).not.toBe("#main");
      expect(scriptsOffProblems(real.replace("</main>", '<script src="/x.js"></script></main>'))).not.toEqual([]);
      expect(scriptsOffProblems(real.replace("<table", '<table style="color: red"'))).not.toEqual([]);
      expect(scriptsOffProblems(real.replace("<a ", '<a onclick="x()" '))).not.toEqual([]);
      // The census, planted: a left-out field claimed as drawn (it changes nothing), a drawn field claimed as left out (it changes the
      // page), and an attachment's title claimed as drawn, which the owner's ruling keeps off the page.
      const moved = (model: keyof typeof CENSUS, field: string, to: "drawn" | "left"): Census => {
        const { drawn: d, left: l } = CENSUS[model];
        const without = (list: readonly string[]): string[] => list.filter((f) => f !== field);
        return { ...CENSUS, [model]: to === "drawn" ? { drawn: [...d, field], left: without(l) } : { drawn: without(d), left: [...l, field] } };
      };
      expect(await censusProblems(moved("Investigation", "owning_unit", "drawn"))).toEqual(["Investigation.owning_unit is drawn but changes nothing"]);
      expect(await censusProblems(moved("BriefAttachment", "title", "drawn"))).toEqual(["BriefAttachment.title is drawn but changes nothing"]);
      expect(await censusProblems(moved("BriefRequirement", "status", "left"))).toEqual(["BriefRequirement.status is left out but changes the page"]);
      expect(await censusProblems(moved("InvestigationListing", "tab_hidden", "left"))).toEqual(["InvestigationListing.tab_hidden is left out but changes the page"]);
      // Each census draws both pages once a field of six models (GR1e added the history's): past vitest's 5 s default under load.
    }, 30_000);

    it("CS15: the source checks fail for a filter, a sort or a cut in the page's code, and for a shared sentence written again", () => {
      const sources = sourcesOfThePage();
      expect(choosingProblems(sources)).toEqual([]);
      const planted = (name: string, change: (text: string) => string): { name: string; text: string }[] => sources.map((s) => (s.name === name ? { ...s, text: change(s.text) } : s));
      expect(choosingProblems(planted("server/views/casesWords.ts", (t) => t.replace("for (const row of body", "for (const row of (body as unknown[]).filter(Boolean) as unknown[] ?? body")))).not.toEqual([]);
      expect(choosingProblems(planted("server/views/casesWords.ts", (t) => `${t}\nconst x = [].sort();\n`))).not.toEqual([]);
      expect(choosingProblems(planted("tree-govuk/cases.njk", (t) => t.replace("in view.rows %}", 'in view.rows | sort(attribute="name") %}')))).not.toEqual([]);
      expect(choosingProblems(planted("tree-govuk/cases.njk", (t) => t.replace("in r.attachments %}", 'in r.attachments | reject("odd") %}')))).not.toEqual([]);
      // GR1e: a cap on the real loop that reads the history's steps, and on the template's loop that draws them.
      expect(choosingProblems(planted("server/views/casesWords.ts", (t) => t.replace("for (const step of body as unknown[])", "for (const step of (body as unknown[]).slice(0, 100))")))).not.toEqual([]);
      expect(choosingProblems(planted("tree-govuk/cases.njk", (t) => t.replace("in view.history.rows %}", "in view.history.rows | batch(100) | first %}")))).not.toEqual([]);
      const copied = planted("server/views/casesWords.ts", (t) => `${t}\nexport const POLE = "${POLE_LABEL}";\n`);
      expect(copied.some((s) => SHARED_SENTENCES.some((sentence) => s.text.includes(sentence)))).toBe(true);
    });

    it("CS15: the fixture Conduit refuses what the real routes refuse, in their order", async () => {
      const w = await world({ rights: [] });
      const ask = async (path: string, init: RequestInit = {}): Promise<{ status: number; body: unknown }> => {
        const res = await fetch(`${w.conduit.url}${path}`, init);
        return { status: res.status, body: await res.json() };
      };
      const as = { headers: { Authorization: `Bearer ${w.reader.token}` } };
      expect(await ask("/v1/investigations")).toEqual({ status: 401, body: { detail: "Not authenticated" } });
      expect(await ask("/v1/investigations", { headers: { Authorization: "Bearer someone-else" } })).toEqual({ status: 401, body: { detail: UNKNOWN_BEARER } });
      expect(await ask(`/v1/investigations?access_token=${w.reader.token}`)).toEqual({ status: 401, body: { detail: "Not authenticated" } });
      expect(await ask("/v1/investigations/c-harbour/brief", { method: "POST", ...as })).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
      expect(await ask("/v1/investigations/c-harbour/brief", { method: "PUT" })).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
      // A route the real Conduit serves under a case and the fixture does not model: never a 404 the real router would not give.
      expect((await ask("/v1/investigations/c-harbour/views", as)).status).toBe(500);
      expect(await ask("/v1/investigation", as)).toEqual({ status: 404, body: { detail: "Not Found" } });
      for (const id of ["c-unshared", "c-elsewhere", "c-no-such-case"]) expect(await ask(`/v1/investigations/${id}`, as), id).toEqual({ status: 404, body: NOT_FOUND_CASE });
      // The brief's right is checked before the case's gate, as the route-level dependency runs first.
      expect(await ask("/v1/investigations/c-no-such-case/brief", as)).toEqual({ status: 403, body: rightRefusal("investigate") });
      expect(await ask("/v1/investigations/c-harbour/brief", as)).toEqual({ status: 403, body: rightRefusal("investigate") });
      expect(await ask("/v1/investigations", { method: "POST", ...as })).toEqual({ status: 403, body: rightRefusal("create_case") });
      const w2 = await world({ rights: ["investigate", "share_case"] });
      const as2 = { headers: { Authorization: `Bearer ${w2.reader.token}` } };
      const ask2 = async (path: string, init: RequestInit = {}): Promise<number> => (await fetch(`${w2.conduit.url}${path}`, init)).status;
      expect(await ask2("/v1/investigations/c-ferry", { method: "PATCH", ...as2 })).toBe(403); // a Viewer, and a rename needs Author
      expect(await ask2("/v1/investigations/c-harbour", { method: "PATCH", ...as2 })).toBe(500); // a write that would pass: not modelled
      const brief = (await (await fetch(`${w2.conduit.url}/v1/investigations/c-harbour/brief`, as2)).json()) as { requirements: { attachments: { id: string }[] }[] };
      expect(brief.requirements[0]?.attachments.map((a) => a.id)).toEqual(["t-berths", "v-quay"]);
      // An encoded slash is a slash to the real server's router (measured with uvicorn against the real app's route table): the brief's.
      expect(await (await fetch(`${w2.conduit.url}/v1/investigations/c-harbour%2Fbrief`, as2)).json()).toEqual(brief);
      const listed = (await (await fetch(`${w2.conduit.url}/v1/investigations`, as2)).json()) as { id: string }[];
      expect(listed.map((c) => c.id)).toEqual(MINE);
      // A reader holding no right is sent the list with no dataset in it (`datasets.of_case`'s `reads_dataset_names`).
      const bare = (await (await fetch(w.conduit.url + "/v1/investigations", as)).json()) as { datasets: string[]; dataset_ids: string[] }[];
      expect(bare.map((c) => [c.datasets, c.dataset_ids])).toEqual([[[], []], [[], []], [[], []]]);
      const one = (await (await fetch(`${w2.conduit.url}/v1/investigations/c-harbour`, as2)).json()) as Record<string, unknown>;
      expect("domains_chosen" in one).toBe(false);
    });
  });
});

// ------------------------------------------------------------------------------------------------ the history (GR1e)

/** The case page's contents, in order: its parts' addresses on the page. */
const CONTENTS = ["#about", "#brief", "#history"];
const CONTENTS_TEXT = ["About this case", "Brief", "History"];
const HISTORY_CAPTION = "Changes to this case, in the order the case records them";
const HISTORY_COLUMNS = ["Step", "When", "Restore"];
const CAN = "Can be restored";
const CANNOT = "Cannot be restored";
const NO_HISTORY = "Nothing has changed in this case yet.";

interface SentStep {
  id: string;
  label: string;
  created_at: string;
  restorable: boolean;
}
const sentHistory = (c: Case): SentStep[] => historyOf(c) as unknown as SentStep[];
const STEP_IDS = (CASES.flatMap((c) => c.history ?? []) as { id: string }[]).map((s) => s.id);

/** The History part of a case's page: from its heading to the way back to the cases ("" when it has none). */
function historyPartOf(html: string): string {
  const main = mainOf(html);
  const start = main.search(/<h2\b[^>]*\sid="history"/);
  if (start === -1) return "";
  const end = main.indexOf('<p><a href="/cases">', start);
  return main.slice(start, end === -1 ? main.length : end);
}
const historyTable = (html: string): ReturnType<typeof tableOf> => tableOf(`<main>${historyPartOf(html)}</main>`);

/** What an empty history must be (CS18): said in words, with no table or part of one. */
function emptyHistoryProblems(html: string): string[] {
  const part = historyPartOf(html);
  if (part === "") return ["the case's page has no History part"];
  const found: string[] = [];
  if (!unescape(textOf(part)).includes(NO_HISTORY)) found.push("the empty history is not said in words");
  if (/<table|<caption|<th\b/.test(part)) found.push("the empty history is drawn as a table or part of one");
  return found;
}

/** Every fault in the History part as drawn against what was sent: the same function reads the real page and each planted one (CS16). */
function historyProblems(html: string, sent: SentStep[]): string[] {
  const part = historyPartOf(html);
  if (part === "") return ["the case's page has no History part"];
  if (sent.length === 0) return emptyHistoryProblems(html);
  const found: string[] = [];
  if (!/^<h2\b[^>]*>History<\/h2>/.test(part)) found.push("the History part's heading is not a second-level History");
  const table = historyTable(html);
  if (!table) return [...found, "the History part has no table"];
  if (table.caption !== HISTORY_CAPTION) found.push(`the caption is ${JSON.stringify(table.caption)}`);
  if (JSON.stringify(table.columns) !== JSON.stringify(HISTORY_COLUMNS)) found.push(`the columns are ${JSON.stringify(table.columns)}`);
  if (table.rows.length !== sent.length) found.push(`${table.rows.length} rows were drawn for ${sent.length} steps sent`);
  sent.forEach((s, i) => {
    const row = table.rows[i];
    if (!row) return;
    if (row.head !== s.label) found.push(`step ${i} is ${JSON.stringify(row.head)}, not the label sent, ${JSON.stringify(s.label)}`);
    const want = [utcStampOf(s.created_at), s.restorable ? CAN : CANNOT];
    if (JSON.stringify(row.cells.slice(1)) !== JSON.stringify(want)) found.push(`step ${i}'s cells are ${JSON.stringify(row.cells.slice(1))}, not ${JSON.stringify(want)}`);
  });
  if (/<(form|button|input|select|textarea)\b/.test(part)) found.push("the History part offers a control");
  return found;
}

/** A number in the History part that is not a step's moment (CS19): a size, a count of nodes or edges, a count of steps. */
function countProblems(html: string, sent: SentStep[]): string[] {
  if (historyPartOf(html) === "") return ["the case's page has no History part"];
  let text = unescape(textOf(historyPartOf(html)));
  for (const s of sent) text = text.split(utcStampOf(s.created_at)).join(" ");
  return /\d/.test(text) ? [`the History part says a number that is not a moment: ${JSON.stringify(text.trim())}`] : [];
}

/** A step's identifier anywhere in the page's bytes, comments included (CS20). */
const idProblems = (html: string): string[] => STEP_IDS.filter((id) => html.includes(id)).map((id) => `the page holds the step id ${id}`);

/** The contents (CS25): the stops after the sign-out are the three parts' links, each to an element of the main landmark. */
function contentsProblems(html: string): string[] {
  const stops = focusable(html).slice(2, 5);
  const found: string[] = [];
  if (JSON.stringify(stops.map((s) => s.href)) !== JSON.stringify(CONTENTS)) found.push(`the stops after the sign-out are ${JSON.stringify(stops.map((s) => s.href))}, not the contents`);
  if (JSON.stringify(stops.map((s) => s.text)) !== JSON.stringify(CONTENTS_TEXT)) found.push(`the contents say ${JSON.stringify(stops.map((s) => s.text))}`);
  for (const href of CONTENTS) if (!new RegExp(`\\sid="${href.slice(1)}"`).test(mainOf(html))) found.push(`the contents link ${href} goes to no part of the page`);
  return found;
}

/** What a failed history read must be (CS24): the case's could-not-be-read alert, and nothing of the case, its brief or its history. */
function failedHistoryProblems(html: string): string[] {
  const found: string[] = [];
  if (!mainText(html).includes(CASES_WORDS.unreadableCase) || !/<p role="alert">/.test(mainOf(html))) found.push("the failure is not said as the case's alert");
  for (const word of ["Wharf watch", NO_HISTORY, HISTORY_CAPTION, CASES_WORDS.priority]) if (mainText(html).includes(word)) found.push(`a failed read draws ${JSON.stringify(word)}`);
  return found;
}

describe("the history part of a case's page (scenario CS, slice GR1e)", () => {
  it("CS16: after the brief, a table of every step sent, in the order sent, by its label, when it was made and whether it can be restored", async () => {
    const w = await world();
    const res = await getAs(w, pageOf("c-harbour"));
    expect(res.status).toBe(200);
    expect(historyProblems(res.text, sentHistory(harbour))).toEqual([]);
    const rows = historyTable(res.text)?.rows ?? [];
    expect(rows.map((r) => r.head)).toEqual(["Seeded", "Expanded", "Edited the brief", "Changed", "Showed links among the view"]);
    expect(rows.map((r) => r.cells[2])).toEqual([CAN, CAN, CANNOT, CAN, CAN]);
    const h = headings(mainOf(res.text)).map((x) => x.text);
    expect(h.indexOf("History")).toBeGreaterThan(h.indexOf(CASES_WORDS.brief));
    expect(structureProblems(res.text)).toEqual([]);
    // The page says what `restorable` says, never what it would guess from the label.
    const w2 = await world({
      history_answer: {
        status: 200,
        body: [
          { id: "h-x", label: "Edited the brief", created_at: "2026-08-06T10:00:00Z", restorable: true },
          { id: "h-y", label: "Seeded", created_at: "2026-08-07T10:00:00Z", restorable: false },
        ],
      },
    });
    const told = historyTable((await getAs(w2, pageOf("c-harbour"))).text)?.rows ?? [];
    expect(told.map((r) => r.cells[2])).toEqual([CAN, CANNOT]);
    expect([CASES_WORDS.history, CASES_WORDS.historyCaption, CASES_WORDS.historyColumns, CASES_WORDS.canRestore, CASES_WORDS.cannotRestore]).toEqual(["History", HISTORY_CAPTION, HISTORY_COLUMNS, CAN, CANNOT]);
  });

  it("CS17: each label is drawn as the Conduit sent it; a stored label that is not fixed text is sent and drawn as Changed; one the route cannot send is could not be read", async () => {
    const w = await world();
    const rows = historyTable((await getAs(w, pageOf("c-harbour"))).text)?.rows ?? [];
    expect(rows[3]?.head).toBe("Changed");
    // Every label the route can send, drawn as sent.
    const every = SHOWN_LABELS.map((label, i) => ({ id: `h-${i}`, label, created_at: `2026-08-0${(i % 9) + 1}T10:00:00Z`, restorable: label !== "Edited the brief" }));
    const w2 = await world({ history_answer: { status: 200, body: every } });
    const all = await getAs(w2, pageOf("c-harbour"));
    expect(historyProblems(all.text, every)).toEqual([]);
    for (const label of ["Removed 3 nodes", "Expanded by 4", "", "Branched from Harbour"]) {
      const w3 = await world({ history_answer: { status: 200, body: [{ id: "h-z", label, created_at: "2026-08-06T10:00:00Z", restorable: true }] } });
      const res = await getAs(w3, pageOf("c-harbour"));
      expect(res.status, label).toBe(502);
      expect(failedHistoryProblems(res.text), label).toEqual([]);
    }
  });

  it("CS18: a case with no step says so in the History part, and draws no table there", async () => {
    const w = await world();
    const ferry = await getAs(w, pageOf("c-ferry"));
    expect(ferry.status).toBe(200);
    expect(emptyHistoryProblems(ferry.text)).toEqual([]);
    expect(historyProblems(ferry.text, [])).toEqual([]);
    expect(CASES_WORDS.noHistory).toBe(NO_HISTORY);
    expect(structureProblems(ferry.text)).toEqual([]);
  });

  it("CS19: the History part says no number about a step's contents and no count of steps: its only figures are the moments", async () => {
    const w = await world();
    for (const c of [harbour, CASES[0] as Case, CASES[2] as Case]) {
      const res = await getAs(w, pageOf(c.id));
      expect(countProblems(res.text, sentHistory(c)), c.id).toEqual([]);
    }
    // The stored label that held a count is not on the page in any form.
    expect(mainText((await getAs(w, pageOf("c-harbour"))).text)).not.toMatch(/Removed 3|\b3 nodes/);
  });

  it("CS20: no step's identifier is anywhere on the page, comments and attributes included", async () => {
    const w = await world();
    for (const id of ["c-harbour", "c-toll", "c-ferry"]) {
      const res = await getAs(w, pageOf(id));
      expect(idProblems(res.text), id).toEqual([]);
      expect(neverProblems(res.text), id).toEqual([]);
    }
  });

  it("CS21: a refusal of the history's read (any 4xx but a 401) is the very page of a path nothing serves, and the list is not asked", async () => {
    for (const [status, body] of [[404, NOT_FOUND_CASE], [403, rightRefusal("investigate")], [409, { detail: "x" }], [422, { detail: "x" }]] as const) {
      const w = await world({ history_answer: { status, body } });
      const unknown = await getAs(w, NOWHERE);
      w.conduit.calls.splice(0);
      const res = await getAs(w, pageOf("c-harbour"));
      expect(refusalProblems(res, unknown), String(status)).toEqual([]);
      expect(calls(w.conduit), String(status)).toEqual(caseCalls("c-harbour").slice(0, 3));
    }
    // A reader with no right to investigate is refused at the brief, before the history is asked (the real routes' order).
    const w = await world({ rights: [] });
    await getAs(w, pageOf("c-harbour"));
    expect(calls(w.conduit)).toEqual(caseCalls("c-harbour").slice(0, 2));
  });

  it("CS22: one render of a case's page asks for its history exactly once, and the list page never", async () => {
    const w = await world();
    await getAs(w, pageOf("c-harbour"));
    expect(callProblems(calls(w.conduit), caseCalls("c-harbour"))).toEqual([]);
    expect(calls(w.conduit).filter((c) => c.endsWith("/history"))).toEqual(["GET /v1/investigations/c-harbour/history"]);
    w.conduit.calls.splice(0);
    await getAs(w, PATH);
    // The list, then the rights that say whether New case is offered (slice GR1b): no history.
    expect(calls(w.conduit)).toEqual(["GET /v1/investigations", "GET /v1/me/rights"]);
  });

  it("CS23:a history that is not a list, or a step missing or misshaping any field, is the case's could-not-be-read page, never a default", async () => {
    expect(REQUIRED.HistoryStepSummary.sort()).toEqual(["created_at", "id", "label", "restorable"]);
    for (const field of REQUIRED.HistoryStepSummary) {
      const b = withField("HistoryStepSummary", field, undefined);
      expect(caseView("c-harbour", b.case, b.brief, b.history, b.list), `${field} removed`).toBeUndefined();
    }
    const wrong: [string, unknown][] = [["id", null], ["id", 7], ["label", 7], ["label", null], ["created_at", "soon"], ["created_at", 0], ["restorable", "yes"], ["restorable", null], ["restorable", 1]];
    for (const [field, value] of wrong) {
      const b = withField("HistoryStepSummary", field, value);
      expect(caseView("c-harbour", b.case, b.brief, b.history, b.list), `${field} = ${JSON.stringify(value)}`).toBeUndefined();
    }
    for (const top of [null, {}, "x", [null], [[]], { steps: [] }]) expect(caseView("c-harbour", caseBody(), briefBody(), top, listBody()), JSON.stringify(top)).toBeUndefined();
    // And through the service: a step with no `restorable` (the model's default is true) is never taken as restorable.
    for (const field of ["restorable", "created_at", "label", "id"]) {
      const pages = await drawn(withField("HistoryStepSummary", field, undefined));
      expect(pages.caseStatus, field).toBe(502);
      expect(pages.case).not.toContain(CAN);
    }
  });

  it("CS24: a failed history read is the case's could-not-be-read page (502), never an empty history; an ended session says to sign in again", async () => {
    for (const options of [{ history_answer: { status: 500, body: { detail: "boom" } } }, { history_answer: { status: 503, body: { detail: "down" } } }, { history_answer: { status: 200, body: "not json" } }, { history_no_answer: true }] as WorldOptions[]) {
      const w = await world(options);
      const res = await getAs(w, pageOf("c-harbour"));
      expect(res.status, JSON.stringify(options)).toBe(502);
      expect(failedHistoryProblems(res.text), JSON.stringify(options)).toEqual([]);
      // A refused status asks nothing more; a 200 that is not a list of steps is found by the reader, after the one read of the list.
      const text = options.history_answer?.status === 200;
      expect(calls(w.conduit), JSON.stringify(options)).toEqual(text ? caseCalls("c-harbour") : caseCalls("c-harbour").slice(0, 3));
    }
    const w = await world({ history_answer: { status: 401, body: { detail: "Not authenticated" } } });
    const res = await getAs(w, pageOf("c-harbour"));
    expect(res.status).toBe(401);
    expect(mainText(res.text)).toContain(unescape(refusalWords(401, undefined, "")));
    expect(mainText(res.text)).not.toContain(NO_HISTORY);
  });

  it("CS25: the page's contents link to its three parts, after the sign-out and before the ways back, and the History part holds no stop", async () => {
    const w = await world();
    for (const id of ["c-harbour", "c-ferry"]) {
      const res = await getAs(w, pageOf(id));
      expect(contentsProblems(res.text), id).toEqual([]);
      expect(focusable(`<main>${historyPartOf(res.text)}</main>`), id).toEqual([]);
      expect(scriptsOffProblems(res.text), id).toEqual([]);
    }
    expect(CASES_WORDS.contents.map((c) => [c.href, c.text])).toEqual(CONTENTS.map((href, i) => [href, CONTENTS_TEXT[i]]));
  });

  describe("CS26: each history check is red against the real page with one thing changed", () => {
    it("CS26: the history's checks fail for a brief edit said as restorable, a label in other words, an empty table, a count, an id, a control", async () => {
      const w = await world();
      const real = (await getAs(w, pageOf("c-harbour"))).text;
      const sent = sentHistory(harbour);
      expect(historyProblems(real, sent)).toEqual([]);
      const plants: [string, string, (html: string) => string[]][] = [
        ["a brief edit said as restorable", real.replace(`<td>${CANNOT}</td>`, `<td>${CAN}</td>`), (h) => historyProblems(h, sent)],
        ["a label in the page's own words", real.replace(">Changed<", ">Something changed<"), (h) => historyProblems(h, sent)],
        ["the steps newest first", real.replace(/<tbody>([\s\S]*?)<\/tbody>/, (_m, rows: string) => `<tbody>${rows.split("\n").filter(Boolean).reverse().join("\n")}\n</tbody>`), (h) => historyProblems(h, sent)],
        ["a step's time left out", real.replace(`<td>${utcStampOf(sent[0]?.created_at ?? "")}</td>`, "<td></td>"), (h) => historyProblems(h, sent)],
        ["a step skipped", real.replace(/<tbody>([\s\S]*?)<\/tbody>/, (_m, rows: string) => `<tbody>${rows.split("\n").filter((_r, i) => i !== 2).join("\n")}</tbody>`), (h) => historyProblems(h, sent)],
        ["a step added", real.replace(/<tbody>([\s\S]*?)<\/tbody>/, (_m, rows: string) => `<tbody>${rows}${/<tr>[\s\S]*?<\/tr>/.exec(rows)?.[0] ?? ""}\n</tbody>`), (h) => historyProblems(h, sent)],
        ["the steps cut off at three", real.replace(/<tbody>([\s\S]*?)<\/tbody>/, (_m, rows: string) => `<tbody>${rows.split("\n").slice(0, 4).join("\n")}\n</tbody>`), (h) => historyProblems(h, sent)],
        ["a restore button after the table", real.replace("</table>", '</table><button type="button">Restore the latest</button>'), (h) => historyProblems(h, sent)],
        ["the History part's heading in other words", real.replace('<h2 id="history">History</h2>', '<h2 id="history">Steps</h2>'), (h) => historyProblems(h, sent)],
        ["a count of a step's nodes from another read", real.replace(">Expanded<", ">Expanded (12 nodes)<"), (h) => countProblems(h, sent)],
        ["a count of steps", real.replace(HISTORY_CAPTION, `${HISTORY_CAPTION} (5)`), (h) => countProblems(h, sent)],
        ["a step's identifier printed", real.replace(`<td>${CANNOT}</td>`, `<td data-step="h-brief">${CANNOT}</td>`), idProblems],
        ["a step's identifier in a comment", real.replace("</main>", "<!-- h-seed --></main>"), idProblems],
        ["the History link taken out of the contents", real.replace(/<li><a href="#history">History<\/a><\/li>/, ""), contentsProblems],
        ["the History part without its anchor", real.replace(/<h2 id="history">/, "<h2>"), contentsProblems],
      ];
      for (const [label, html, check] of plants) {
        expect(html, label).not.toBe(real);
        expect(check(html).length, label).toBeGreaterThan(0);
      }
      // Each of these fails for the reason it names, not by another path.
      const only = (label: string, html: string, problem: RegExp): void => {
        const found = historyProblems(html, sent);
        expect(found.length, `${label}: ${JSON.stringify(found)}`).toBe(1);
        expect(found[0], label).toMatch(problem);
      };
      only("a step cut off", real.replace(/<tbody>([\s\S]*?)<\/tbody>/, (_m, rows: string) => `<tbody>${rows.split("\n").slice(0, 5).join("\n")}\n</tbody>`), /4 rows were drawn for 5 steps sent/);
      only("a control after the table", real.replace("</table>", '</table><button type="button">Restore the latest</button>'), /offers a control/);
      only("the heading", real.replace('<h2 id="history">History</h2>', '<h2 id="history">Steps</h2>'), /heading is not a second-level History/);
      const ferry = (await getAs(w, pageOf("c-ferry"))).text;
      expect(emptyHistoryProblems(ferry)).toEqual([]);
      // The empty-brief check reads the Brief part: from its own heading, holding the sentence, and not the contents' list before it.
      expect(briefPartOf(ferry).startsWith('<h2 id="brief">')).toBe(true);
      expect(briefPartOf(ferry)).toContain(CASES_WORDS.noBrief);
      expect(briefPartOf(ferry)).not.toContain(CASES_WORDS.contentsTitle);
      expect(mainOf(ferry)).toMatch(/<ul>/);
      expect(emptyBriefProblems(ferry)).toEqual([]);
      const listInBrief = emptyBriefProblems(ferry.replace(`<p>${CASES_WORDS.noBrief}</p>`, `<p>${CASES_WORDS.noBrief}</p><ul><li>A requirement</li></ul>`));
      expect(listInBrief).toEqual(["the empty brief is drawn as a list"]);
      const emptyTable = `<table class="table"><caption class="caption">${HISTORY_CAPTION}</caption><thead><tr><th scope="col">Step</th></tr></thead><tbody></tbody></table>`;
      expect(emptyHistoryProblems(ferry.replace(`<p>${NO_HISTORY}</p>`, emptyTable))).not.toEqual([]);
    });

    it("CS26: the refusal, the calls, the reader and the failure checks fail for a 403 passed through, a second read, a default, an empty history", async () => {
      const w = await world({ history_answer: { status: 403, body: rightRefusal("investigate") } });
      const unknown = await getAs(w, NOWHERE);
      const refused = await getAs(w, pageOf("c-harbour"));
      expect(refusalProblems(refused, unknown)).toEqual([]);
      expect(refusalProblems({ status: 403, text: refused.text }, unknown)).not.toEqual([]);
      const history = caseCalls("c-harbour")[2] as string;
      expect(callProblems([...caseCalls("c-harbour").slice(0, 3), history, "GET /v1/investigations"], caseCalls("c-harbour"))).not.toEqual([]);
      // A reader that took a missing `restorable` as the model's default: the real view refuses, the lenient one draws.
      const b = withField("HistoryStepSummary", "restorable", undefined);
      const lenient = (h: unknown): unknown => caseView("c-harbour", b.case, b.brief, (h as Record<string, unknown>[]).map((s) => ({ restorable: true, ...s })), b.list);
      expect(caseView("c-harbour", b.case, b.brief, b.history, b.list)).toBeUndefined();
      expect(lenient(b.history)).toBeDefined();
      // A reader that took a label the route cannot send as `Changed`: the real view refuses it, the lenient one draws.
      const odd = withField("HistoryStepSummary", "label", "Removed 3 nodes");
      const relabel = (h: unknown): unknown => caseView("c-harbour", odd.case, odd.brief, (h as Record<string, unknown>[]).map((s) => ({ ...s, label: SHOWN_LABELS.includes(s["label"] as string) ? s["label"] : "Changed" })), odd.list);
      expect(caseView("c-harbour", odd.case, odd.brief, odd.history, odd.list)).toBeUndefined();
      expect(relabel(odd.history)).toBeDefined();
      // A failed read drawn as an empty history: the real empty history's page, given as the failure.
      const w2 = await world({ history_answer: { status: 500, body: {} } });
      const failed = (await getAs(w2, pageOf("c-harbour"))).text;
      expect(failedHistoryProblems(failed)).toEqual([]);
      const ferry = (await getAs(await world(), pageOf("c-ferry"))).text;
      expect(emptyHistoryProblems(ferry)).toEqual([]);
      expect(failedHistoryProblems(ferry)).not.toEqual([]);
      expect(failedHistoryProblems(failed.replace('<p role="alert">', "<p>"))).not.toEqual([]);
    });

    it("CS26: the fixture Conduit refuses what the real history routes refuse, in their order, and sends what they send", async () => {
      const w = await world({ rights: [] });
      const ask = async (url: string, path: string, init: RequestInit = {}): Promise<{ status: number; body: unknown }> => {
        const res = await fetch(`${url}${path}`, init);
        return { status: res.status, body: await res.json() };
      };
      const as = { headers: { Authorization: `Bearer ${w.reader.token}` } };
      const H = "/v1/investigations/c-harbour/history";
      expect(await ask(w.conduit.url, H)).toEqual({ status: 401, body: { detail: "Not authenticated" } });
      expect(await ask(w.conduit.url, H, { method: "POST", ...as })).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
      expect(await ask(w.conduit.url, `${H}/h-seed`, as)).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
      // The right to investigate is the route's, before the case's gate, for the read and the restore.
      expect(await ask(w.conduit.url, "/v1/investigations/c-no-such-case/history", as)).toEqual({ status: 403, body: rightRefusal("investigate") });
      expect(await ask(w.conduit.url, `${H}/h-seed`, { method: "POST", ...as })).toEqual({ status: 403, body: rightRefusal("investigate") });
      const w2 = await world();
      const as2 = { headers: { Authorization: `Bearer ${w2.reader.token}` } };
      for (const id of ["c-unshared", "c-elsewhere", "c-no-such-case"]) expect(await ask(w2.conduit.url, `/v1/investigations/${id}/history`, as2), id).toEqual({ status: 404, body: NOT_FOUND_CASE });
      expect((await ask(w2.conduit.url, "/v1/investigations/c-ferry/history/h-x", { method: "POST", ...as2 })).status).toBe(403); // a Viewer: a restore needs Editor
      expect((await ask(w2.conduit.url, "/v1/investigations/c-toll/history/h-toll", { method: "POST", ...as2 })).status).toBe(500); // an Editor: not modelled
      const sent = (await ask(w2.conduit.url, H, as2)).body as Record<string, unknown>[];
      expect(sent.map((s) => [s["label"], s["restorable"]])).toEqual([["Seeded", true], ["Expanded", true], ["Edited the brief", false], ["Changed", true], ["Showed links among the view", true]]);
      expect(sent.map((s) => Object.keys(s).sort())).toEqual(sent.map(() => ["created_at", "id", "label", "restorable"]));
      expect((await ask(w2.conduit.url, "/v1/investigations/c-ferry/history", as2)).body).toEqual([]);
    });
  });
});
