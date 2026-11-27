/**
 * The alert queue, read-only, as a page of the GOV.UK tree (slice RM1a; ADR-152 decisions 1, 4, 5, 6, 7 and 12; invariants I1, I2, I5, I7,
 * I9, I10 and I15; FUNCTIONS row `alerts-rules-watches`; scenario AQ of `spec/08_ACCEPTANCE_SCENARIOS.md`, written first because none of B12,
 * B13, B14 and B20 says what a person who only reads the queue is shown). `tests/glass_trees/test_govuk_alert_queue_scenario.py` holds the
 * scenario, this file's case titles, the function row, the route list and the page's source in step.
 *
 * The Conduit here is `alertQueueConduit.ts`: a real server on a free port that refuses what the real queue route refuses (no bearer, the
 * right, the rows not offered, a case not held, the query's own checks) and leaves out an alert the reader's clearance does not cover. A page
 * is only as safe as the answer it is given, so each access case is made in both directions: what the Conduit sends is drawn whole, and what
 * it does not send is nowhere on the page.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a row not drawn, drawn out of order, a field the page should not draw (an id, an entity, a citation), a second read   -> AQ1
 *  - a kind, a state, a holder's name or a time worded other than the React queue words it                                 -> AQ2
 *  - the case list drawn wrongly, a queue read when no case was asked for                                                  -> AQ3
 *  - an empty queue drawn as a table, a failed read drawn as an empty queue, a row missing a field accepted                -> AQ4
 *  - a refusal worded or sent differently from a page that is not there, a Conduit word shown, an unsigned request served  -> AQ5
 *  - a header of the browser's sent on, another person's token used                                                        -> AQ6
 *  - an alert the Conduit left out named, hinted at or counted; a row it sent left out; a count the page made up           -> AQ7
 *  - a method but GET answered, a form that is not sign-out, a control that acts, a call that is not a read                -> AQ8
 *  - a script, a handler, an inline style, a tab stop out of order, a table with no caption or scope                       -> AQ9
 *  - a route not in the list, served by the other tree, or a sentence of the page written in its template                  -> AQ10
 * Every planted fault is the real page (or the real Conduit's answer) with one thing changed, run through the same function that finds
 * nothing in the real one (AQ11, rule 15).
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";
import type { Express } from "express";
import { TYPOLOGY_LABELS, typologyLabel } from "@ospreyflow/glass-shared";

import { PAGES } from "../../server/pageList.js";
import { typologyWords } from "../../server/views/alertQueueWords.js";
import { build } from "../support/build.js";
import { request, signIn } from "../support/http.js";
import type { Signed } from "../support/http.js";
import { textOf, providerFor } from "../support/studioWorld.js";
import { aCase, aReader, aRow, queueConduit } from "./alertQueueConduit.js";
import type { Held, QueueConduit, QueuedAlert, Reader } from "./alertQueueConduit.js";

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const read = (...parts: string[]): string => {
  const file = join(PAGES_DIR, ...parts);
  return existsSync(file) ? readFileSync(file, "utf8") : "";
};

// ------------------------------------------------------------------------------------------------ the world

const stops: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (stops.length > 0) await stops.pop()?.();
});

interface Person {
  reader: Reader;
  app: Express;
  signed: Signed;
  logs: string[];
  get(path: string): ReturnType<ReturnType<typeof request>["get"]>;
}

interface World {
  conduit: QueueConduit;
  /** Signs a reader in to a service of their own (their bearer is the one their sessions carry), for a tree. */
  as(reader: Reader, tree?: "govuk" | "default"): Promise<Person>;
}

async function world(readers: Reader[], alerts: Held[], options: { reach?: boolean } = {}): Promise<World> {
  const conduit = await queueConduit({ readers, alerts, ...options });
  stops.push(() => conduit.stop());
  return {
    conduit,
    async as(reader, tree = "govuk") {
      const logs: string[] = [];
      const built = build({
        pages: PAGES,
        tree,
        identityProvider: providerFor(reader.token, `sub-${reader.token}`),
        forward: { conduitUrl: conduit.url, bodyMaxBytes: 1024 * 1024, uploadMaxBytes: 8 * 1024 * 1024, upstreamTimeoutSeconds: 5 },
        log: (message) => logs.push(message),
      });
      const signed = await signIn(built.app);
      const api = request(built.app);
      return { reader, app: built.app, signed, logs, get: (path) => api.get(path).set("Cookie", signed.cookie) };
    },
  };
}

const held = (caseId: string, row: QueuedAlert, needs?: string): Held => ({ caseId, row, ...(needs === undefined ? {} : { needs }) });
const queueUrl = (caseId: string): string => `/alert-queue?case=${encodeURIComponent(caseId)}`;
const queueCalls = (conduit: QueueConduit): string[] => conduit.calls.filter((c) => /alert-queue$/.test(c.path)).map((c) => c.url);

// ------------------------------------------------------------------------------------------------ reading a page

const strip = (html: string): string => html.replace(/<!--[\s\S]*?-->/g, "");
const attr = (tag: string, name: string): string | undefined => new RegExp(`\\s${name}="([^"]*)"`).exec(tag)?.[1];

function mainOf(html: string): string {
  const found = /<main\b[^>]*>([\s\S]*?)<\/main>/.exec(strip(html));
  return found ? (found[1] as string) : "";
}

interface Stop {
  tag: string;
  href: string | undefined;
  text: string;
}

/** Every stop a keyboard has, in document order. */
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
  [...strip(html).matchAll(/<h([1-6])\b[^>]*>([\s\S]*?)<\/h\1>/g)].map((m) => ({ level: Number(m[1]), text: textOf(m[2] as string) }));

/** The cells of the page's one table: its caption, column names and each row's cells as text (the row header first). */
interface Grid {
  caption: string;
  columns: string[];
  rows: string[][];
  rowHeaders: boolean;
}
function gridOf(html: string): Grid | undefined {
  const table = /<table\b[^>]*>([\s\S]*?)<\/table>/.exec(mainOf(html));
  if (!table) return undefined;
  const inner = table[1] as string;
  const body = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/.exec(inner)?.[1] ?? "";
  const rows = [...body.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((r) => [...(r[1] as string).matchAll(/<(?:th|td)\b[^>]*>([\s\S]*?)<\/(?:th|td)>/g)].map((c) => textOf(c[1] as string)));
  return {
    caption: textOf(/<caption\b[^>]*>([\s\S]*?)<\/caption>/.exec(inner)?.[1] ?? ""),
    columns: [...(/<thead\b[^>]*>([\s\S]*?)<\/thead>/.exec(inner)?.[1] ?? "").matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/g)].map((c) => textOf(c[1] as string)),
    rows,
    rowHeaders: [...body.matchAll(/<tr\b[^>]*>\s*<(th|td)\b([^>]*)>/g)].every((r) => r[1] === "th" && attr(r[2] as string, "scope") === "row"),
  };
}

/** Every fault in a page's structure, in words (AQ9; the same function reads the real page and each planted one). */
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
  if (!first || first.href !== `#${mainId}` || !/skip to main content/i.test(first.text)) {
    found.push(`the first stop is not the skip link to the main landmark (it is ${JSON.stringify(first)})`);
  }
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
  return found;
}

/** Everything in a page that needs a script, an inline rule or a tab stop out of order (AQ9). */
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
  for (const l of page.matchAll(/<(?:link|img|iframe|object|embed)\b[^>]*\s(?:href|src|data)="([^"]*)"/g)) {
    if (/^(?:[a-z]+:)?\/\//i.test(l[1] as string)) found.push(`an address on another origin: ${l[1] as string}`);
  }
  // The data block is data: nothing of the queue is in it.
  for (const s of page.matchAll(/<script\b[^>]*type="application\/json"[^>]*>([\s\S]*?)<\/script>/g)) {
    if (!/^\{"page":"alert-queue"\}$/.test((s[1] as string).trim())) found.push(`the data block holds more than the page's name: ${(s[1] as string).trim()}`);
  }
  return found;
}

/** The forms a page has, other than the layout's sign-out (AQ8). */
function formProblems(html: string): string[] {
  const forms = [...strip(html).matchAll(/<form\b([^>]*)>/g)].filter((m) => attr(m[1] as string, "action") !== "/session/sign-out");
  return forms.map((m) => `a form that is not the sign-out:${m[1] as string}`);
}

/** A count the page states of its own (AQ7): a number of alerts, rows, results or cases anywhere but in the rows' own words. */
function countProblems(html: string): string[] {
  const page = strip(html);
  const outsideRows = page.replace(/<tbody\b[\s\S]*?<\/tbody>/g, " ");
  const text = `${textOf(outsideRows)} ${[...outsideRows.matchAll(/\s(?:aria-[a-z]+|data-[a-z-]+|title|alt)="([^"]*)"/g)].map((m) => m[1]).join(" ")}`;
  const found: string[] = [];
  if (/\b\d[\d,]*\s+(?:new\s+)?(?:alerts?|results?|rows?|items?|cases?|matches|entries)\b/i.test(text)) found.push("a number of alerts, rows, results or cases");
  if (/\b(?:showing|total|of|only|hidden|more)\s+\d/i.test(text)) found.push("a total or a number shown 'of'");
  if (/\(\d+\)/.test(text)) found.push("a number in brackets");
  if (/aria-rowcount|data-count|data-total|aria-setsize/i.test(page)) found.push("a count in an attribute");
  return found;
}

/** Where a marker the page must not carry is found in a page, by place (empty when it is nowhere). */
function leakProblems(html: string, markers: string[]): string[] {
  return markers.filter((marker) => html.includes(marker) || html.includes(encodeURIComponent(marker))).map((marker) => `the page carries ${marker}`);
}

const withoutNonce = (html: string): string => html.replace(/nonce="[^"]*"/g, 'nonce="N"');
const sameFor = (html: string, csrf: string): string => withoutNonce(html.split(csrf).join("CSRF"));

/** The headers a Conduit call may carry: the person's bearer, what the call asks for, and what the HTTP client itself adds. */
function headerProblems(headers: Record<string, string | string[] | undefined>, token: string): string[] {
  const found: string[] = [];
  const names = Object.keys(headers).map((n) => n.toLowerCase());
  if (headers["authorization"] !== `Bearer ${token}`) found.push("the call does not carry the person's own bearer");
  for (const bad of ["cookie", "x-csrf-token", "x-forwarded-proto", "x-forwarded-for", "x-forwarded-host", "referer", "origin", "x-probe", "forwarded", "x-real-ip"]) {
    if (names.includes(bad)) found.push(`the call carries ${bad}`);
  }
  return found;
}

const NOWHERE = "/nothing-is-served-here";

// ------------------------------------------------------------------------------------------------ the table

const COLUMNS = ["Alert", "Kind", "State", "When", "Case"];
const MARKER_FIELDS = (r: QueuedAlert): string[] => [
  r.alert.id,
  r.alert.rule_id,
  r.alert.owner_id,
  ...(r.alert.referent_node_ids ?? []),
  r.alert.dataset_id ?? "",
  r.alert.words ?? "",
  ...(r.alert.edge_ids ?? []),
  ...(r.alert.event_ids ?? []),
  r.alert.alert_node_id ?? "",
  ...(r.alert.citations ?? []).flatMap((c) => [c.words, ...(c.node_ids ?? [])]),
];

describe("the alert queue page (the govuk tree)", () => {
  it("AQ1: reads the case's queue once, as the person, and draws one row for each alert the Conduit sent, in the order sent, and nothing else of the alert", async () => {
    const mine = aCase({ name: "Wing review" });
    const reader = aReader({ cases: [mine] });
    const rows = [
      aRow({ summary: "Payments just under the limit from account A" }),
      aRow({ summary: "A hotlisted number appears in a new seizure record", row: { kind: "hotlist", severity: "high" } }),
      aRow({ summary: "Third finding, raised last", alert: { created_at: "2026-11-20T07:05:00Z" } }),
    ];
    const w = await world([reader], rows.map((r) => held(mine.id, r)));
    const p = await w.as(reader);
    const res = await p.get(queueUrl(mine.id));
    expect(res.status).toBe(200);
    expect(res.type).toMatch(/html/);
    const grid = gridOf(res.text);
    expect(grid).toBeDefined();
    expect(grid?.columns).toEqual(COLUMNS);
    expect(grid?.rowHeaders).toBe(true);
    expect(grid?.caption).toBe("Open, claimed and closing alerts in Wing review");
    expect(grid?.rows.map((r) => r[0])).toEqual(rows.map((r) => r.summary));
    expect(grid?.rows.every((r) => r.length === COLUMNS.length && r[4] === "Wing review")).toBe(true);
    // Nothing an alert rests on, and no id: every field the page does not draw is a marker, and none is in the page.
    expect(leakProblems(res.text, rows.flatMap(MARKER_FIELDS))).toEqual([]);
    // One read of the queue, with no filter, and one of the case list for the case's name: nothing else, and never a write.
    expect(queueCalls(w.conduit)).toEqual([`/v1/investigations/${mine.id}/alert-queue`]);
    expect(w.conduit.calls.map((c) => `${c.method} ${c.path}`).sort()).toEqual([`GET /v1/investigations`, `GET /v1/investigations/${mine.id}/alert-queue`]);
    const heading = headings(mainOf(res.text));
    expect(heading[0]).toEqual({ level: 1, text: "Alert queue" });
  });

  it("AQ1: a field the page does not draw changes nothing on it (the census of the row's own fields)", async () => {
    const mine = aCase();
    const reader = aReader({ cases: [mine] });
    const whole = aRow({ row: { assignee_name: "Sam Example", kind: "hotlist" }, alert: { status: "claimed" } });
    const DRAWN_ROW = new Set(["alert", "summary", "kind", "suppressed", "assignee_name"]);
    const DRAWN_ALERT = new Set(["status", "created_at"]);
    const readPage = async (row: QueuedAlert): Promise<string> => {
      const w = await world([reader], [held(mine.id, row)]);
      const p = await w.as(reader);
      const res = await p.get(queueUrl(mine.id));
      expect(res.status).toBe(200);
      return sameFor(res.text, p.signed.csrf);
    };
    const real = await readPage(whole);
    for (const key of Object.keys(whole)) {
      if (DRAWN_ROW.has(key)) continue;
      const changed = structuredClone(whole) as Record<string, unknown>;
      changed[key] = key === "summary" ? "x" : null;
      expect(await readPage(changed as unknown as QueuedAlert), `the page draws the row's ${key}`).toBe(real);
    }
    for (const key of Object.keys(whole.alert)) {
      if (DRAWN_ALERT.has(key)) continue;
      const changed = structuredClone(whole);
      (changed.alert as Record<string, unknown>)[key] = key === "id" ? "other-id" : null;
      expect(await readPage(changed), `the page draws the alert's ${key}`).toBe(real);
    }
  });

  it("AQ2: says each kind, each state, a holder's name, a suppressed alert and the time in words, the React queue's words", async () => {
    const mine = aCase({ name: "Wing review" });
    const reader = aReader({ cases: [mine] });
    const cases: [QueuedAlert, string[]][] = [
      [aRow({ row: { kind: "typology" }, alert: { typology: "structuring" } }), ["Structuring", "Open", "24 November 2026, 09:15 UTC"]],
      [aRow({ row: { kind: "typology" }, alert: { typology: "dormant_reactivated" } }), ["Dormant account reactivated", "Open", "24 November 2026, 09:15 UTC"]],
      [aRow({ row: { kind: "typology" }, alert: { typology: null } }), ["Alert", "Open", "24 November 2026, 09:15 UTC"]],
      [aRow({ row: { kind: "typology" }, alert: { typology: "a_typology_nobody_named" } }), ["Alert", "Open", "24 November 2026, 09:15 UTC"]],
      [aRow({ row: { kind: "analyst" }, alert: { rule_id: "analyst:dataset:harbour-extract" } }), ["Dataset alert", "Open", "24 November 2026, 09:15 UTC"]],
      [aRow({ row: { kind: "hotlist" } }), ["Hotlist", "Open", "24 November 2026, 09:15 UTC"]],
      [aRow({ row: { kind: "monitor" }, alert: { status: "claimed", assignee: "who" }, summary: "Claimed with a name" }), ["Watched pattern", "Claimed", "24 November 2026, 09:15 UTC"]],
      [aRow({ row: { kind: "analyst" }, alert: { status: "closing" } }), ["Raised by an analyst", "Closing", "24 November 2026, 09:15 UTC"]],
      [aRow({ row: { kind: "drawn_watch" }, alert: { status: "closed" } }), ["A load met a drawn item", "Closed", "24 November 2026, 09:15 UTC"]],
    ];
    const named = aRow({ row: { assignee_name: "Sam Example" }, alert: { status: "claimed", assignee: "sam" }, summary: "Held by someone" });
    const suppressed = aRow({ row: { suppressed: true }, alert: { suppressed_until: "2026-12-01T00:00:00Z", suppress_reason: "reason-marker" }, summary: "Suppressed one" });
    const offset = aRow({ alert: { created_at: "2026-11-24T10:15:00+01:00" }, summary: "Written with an offset" });
    const all = [...cases.map(([r]) => r), named, suppressed, offset];
    const w = await world([reader], []);
    // The queue is answered as given (closed and closing included): this case is about the words, not about which states the route sends.
    w.conduit.fault = { on: "queue", body: all };
    const res = await (await w.as(reader)).get(queueUrl(mine.id));
    expect(res.status).toBe(200);
    const grid = gridOf(res.text);
    cases.forEach(([row, [kind, state, when]], i) => {
      expect(grid?.rows[i]?.slice(1, 4), row.summary).toEqual([kind, state, when]);
    });
    const after = cases.length;
    expect(grid?.rows[after]?.[2]).toBe("Claimed by Sam Example");
    expect(grid?.rows[after + 1]?.[2]).toBe("Open, suppressed");
    expect(res.text).not.toContain("reason-marker");
    expect(grid?.rows[after + 2]?.[3]).toBe("24 November 2026, 09:15 UTC");
    expect(res.text).toMatch(/<time datetime="2026-11-24T09:15:00\.000Z">24 November 2026, 09:15 UTC<\/time>/);
  });

  it("AQ2: a typology alert is named by its typology exactly as the React queue names it (the shared table, every key of it)", () => {
    // The page keeps its own copy of the table (it imports no workspace package, as `studioWords.ts` does not): this holds the copy to the
    // shared one, key by key and for the fallback, so the two trees never name one alert in two ways.
    for (const [key, words] of Object.entries(TYPOLOGY_LABELS)) expect(typologyWords(key), key).toBe(words);
    for (const unknown of [null, undefined, "", "a_typology_nobody_named"]) expect(typologyWords(unknown), String(unknown)).toBe(typologyLabel(unknown));
    // `toString` and `constructor` are not typologies: a name taken from the object's own prototype would be a word nobody wrote.
    for (const inherited of ["toString", "constructor", "__proto__"]) expect(typologyWords(inherited), inherited).toBe("Alert");
  });

  it("AQ3: with no case lists the cases the Conduit sends as links to their queues, and reads no queue", async () => {
    const one = aCase({ name: "Wing review" });
    const two = aCase({ id: "case with / and ?", name: "Harbour & <quay> case" });
    const reader = aReader({ cases: [one, two] });
    const w = await world([reader], [held(one.id, aRow())]);
    const p = await w.as(reader);
    for (const path of ["/alert-queue", "/alert-queue?case="]) {
      const res = await p.get(path);
      expect(res.status).toBe(200);
      const links = focusable(mainOf(res.text)).filter((s) => s.href?.startsWith("/alert-queue")).map((s) => [s.text, s.href]);
      expect(links).toEqual([
        ["Wing review", `/alert-queue?case=${encodeURIComponent(one.id)}`],
        ["Harbour & <quay> case", `/alert-queue?case=${encodeURIComponent(two.id)}`],
      ]);
      expect(res.text).not.toContain("<quay>");
      expect(gridOf(res.text)).toBeUndefined();
    }
    expect(queueCalls(w.conduit)).toEqual([]);
    // No case held: said in words, with no link. The list that could not be read: said, and no link and no table.
    const nobody = aReader({ cases: [] });
    const w2 = await world([nobody], []);
    const empty = await (await w2.as(nobody)).get("/alert-queue");
    expect(empty.status).toBe(200);
    expect(textOf(mainOf(empty.text))).toContain("You do not hold any case yet.");
    expect(focusable(mainOf(empty.text)).filter((s) => s.href?.startsWith("/alert-queue"))).toEqual([]);
    w.conduit.fault = { on: "cases", status: 500 };
    const broken = await p.get("/alert-queue");
    expect(broken.status).toBe(502);
    expect(textOf(mainOf(broken.text))).toContain("The list of your cases could not be read. Try again in a few minutes.");
    expect(focusable(mainOf(broken.text)).filter((s) => s.href?.startsWith("/alert-queue?"))).toEqual([]);
    w.conduit.fault = { on: "cases", body: { not: "a list" } };
    expect((await p.get("/alert-queue")).status).toBe(502);
  });

  it("AQ3: a queue read still works when the case list cannot be, and says 'This case' for the case's name", async () => {
    const mine = aCase({ name: "Wing review" });
    const reader = aReader({ cases: [mine] });
    const w = await world([reader], [held(mine.id, aRow({ summary: "A finding" }))]);
    w.conduit.fault = { on: "cases", status: 503 };
    const res = await (await w.as(reader)).get(queueUrl(mine.id));
    expect(res.status).toBe(200);
    expect(gridOf(res.text)?.rows[0]?.[4]).toBe("This case");
    expect(gridOf(res.text)?.caption).toBe("Open, claimed and closing alerts in this case");
  });

  it("AQ4: a queue with no alert says so in words and draws no table", async () => {
    const mine = aCase();
    const reader = aReader({ cases: [mine] });
    const w = await world([reader], []);
    const res = await (await w.as(reader)).get(queueUrl(mine.id));
    expect(res.status).toBe(200);
    expect(gridOf(res.text)).toBeUndefined();
    expect(textOf(mainOf(res.text))).toContain("There are no alerts for you to see in this case.");
    expect(countProblems(res.text)).toEqual([]);
  });

  it("AQ4: a queue that cannot be read says so, draws no table and no zero, and one bad row makes the whole queue unreadable", async () => {
    const mine = aCase();
    const reader = aReader({ cases: [mine] });
    const good = aRow({ summary: "A good row" });
    const w = await world([reader], []);
    const p = await w.as(reader);
    const unreadable = async (why: string): Promise<void> => {
      const res = await p.get(queueUrl(mine.id));
      expect(res.status, why).toBe(502);
      expect(gridOf(res.text), why).toBeUndefined();
      expect(textOf(mainOf(res.text)), why).toContain("The alert queue could not be read. Nothing has changed. Try again in a few minutes.");
      expect(textOf(mainOf(res.text)), why).not.toMatch(/no alerts/i);
      expect(res.text, why).not.toContain("A good row");
    };
    const answers: [string, unknown, number?][] = [
      ["the Conduit failing", { detail: "Internal Server Error" }, 500],
      ["the Conduit unavailable", { detail: "Service Unavailable" }, 503],
      ["a body that is an object", { alerts: [good] }],
      ["a body that is text", "an answer"],
      ["a body that is null", null],
      ["a row that is not an object", [good, "a row"]],
      ["a row that is null", [good, null]],
    ];
    for (const [why, body, status] of answers) {
      w.conduit.fault = { on: "queue", body, ...(status === undefined ? {} : { status }) };
      await unreadable(why);
    }
    // A row missing one of the fields it draws (the route always sends each), or wrong in it: never a guess, never a zero.
    const without = (path: string): QueuedAlert => {
      const row = structuredClone(good) as unknown as Record<string, unknown>;
      const parts = path.split(".");
      const holder = parts.length === 2 ? (row[parts[0] as string] as Record<string, unknown>) : row;
      delete holder[parts[parts.length - 1] as string];
      return row as unknown as QueuedAlert;
    };
    for (const path of ["summary", "kind", "suppressed", "assignee_name", "alert", "alert.status", "alert.created_at"]) {
      w.conduit.fault = { on: "queue", body: [good, without(path)] };
      await unreadable(`a row without ${path}`);
    }
    const wrong: [string, QueuedAlert][] = [
      ["a state the route does not have", aRow({ alert: { status: "archived" as never } })],
      ["a kind the route does not have", aRow({ row: { kind: "rumour" as never } })],
      ["a time that is not one", aRow({ alert: { created_at: "last Tuesday" } })],
      ["a summary that is not text", aRow({ row: { summary: 7 as never } })],
      ["a suppressed mark that is not true or false", aRow({ row: { suppressed: "no" as never } })],
      ["a holder's name that is neither text nor null", aRow({ row: { assignee_name: 3 as never } })],
      ["a typology that is neither text nor null", aRow({ row: { kind: "typology" }, alert: { typology: 3 as never } })],
      ["an analyst alert whose rule is not text", aRow({ row: { kind: "analyst" }, alert: { rule_id: 3 as never } })],
    ];
    // A typology alert without the typology the route always sends, and an analyst alert without its rule, are bodies that are not the route's.
    const noTypology = aRow({ row: { kind: "typology" } });
    delete (noTypology.alert as unknown as Record<string, unknown>)["typology"];
    wrong.push(["a typology alert without a typology", noTypology]);
    const noRule = aRow({ row: { kind: "analyst" } });
    delete (noRule.alert as unknown as Record<string, unknown>)["rule_id"];
    wrong.push(["an analyst alert without a rule", noRule]);
    for (const [why, row] of wrong) {
      w.conduit.fault = { on: "queue", body: [good, row] };
      await unreadable(why);
    }
    // A Conduit that cannot be reached at all.
    await w.conduit.stop();
    w.conduit.fault = undefined;
    const gone = await p.get(queueUrl(mine.id));
    expect(gone.status).toBe(502);
    expect(gridOf(gone.text)).toBeUndefined();
    // Said in fixed words in the log, never a body: no summary, id or token.
    expect(p.logs.join("\n")).not.toContain("A good row");
    expect(p.logs.join("\n")).not.toContain(reader.token);
  });

  it("AQ5: whatever the Conduit refuses is answered as a path nothing serves, with none of the Conduit's words", async () => {
    const mine = aCase({ name: "Wing review" });
    const theirs = aCase({ name: "Someone else's case" });
    const alert = aRow({ summary: "Hidden finding" });
    const strangers = aReader({ cases: [theirs] });
    const noRight = aReader({ cases: [mine], rights: ["triage_alerts"] });
    const countsOnly = aReader({ cases: [mine], rights: ["read_alert_queue"] });
    const insufficient = aReader({ cases: [{ ...mine, level: "none" as never }] });
    const ok = aReader({ cases: [mine] });
    const w = await world([strangers, noRight, countsOnly, insufficient, ok], [held(mine.id, alert), held(theirs.id, aRow())]);
    const nothing = await (await w.as(ok)).get(NOWHERE);
    expect(nothing.status).toBe(404);
    const refusals: [string, Reader, string][] = [
      ["a case the person does not hold", strangers, mine.id],
      ["a case that does not exist", ok, "no-such-case"],
      ["the right to read the queue not held", noRight, mine.id],
      ["the rows not offered to the person (the counts are what they may read)", countsOnly, mine.id],
      ["a level in the case that is not enough", insufficient, mine.id],
      ["a case id that is not a plain one", ok, "../me"],
      ["a case id of two thousand characters", ok, "x".repeat(2000)],
      // `encodeURIComponent` leaves a dot segment as it is and the address is then resolved, so `.` would read
      // `/v1/investigations/alert-queue` (a case's own page, which writes an audit row) and `..` would read `/v1/alert-queue`.
      ["a case id that is one dot", ok, "."],
      ["a case id that is two dots", ok, ".."],
      // The real Conduit decodes `%2F` to `/` before it routes: each of these would reach another route of it (a node's ownership read,
      // `explain_alert` which writes an audit row), as the person. A case id is a plain name, so none is asked about.
      ["a case id holding a slash (X/ownership)", ok, `${mine.id}/ownership`],
      ["a case id holding a slash (X/alert-queue)", ok, `${mine.id}/alert-queue`],
      ["a case id holding a percent sign", ok, `${mine.id}%2Fownership`],
      ["a case id starting with a dot", ok, ".hidden"],
      ["a case id with a space", ok, "a case"],
      ["a case id of exactly the longest length plus one", ok, "a".repeat(201)],
    ];
    for (const [why, who, id] of refusals) {
      const p = await w.as(who);
      const callsBefore = w.conduit.calls.length;
      const res = await p.get(queueUrl(id));
      // An id that is not a plain name is refused before the Conduit is asked: whatever address it would be sent to, no call is made.
      // (The test states the rule it holds the page to: a plain name of at most 200 characters, as `server/plainName.ts`.)
      if (!(id.length <= 200 && /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(id))) {
        expect(w.conduit.calls.slice(callsBefore).map((c) => c.url), why).toEqual([]);
      }
      expect(res.status, why).toBe(404);
      // The same page, byte for byte but for the token and the nonce: nothing in it says what was refused or why.
      expect(sameFor(res.text, p.signed.csrf), why).toBe(sameFor((await p.get(NOWHERE)).text, p.signed.csrf));
      expect(res.text, why).not.toMatch(/right_required|read_alert_queue|queue_rows_not_offered|counts|investigation_not_found|insufficient|Viewer|Missing right|triage|rules/i);
      expect(res.text, why).not.toContain("Hidden finding");
    }
    // The query string as a browser carries it, `%2F` for the slash (and an unencoded slash): the same refusal, and no call.
    for (const raw of [`${mine.id}%2Fownership`, `${mine.id}%2Falert-queue`, `${mine.id}/ownership`, `${mine.id}/alert-queue`]) {
      const p = await w.as(ok);
      const callsBefore = w.conduit.calls.length;
      const res = await p.get(`/alert-queue?case=${raw}`);
      expect(res.status, raw).toBe(404);
      expect(w.conduit.calls.slice(callsBefore).map((c) => c.url), raw).toEqual([]);
      expect(sameFor(res.text, p.signed.csrf), raw).toBe(sameFor((await p.get(NOWHERE)).text, p.signed.csrf));
    }
    // A request with no session learns nothing and is sent to sign-in; the Conduit is not asked.
    const before = w.conduit.calls.length;
    const bare =await request((await w.as(ok)).app).get(queueUrl(mine.id));
    expect(bare.status).toBe(302);
    expect(bare.headers["location"]).toBe("/session/sign-in");
    expect(w.conduit.calls.length).toBe(before);
    // The Conduit does not know the person's bearer at all (401): the same words, and nothing of the answer.
    const unknown = aReader({ cases: [mine] });
    const w2 = await world([ok], [held(mine.id, alert)]);
    const lost = await (await w2.as(unknown)).get(queueUrl(mine.id));
    expect(lost.status).toBe(404);
    expect(lost.text).not.toContain("Not authenticated");
  });

  it("AQ6: the call carries the person's bearer and nothing the browser sent, and two people at once each see only what the Conduit sends them", async () => {
    const mine = aCase({ name: "Wing review" });
    const other = aCase({ name: "Harbour case" });
    const a = aReader({ cases: [mine] });
    const b = aReader({ cases: [other] });
    const w = await world([a, b], [held(mine.id, aRow({ summary: "A's finding" })), held(other.id, aRow({ summary: "B's finding" }))]);
    const [pa, pb] = await Promise.all([w.as(a), w.as(b)]);
    const [ra, rb] = await Promise.all([
      pa.get(queueUrl(mine.id)).set("X-Probe", "probe-marker").set("Referer", "https://elsewhere.example/").set("Authorization", "Bearer browser-chosen"),
      pb.get(queueUrl(other.id)).set("X-Probe", "probe-marker"),
    ]);
    expect(ra.status).toBe(200);
    expect(rb.status).toBe(200);
    expect(gridOf(ra.text)?.rows.map((r) => r[0])).toEqual(["A's finding"]);
    expect(gridOf(rb.text)?.rows.map((r) => r[0])).toEqual(["B's finding"]);
    expect(ra.text).not.toContain("B's finding");
    expect(rb.text).not.toContain("A's finding");
    for (const call of w.conduit.calls) {
      const who = call.headers["authorization"] === `Bearer ${a.token}` ? a : b;
      expect(headerProblems(call.headers, who.token), call.url).toEqual([]);
      expect(call.rawHeaders.join(" ")).not.toContain("probe-marker");
      expect(call.rawHeaders.join(" ")).not.toContain("browser-chosen");
      expect(call.query.toString()).toBe("");
    }
    // A's session carrying B's case: the Conduit decides, and says no, as for a case that does not exist.
    const crossed = await pa.get(queueUrl(other.id));
    expect(crossed.status).toBe(404);
    expect(crossed.text).not.toContain("B's finding");
    // The token is in no page, header or log.
    expect(JSON.stringify(ra.headers) + ra.text + pa.logs.join("\n")).not.toContain(a.token);
  });

  it("AQ7: an alert the Conduit left out is nowhere on the page, and the page is the same page as one where it never existed", async () => {
    const mine = aCase({ name: "Wing review" });
    const plain = aReader({ cases: [mine], cleared: [] });
    const cleared = aReader({ cases: [mine], cleared: ["restricted"] });
    const visibleA = aRow({ summary: "Visible A" });
    const visibleB = aRow({ summary: "Visible B", alert: { created_at: "2026-11-23T10:00:00Z" } });
    const hidden = aRow({ summary: "Restricted finding naming Harbour Quay", alert: { id: "alert-hidden-id" }, row: { kind: "hotlist", severity: "high" } });
    const withHidden = await world([plain, cleared], [held(mine.id, visibleA), held(mine.id, hidden, "restricted"), held(mine.id, visibleB)]);
    const without = await world([plain], [held(mine.id, visibleA), held(mine.id, visibleB)]);
    const [pw, po, pc] = [await withHidden.as(plain), await without.as(plain), await withHidden.as(cleared)];
    const seenWith = await pw.get(queueUrl(mine.id));
    const seenWithout = await po.get(queueUrl(mine.id));
    expect(seenWith.status).toBe(200);
    // Nothing of it: not its words, id, kind, severity, nor a gap, a count or a note. The two pages are the same but for the token and nonce.
    expect(leakProblems(seenWith.text, ["Restricted finding", "Harbour Quay", "alert-hidden-id", "restricted", "Hotlist"])).toEqual([]);
    expect(sameFor(seenWith.text, pw.signed.csrf)).toBe(sameFor(seenWithout.text, po.signed.csrf));
    expect(countProblems(seenWith.text)).toEqual([]);
    // The same of the case list: the cases a person holds are the Conduit's to say, and no number is added.
    expect(sameFor((await pw.get("/alert-queue")).text, pw.signed.csrf)).toBe(sameFor((await po.get("/alert-queue")).text, po.signed.csrf));
    // The reader who is cleared for it is sent it, and the page draws it.
    const seenCleared = await pc.get(queueUrl(mine.id));
    expect(gridOf(seenCleared.text)?.rows.map((r) => r[0])).toEqual(["Visible A", "Restricted finding naming Harbour Quay", "Visible B"]);
    expect(countProblems(seenCleared.text)).toEqual([]);
  });

  it("AQ7: the page filters nothing after retrieval: every row the Conduit sent is drawn, whatever it is, and no count is stated", async () => {
    const mine = aCase({ name: "Wing review" });
    const reader = aReader({ cases: [mine] });
    const sent = [
      aRow({ summary: "An open one" }),
      aRow({ summary: "A closing one", alert: { status: "closing" } }),
      aRow({ summary: "A suppressed one", row: { suppressed: true } }),
      aRow({ summary: "A low severity one", row: { severity: "low" } }),
      aRow({ summary: "An alert raised by someone else", alert: { owner_id: "someone-else" } }),
      aRow({ summary: "A twin of the first", alert: { created_at: "2026-11-24T09:15:00Z" } }),
      aRow({ summary: "A twin of the first", alert: { created_at: "2026-11-24T09:15:00Z" } }),
    ];
    // A Conduit that did NOT leave out an alert the reader may not see: the page is not the access control and keeps no filter of its own.
    const unclear = aRow({ summary: "An alert the reader is not cleared for" });
    const w = await world([reader], [...sent.map((r) => held(mine.id, r)), held(mine.id, unclear, "restricted")], { reach: false });
    const res = await (await w.as(reader)).get(queueUrl(mine.id));
    expect(res.status).toBe(200);
    expect(gridOf(res.text)?.rows.map((r) => r[0])).toEqual([...sent.map((r) => r.summary), unclear.summary]);
    expect(countProblems(res.text)).toEqual([]);
    expect(textOf(res.text)).not.toMatch(/\b8\b/);
    // And with a hundred and fifty alerts sent, none is cut: a bare slice near a limit is a defect (rule 2).
    const many = Array.from({ length: 150 }, (_, i) => aRow({ summary: `Finding number ${i + 1}` }));
    w.conduit.fault = { on: "queue", body: many };
    const big = await (await w.as(reader)).get(queueUrl(mine.id));
    expect(gridOf(big.text)?.rows.length).toBe(150);
    expect(gridOf(big.text)?.rows[149]?.[0]).toBe("Finding number 150");
  });

  it("AQ8: answers GET alone, has no form but sign-out and no control that acts, and calls the Conduit for two reads and nothing else", async () => {
    const mine = aCase();
    const reader = aReader({ cases: [mine] });
    const w = await world([reader], [held(mine.id, aRow())]);
    const p = await w.as(reader);
    const res = await p.get(queueUrl(mine.id));
    expect(formProblems(res.text)).toEqual([]);
    expect(focusable(res.text).filter((s) => s.tag !== "a").map((s) => s.text)).toEqual(["Sign out"]);
    expect(textOf(mainOf(res.text))).not.toMatch(/\b(close|claim|assign|suppress|approve|release|edit|delete|add a|new rule|new watch)\b/i);
    const before = w.conduit.calls.length;
    const api = request(p.app);
    for (const method of ["post", "put", "patch", "delete"] as const) {
      const sent = await api[method](queueUrl(mine.id)).set("Cookie", p.signed.cookie).set("X-CSRF-Token", p.signed.csrf).type("form").send({ _csrf: p.signed.csrf });
      expect(sent.status, method).toBe(404);
    }
    expect(w.conduit.calls.length).toBe(before);
    expect(w.conduit.calls.every((c) => c.method === "GET")).toBe(true);
  });

  it("AQ9: is complete with scripts off, has the structure of the tree's pages, and its tab stops come in the page's order", async () => {
    const mine = aCase({ name: "Wing review" });
    const second = aCase({ name: "Harbour case" });
    const reader = aReader({ cases: [mine, second] });
    const w = await world([reader], [held(mine.id, aRow())]);
    const p = await w.as(reader);
    const queue = await p.get(queueUrl(mine.id));
    const list = await p.get("/alert-queue");
    const empty = await (await world([reader], [])).as(reader).then((q) => q.get(queueUrl(mine.id)));
    for (const [name, page] of [["queue", queue], ["list", list], ["empty", empty]] as const) {
      expect(structureProblems(page.text), name).toEqual([]);
      expect(scriptsOffProblems(page.text), name).toEqual([]);
      expect(page.headers["content-security-policy"], name).not.toMatch(/unsafe-inline/);
    }
    const order = (html: string): string[] => focusable(html).map((s) => `${s.tag}: ${s.text}`);
    expect(order(queue.text)).toEqual(["a: Skip to main content", "button: Sign out", "a: All cases", "a: Back to Home"]);
    expect(order(list.text)).toEqual(["a: Skip to main content", "button: Sign out", "a: Wing review", "a: Harbour case", "a: Back to Home"]);
    expect(focusable(queue.text).map((s) => s.href)).toEqual(["#main", undefined, "/alert-queue", "/"]);
  });

  it("AQ10: the route is in the tree's list and in its table of pages, the govuk tree serves it and the default tree does not", async () => {
    const list = read("tree-govuk", "routes.yaml");
    const listed = [...list.matchAll(/^\s+-\s+(\S+)\s*$/gm)].map((m) => m[1]);
    // This page's path, once; the list and the tree's pages are the same (and HP9 holds them), so a page added to the tree edits nothing here.
    expect(listed.filter((r) => r === "/alert-queue")).toEqual(["/alert-queue"]);
    listed.sort();
    const govuk = PAGES.filter((page) => (page.trees ?? ["default"]).includes("govuk")).map((page) => [page.id, page.path, [...page.methods]]);
    expect(govuk).toContainEqual(["alerts-rules-watches", "/alert-queue", ["GET"]]);
    expect(govuk.map((g) => g[1] as string).sort()).toEqual(listed);
    expect(PAGES.filter((page) => page.path === "/alert-queue").map((page) => page.trees)).toEqual([["govuk"]]);
    // The row keeps an empty route: the function is complete only when its rules, watches and strength have pages too, and a row with a route
    // is read as a function whose GOV.UK page exists (`tree_parity.py`).
    expect(read("FUNCTIONS.yaml")).toMatch(/- id: alerts-rules-watches\n(?: {4}.*\n)*? {4}route: ""\n/);
    expect(read("FUNCTIONS.yaml")).not.toMatch(/- id: alerts-rules-watches\n(?: {4}.*\n)*? {4}route: "\/alert-queue"/);
    // The default tree answers it as a path nothing serves, signed in or not, and asks the Conduit nothing.
    const mine = aCase();
    const reader = aReader({ cases: [mine] });
    const w = await world([reader], [held(mine.id, aRow())]);
    const other = await w.as(reader, "default");
    const here = await other.get(queueUrl(mine.id));
    const nowhere = await other.get(NOWHERE);
    expect(here.status).toBe(404);
    expect(sameFor(here.text, other.signed.csrf)).toBe(sameFor(nowhere.text, other.signed.csrf));
    expect(w.conduit.calls).toEqual([]);
    expect((await request(other.app).get("/alert-queue")).headers["location"]).toBeUndefined();
  });

  it("AQ10: the page's own words are in server/views/alertQueueWords.ts, in British English, and none is written again in the template", async () => {
    const words: unknown = (await import("../../server/views/alertQueueWords.js")) as unknown;
    const exported = (words as { ALERT_QUEUE_WORDS?: Record<string, unknown> }).ALERT_QUEUE_WORDS;
    expect(exported).toBeDefined();
    const leaves: string[] = [];
    const walk = (value: unknown): void => {
      if (typeof value === "string") leaves.push(value);
      else if (Array.isArray(value)) value.forEach(walk);
      else if (value !== null && typeof value === "object") Object.values(value).forEach(walk);
    };
    walk(exported);
    expect(leaves.length).toBeGreaterThan(8);
    const template = read("tree-govuk", "alert-queue.njk").replace(/\{#[\s\S]*?#\}/g, "");
    expect(template).not.toBe("");
    for (const leaf of leaves.filter((l) => l.length > 6)) expect(template, `the template writes ${leaf} again`).not.toContain(leaf);
    const american = /\b(color|colour's|center|organization|favorite|behavior|analyze|recognize|catalog|license(?!d)|gray)\b/i;
    const source = read("server", "views", "alertQueueWords.ts").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    expect(source).not.toMatch(american);
    expect(leaves.join(" ")).not.toMatch(american);
  });

  it("AQ11: each check is red against the real page with one thing changed", async () => {
    const mine = aCase({ name: "Wing review" });
    const reader = aReader({ cases: [mine] });
    const row = aRow({ summary: "A finding" });
    const w = await world([reader], [held(mine.id, row)]);
    const p = await w.as(reader);
    const real = (await p.get(queueUrl(mine.id))).text;
    const nowhere = (await p.get(NOWHERE)).text;
    const refused = (await p.get(queueUrl("no-such-case"))).text;
    expect(refused).toContain("That page could not be found.");
    // The real page and the real Conduit call are clean under every check (so a finding below is the plant's).
    expect(structureProblems(real)).toEqual([]);
    expect(scriptsOffProblems(real)).toEqual([]);
    expect(formProblems(real)).toEqual([]);
    expect(countProblems(real)).toEqual([]);
    expect(leakProblems(real, MARKER_FIELDS(row))).toEqual([]);
    const seen = w.conduit.calls[w.conduit.calls.length - 1];
    expect(headerProblems(seen?.headers ?? {}, reader.token)).toEqual([]);
    const plants: [string, string[], string][] = [
      ["no skip link", structureProblems(real.replace(/<a class="skip-link"[^>]*>[^<]*<\/a>/, "")), "first stop"],
      ["a second heading of the first level", structureProblems(real.replace("<table", "<h1>Again</h1><table")), "headings of the first level"],
      ["a skipped heading level", structureProblems(real.replace("<table", "<h3>Skipped</h3><table")), "skips from level"],
      ["a table with no caption", structureProblems(real.replace(/<caption[\s\S]*?<\/caption>/, "")), "no caption"],
      ["a column header with no scope", structureProblems(real.replace('<th scope="col">Alert</th>', "<th>Alert</th>")), "scope"],
      ["a row header with no scope", structureProblems(real.replace(/<th scope="row"/, "<th")), "scope"],
      ["a script", scriptsOffProblems(real.replace("</main>", '<script src="/x.js"></script></main>')), "not a data block"],
      ["a handler", scriptsOffProblems(real.replace("<table", '<table onclick="go()"')), "event-handler"],
      ["an inline style", scriptsOffProblems(real.replace("<table", '<table style="width:1px"')), "inline style"],
      ["a tab stop of 3", scriptsOffProblems(real.replace("<table", '<table tabindex="3"')), "tab stop of 3"],
      ["an address on another origin", scriptsOffProblems(real.replace("</head>", '<link rel="stylesheet" href="https://elsewhere.example/a.css"></head>')), "another origin"],
      ["the queue in the data block", scriptsOffProblems(real.replace('{"page":"alert-queue"}', '{"page":"alert-queue","rows":["A finding"]}')), "data block holds more"],
      ["a form that closes an alert", formProblems(real.replace("<table", '<form method="post" action="/alert-queue/close"><table')), "not the sign-out"],
      ["a count written above the table", countProblems(real.replace("<table", "<p>4 alerts you can see.</p><table")), "number of alerts"],
      ["a count in the caption", countProblems(real.replace("</caption>", " (4)</caption>")), "brackets"],
      ["a total", countProblems(real.replace("<table", "<p>Showing 3 of 9</p><table")), "'of'"],
      ["a count in an attribute", countProblems(real.replace("<table", '<table aria-rowcount="4"')), "attribute"],
      ["a hidden alert's id in the data block", leakProblems(real.replace('{"page":"alert-queue"}', '{"page":"alert-queue","hidden":"alert-hidden-id"}'), ["alert-hidden-id"]), "alert-hidden-id"],
      ["an entity's id in the page", leakProblems(real.replace("<table", `<table data-node="${row.alert.referent_node_ids?.[0] ?? ""}"`), MARKER_FIELDS(row)), "node-id"],
      ["a cookie sent on to the Conduit", headerProblems({ authorization: `Bearer ${reader.token}`, cookie: "session=1" }, reader.token), "cookie"],
      ["another person's bearer", headerProblems({ authorization: "Bearer someone-else" }, reader.token), "own bearer"],
      ["the browser's own bearer", headerProblems({ ...(seen?.headers ?? {}), authorization: "Bearer browser" }, reader.token), "own bearer"],
    ];
    for (const [label, found, expected] of plants) {
      expect(found.length, `${label}: the check found nothing`).toBeGreaterThan(0);
      expect(found.join(" | "), label).toContain(expected);
    }
    // A refusal worded other than a missing page differs from it, so the comparison AQ5 makes can fail.
    expect(sameFor(refused, p.signed.csrf)).toBe(sameFor(nowhere, p.signed.csrf));
    expect(sameFor(refused.replace("That page could not be found.", "You may not read that queue."), p.signed.csrf)).not.toBe(sameFor(nowhere, p.signed.csrf));
  });
});
