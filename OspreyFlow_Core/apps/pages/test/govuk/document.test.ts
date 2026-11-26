/**
 * One document of a case in the reader, read-only, on the GOV.UK tree (slice GG3b; ADR-152 decisions 1, 4, 5, 6, 7 and 12; FUNCTIONS
 * row `documents`; scenario DR of `spec/08_ACCEPTANCE_SCENARIOS.md`, written first).
 * `tests/glass_trees/test_govuk_document_scenario.py` holds the scenario and this file in step: each case's id is a row of the scenario.
 *
 * There is no React-first proof (the React reader is a dialog opened from the canvas, with designation and extraction beside the text):
 * the proof is the real service started for the GOV.UK tree, the real page list, the real `/v1` forwarder, and a fixture Conduit that
 * refuses what the real routes refuse (`documentConduit.ts`).
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a span's provenance drawn as another's, a span missing, out of order, a hidden span drawn, a type in other words  -> DR1
 *  - text lost or doubled where spans touch or overlap, a mark moved by a character outside the basic plane              -> DR2
 *  - a sender or recipient named, a time not said or said in other words                                                    -> DR3
 *  - a cut text not said                                                                                                     -> DR4
 *  - a picture not drawn, inlined, from another address, or one drawn with no file                                          -> DR5
 *  - a film drawn as a picture                                                                                               -> DR6
 *  - a file of another kind embedded                                                                                         -> DR7
 *  - a missing title said as the id                                                                                          -> DR8
 *  - a hidden, missing or other case's document told apart, or told in other words than an unknown path's                   -> DR9
 *  - the document read twice, the browser's headers sent on, a write, an unsigned read                                       -> DR10
 *  - a failed read drawn as an empty text, an ended session not said                                                         -> DR11
 *  - a missing or wrong field read as empty, a span the page cannot place drawn                                              -> DR12
 *  - a graph id in the page                                                                                                  -> DR13
 *  - markup drawn as markup                                                                                                  -> DR14
 *  - the file's answer without nosniff                                                                                       -> DR15
 *  - a form, a control, a skipped heading, a stop out of order, a script                                                     -> DR16
 *  - a field neither drawn nor named as left out, a left-out field that changes the page                                    -> DR17
 *  - the page in the Default tree, left out of the route list, its code choosing what is drawn, American spelling            -> DR18
 * Every planted fault is the real page (or the real view, or the real file) with one thing changed, run through the same function that
 * finds nothing in the real one (DR19, rule 15).
 */
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Express } from "express";
import { afterEach, describe, expect, it } from "vitest";

import { createApp } from "../../server/app.js";
import { PAGES } from "../../server/pageList.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { CENSUS, DOCUMENT_WORDS, REQUIRED, documentView } from "../../server/views/documentWords.js";
import { refusalWords } from "../../server/views/studioWords.js";
import { testClock } from "../support/clock.js";
import { cookieFrom, csrfFromPage, request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { bearer, providerFor } from "../support/studioWorld.js";
import { NOT_FOUND_CASE, NOT_FOUND_DOCUMENT, PNG, RIGHT_REFUSAL, UNKNOWN_BEARER, documentConduit, readerViewOf } from "./documentConduit.js";
import type { Case, Doc, DocumentConduit, DocumentConduitOptions, Reader, Span } from "./documentConduit.js";

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const read = (...parts: string[]): string => readFileSync(join(...parts), "utf8");

const PATH = "/cases/document";
const NOWHERE = "/nothing-is-served-here";
const pageOf = (caseId: string, documentId: string): string => `${PATH}?case=${encodeURIComponent(caseId)}&document=${encodeURIComponent(documentId)}`;
const fileOf = (caseId: string, documentId: string): string => `/v1/investigations/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/file`;
const readerOf = (caseId: string, documentId: string): string => `/v1/investigations/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/reader`;

// ------------------------------------------------------------------------------------------------ the world

const conduits: DocumentConduit[] = [];
afterEach(async () => {
  while (conduits.length > 0) await conduits.pop()?.stop();
});

const UNIT = "harbour-unit";
const CASE = "c-harbour";
const CASES: Case[] = [
  { id: CASE, owning_unit: UNIT },
  { id: "c-ferry", owning_unit: UNIT },
  { id: "c-unshared", owning_unit: UNIT },
  { id: "c-away", owning_unit: "other-unit" },
];
const LEVELS: Reader["levels"] = { [CASE]: "viewer", "c-ferry": "editor", "c-away": "author" };
const CLEARANCE = 2;

const base = (over: Partial<Doc> & Pick<Doc, "id">): Doc => ({
  case_id: CASE,
  title: "A synthetic note",
  text: "",
  truncated: false,
  spans: [],
  sent_at: null,
  sender_id: null,
  recipient_id: null,
  edge_id: null,
  event_id: null,
  media_kind: null,
  has_file: false,
  ...over,
});

const span = (start: number, end: number, entity_type: string, provenance_state: Span["provenance_state"], node_id: string, marking?: number): Span =>
  marking === undefined ? { start, end, node_id, entity_type, provenance_state } : { start, end, node_id, entity_type, provenance_state, marking };

// "Ada Quill met the Harbour Board at Pier Nine.\nBrook Vale signed." with its places counted by hand.
const LEDGER_TEXT = "Ada Quill met the Harbour Board at Pier Nine.\nBrook Vale signed.";
const LEDGER: Doc = base({
  id: "d-ledger",
  title: "Quay ledger note",
  text: LEDGER_TEXT,
  spans: [
    span(0, 9, "Person", "asserted", "n-ada-1"),
    span(18, 31, "Organisation", "inferred", "n-board-2"),
    span(35, 44, "Location", "asserted", "n-pier-3"),
    // A span whose node the reader may not see: the route leaves it out (rule 3), so the page never has it.
    span(46, 56, "Person", "asserted", "n-hidden-4", 5),
    span(57, 63, "Event", "unresolved", "n-signed-5"),
  ],
});

// Touching: "Ada" then "Quill"; overlapping: "Harbour Board" and "Board"; a parcel sign outside the basic plane before the last span.
const OVERLAP_TEXT = "AdaQuill met the Harbour Board.\n📦 Pier Nine";
const OVERLAP: Doc = base({
  id: "d-overlap",
  title: "Touching and overlapping",
  text: OVERLAP_TEXT,
  spans: [
    span(0, 3, "Person", "asserted", "n-ov-1"),
    span(3, 8, "Person", "inferred", "n-ov-2"),
    span(17, 30, "Organisation", "asserted", "n-ov-3"),
    span(25, 30, "Organisation", "inferred", "n-ov-4"),
    span(34, 43, "Location", "asserted", "n-ov-5"),
  ],
});

const EMAIL: Doc = base({
  id: "d-email",
  title: "Re: the night berth",
  text: "Meet at berth four after dark.",
  truncated: true,
  sent_at: "2026-03-03T14:05:00Z",
  sender_id: "n-sender-71",
  recipient_id: "n-recipient-82",
  edge_id: "e-link-93",
  event_id: "ev-email-104",
  spans: [span(8, 18, "Location", "inferred", "n-berth-6")],
});

const PHOTO: Doc = base({ id: "d-photo", title: "Gate photograph", media_kind: "image", has_file: true, file: { bytes: PNG, type: "image/png" } });
const NO_FILE: Doc = base({ id: "d-photo-gone", title: "A picture never kept", media_kind: "image", has_file: false });
const FILM: Doc = base({ id: "d-film", title: "Quay camera", media_kind: "video", has_file: true, file: { bytes: Buffer.from("synthetic film"), type: "video/webm" } });
const KEPT: Doc = base({ id: "d-kept", title: "Kept text", text: "A kept note.", media_kind: "text", has_file: true, file: { bytes: Buffer.from("A kept note."), type: "text/plain" } });
const ODD: Doc = base({ id: "d-odd", title: "A sound", media_kind: "audio", has_file: true, file: { bytes: Buffer.from("noise"), type: "application/octet-stream" } });
const UNTITLED: Doc = base({ id: "d-untitled-77", title: null, text: "Nothing to name it by." });
const MARKUP: Doc = base({
  id: "d-markup",
  title: "<b>Bold</b> & co",
  text: "<script>alert(1)</script> <img src=x onerror=y>",
  spans: [span(0, 8, "<i>Type</i>", "asserted", "n-mk-1")],
});
// A span whose place is not in the text, as the real route can send one: the designation route checks the words with a Python slice,
// which accepts an end past the text ("abc"[1:99] == "bc"), and a second extraction replaces the kept text under accepted spans.
const STALE: Doc = base({
  id: "d-stale",
  title: "Re-read note",
  text: "Ada met the board.",
  spans: [span(0, 3, "Person", "asserted", "n-st-1"), span(8, 99, "Organisation", "inferred", "n-st-2"), span(12, 12, "Thing", "asserted", "n-st-3")],
});
const SECRET: Doc = base({ id: "d-secret", title: "Above the reader", text: "Not yours.", marking: 5 });
const PERSON: Doc = base({ id: "d-person", type: "Person", title: "Not a document" });
const ELSEWHERE: Doc = base({ id: "d-elsewhere", case_id: "c-ferry", title: "In another case" });
const UNSHARED: Doc = base({ id: "d-unshared", case_id: "c-unshared", title: "In an unshared case" });
const AWAY: Doc = base({ id: "d-away", case_id: "c-away", title: "In another unit's case" });

const DOCS: Doc[] = [LEDGER, OVERLAP, EMAIL, PHOTO, NO_FILE, FILM, KEPT, ODD, UNTITLED, MARKUP, STALE, SECRET, PERSON, ELSEWHERE, UNSHARED, AWAY];

interface World {
  app: Express;
  conduit: DocumentConduit;
  reader: Reader;
  cookie: string;
  csrf: string;
}

interface WorldOptions extends Partial<Omit<DocumentConduitOptions, "readers">> {
  rights?: string[];
  levels?: Reader["levels"];
  tree?: "govuk" | "default";
  conduitUrl?: string;
  unknownBearer?: boolean;
}

async function world(options: WorldOptions = {}): Promise<World> {
  const token = bearer();
  const reader: Reader = { token, unit: UNIT, rights: options.rights ?? ["investigate"], levels: options.levels ?? LEVELS, clearance: CLEARANCE };
  const { rights: _r, levels: _l, tree: _t, conduitUrl: _c, unknownBearer: _u, ...answers } = options;
  const conduit = await documentConduit({ readers: options.unknownBearer === true ? [] : [reader], cases: options.cases ?? CASES, documents: options.documents ?? DOCS, ...answers });
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
const calls = (c: DocumentConduit): string[] => c.calls.map((call) => `${call.method} ${call.url}`);

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
const unescape = (s: string): string => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const textOf = (html: string): string => unescape(html.replace(/<script\b[\s\S]*?<\/script>/g, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim());

function mainOf(html: string): string {
  const found = /<main\b[^>]*>([\s\S]*?)<\/main>/.exec(strip(html));
  return found ? (found[1] as string) : "";
}
const mainText = (html: string): string => textOf(mainOf(html));

interface Stop {
  tag: string;
  href: string | undefined;
  text: string;
}

function focusable(html: string): Stop[] {
  const stops: Stop[] = [];
  for (const m of strip(html).matchAll(/<(a|button)\b([^>]*)>([\s\S]*?)<\/\1>|<(input|select|textarea)\b([^>]*)>|<(video)\b([^>]*)>/g)) {
    const tag = (m[1] ?? m[4] ?? m[6]) as string;
    const attrs = (m[2] ?? m[5] ?? m[7]) as string;
    if (tag === "input" && /\stype="hidden"/.test(attrs)) continue;
    if (tag === "a" && attr(attrs, "href") === undefined) continue;
    if (tag === "video" && !/\scontrols\b/.test(attrs)) continue;
    const href = attr(attrs, "href");
    stops.push({ tag, href: href === undefined ? undefined : unescape(href), text: tag === "video" ? (attr(attrs, "aria-label") ?? "") : textOf(m[3] ?? "") });
  }
  return stops;
}

const headings = (html: string): { level: number; text: string }[] =>
  [...strip(html).matchAll(/<h([1-6])\b([^>]*)>([\s\S]*?)<\/h\1>/g)].map((m) => ({ level: Number(m[1]), text: textOf(m[3] as string) }));

/** The document's text as drawn: the words, with each line break given back, and each marked passage's words, in order. */
function drawnText(html: string): { text: string; marks: string[] } | undefined {
  const found = /<p id="document-text">([\s\S]*?)<\/p>/.exec(mainOf(html));
  if (!found) return undefined;
  const inner = (found[1] as string).replace(/<br>/g, "\n");
  const marks = [...inner.matchAll(/<mark>([\s\S]*?)<\/mark>/g)].map((m) => unescape(m[1] as string));
  return { text: unescape(inner.replace(/<\/?mark>/g, "")), marks };
}

interface MarkRow {
  words: string;
  type: string;
  how: string;
}

function tableOf(html: string): { caption: string; columns: string[]; rows: MarkRow[] } | undefined {
  const found = /<table\b[^>]*>([\s\S]*?)<\/table>/.exec(mainOf(html));
  if (!found) return undefined;
  const inner = found[1] as string;
  const caption = textOf(/<caption\b[^>]*>([\s\S]*?)<\/caption>/.exec(inner)?.[1] ?? "");
  const head = /<thead\b[^>]*>([\s\S]*?)<\/thead>/.exec(inner)?.[1] ?? "";
  const columns = [...head.matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/g)].map((m) => textOf(m[1] as string));
  const body = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/.exec(inner)?.[1] ?? "";
  const rows = [...body.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((row) => {
    const cells = [...(row[1] as string).matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/g)].map((c) => unescape((c[1] as string).replace(/<br>/g, "\n")));
    return { words: cells[0] ?? "", type: cells[1] ?? "", how: cells[2] ?? "" };
  });
  return { caption, columns, rows };
}

/** Every fault in a page's structure, in words: the same function reads the real page and each planted one (DR16). */
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

/** Every thing in a page that needs a script, an inline rule or a tab stop out of order (DR16). */
function scriptsOffProblems(html: string): string[] {
  const page = strip(html);
  const found: string[] = [];
  for (const s of page.matchAll(/<script\b([^>]*)>/g)) {
    if (attr(s[1] as string, "type") !== "application/json") found.push(`a script element that is not a data block: <script${s[1] as string}>`);
  }
  // Inside a tag only: a text that says "onerror=" is drawn escaped, as words, and is no attribute (DR14).
  if (/<[^>]*\son[a-z]+\s*=/i.test(page)) found.push("an event-handler attribute");
  if (/<[^>]*\sstyle\s*=/i.test(page)) found.push("an inline style attribute");
  if (/<style\b/i.test(page)) found.push("a style element");
  if (/<[^>]*javascript:/i.test(page)) found.push("a javascript: address");
  for (const t of page.matchAll(/\stabindex="(-?\d+)"/g)) if (Number(t[1]) > 0) found.push(`a tab stop of ${t[1] as string}`);
  return found;
}

/** What the refusal must be: the unknown path's page, byte for byte but for the script nonce. */
const refusalProblems = (refused: { status: number; text: string }, unknown: { status: number; text: string }): string[] =>
  refused.status === unknown.status && withoutNonce(refused.text) === withoutNonce(unknown.text) ? [] : ["the refusal is not the page of a path nothing serves"];

/** Graph ids and Conduit words the page must never show, in any text or attribute (DR13). */
const GRAPH_IDS = DOCS.flatMap((d) => [...d.spans.map((s) => s.node_id), d.sender_id, d.recipient_id, d.edge_id, d.event_id]).filter((id): id is string => id !== null);
// (The hidden span's words, "Brook Vale", are in the text the reader may read: only its mark is withheld, which DR1 checks.)
const NEVER = [...GRAPH_IDS, "document_not_found", "investigation_not_found", "right_required", "investigate", "data-node", UNIT, "not have access"];
const neverProblems = (html: string): string[] => NEVER.filter((word) => strip(html).includes(word)).map((word) => `the page shows ${JSON.stringify(word)}`);

// ------------------------------------------------------------------------------------------------ what the page should draw

const HOW: Record<Span["provenance_state"], string> = {
  asserted: "Marked by a person",
  inferred: "Proposed by a model, not yet confirmed",
  unresolved: "From a single source, not yet corroborated",
};
const codePoints = (text: string): string[] => Array.from(text);
const wordsOf = (text: string, s: Pick<Span, "start" | "end">): string => codePoints(text).slice(s.start, s.end).join("");
// The fixture leaves out a span the reader may not see, as the route does (`dossier.py`'s `narrow_to_visible`): the page is only ever
// sent the rest, so what these checks prove is that the page draws what it is sent, not the route's filter (the Conduit's own tests').
const visible = (d: Doc): Span[] => d.spans.filter((s) => (s.marking ?? 0) <= CLEARANCE);
/** A span whose words are in the text: it starts before it ends, and ends within the text. */
const placed = (d: Doc, s: Span): boolean => s.start < s.end && s.end <= codePoints(d.text).length;

/** The marked passages the text must hold: overlapping spans joined into one, touching ones kept apart, in order. */
function passagesOf(d: Doc): string[] {
  const groups: { start: number; end: number }[] = [];
  for (const s of visible(d).filter((one) => placed(d, one))) {
    const last = groups[groups.length - 1];
    if (last && s.start < last.end) last.end = Math.max(last.end, s.end);
    else groups.push({ start: s.start, end: s.end });
  }
  return groups.map((g) => wordsOf(d.text, g));
}

/** Every fault in the text and the table as drawn against what was sent (DR1, DR2, DR19). */
function markProblems(html: string, d: Doc): string[] {
  const found: string[] = [];
  const text = drawnText(html);
  if (!text) return ["the page has no text block"];
  if (text.text !== d.text) found.push(`the text drawn is ${JSON.stringify(text.text)}, not ${JSON.stringify(d.text)}`);
  if (JSON.stringify(text.marks) !== JSON.stringify(passagesOf(d))) found.push(`the marked passages are ${JSON.stringify(text.marks)}, not ${JSON.stringify(passagesOf(d))}`);
  const spans = visible(d);
  const table = tableOf(html);
  if (spans.length === 0) {
    if (table) found.push("a document with no span draws a table");
    if (!mainText(html).includes(DOCUMENT_WORDS.noMarks)) found.push("a document with no span does not say so");
    return found;
  }
  if (!table) return [...found, "the page has no table of marked words"];
  if (table.caption !== DOCUMENT_WORDS.caption) found.push(`the caption is ${JSON.stringify(table.caption)}`);
  if (JSON.stringify(table.columns) !== JSON.stringify(DOCUMENT_WORDS.columns)) found.push(`the columns are ${JSON.stringify(table.columns)}`);
  const want = spans.map((s) => ({ words: placed(d, s) ? wordsOf(d.text, s) : DOCUMENT_WORDS.notInText, type: s.entity_type, how: HOW[s.provenance_state] }));
  const said = mainText(html).includes(DOCUMENT_WORDS.someNotPlaced);
  if (said !== spans.some((s) => !placed(d, s))) found.push(`the page ${said ? "says" : "does not say"} that some marked words are not in the text`);
  if (JSON.stringify(table.rows) !== JSON.stringify(want)) found.push(`the rows are ${JSON.stringify(table.rows)}, not ${JSON.stringify(want)}`);
  return found;
}

type FileSaid = { kind: "picture" | "film" | "link"; src: string } | undefined;

/** The file as drawn: an `<img>`, a `<video>`, or a link to the file (DR5 to DR7). */
function fileOn(html: string): { kinds: string[]; file: FileSaid; name: string | undefined } {
  const main = mainOf(html);
  const kinds: string[] = [];
  let file: FileSaid;
  let name: string | undefined;
  for (const m of main.matchAll(/<img\b([^>]*)>/g)) {
    kinds.push("picture");
    file = { kind: "picture", src: unescape(attr(m[1] as string, "src") ?? "") };
    name = attr(m[1] as string, "alt");
  }
  for (const m of main.matchAll(/<video\b([^>]*)>/g)) {
    kinds.push(/\scontrols\b/.test(m[1] as string) ? "film" : "film without controls");
    file = { kind: "film", src: unescape(attr(m[1] as string, "src") ?? "") };
    name = attr(m[1] as string, "aria-label");
  }
  if (/<(object|embed|iframe)\b/.test(main)) kinds.push("embedded");
  if (kinds.length === 0) {
    const link = /<a\b([^>]*)>([^<]*)<\/a>/g;
    for (const m of main.matchAll(link)) {
      const href = unescape(attr(m[1] as string, "href") ?? "");
      if (href.startsWith("/v1/")) {
        kinds.push("link");
        file = { kind: "link", src: href };
        name = unescape(m[2] as string);
      }
    }
  }
  return { kinds, file, name };
}

/** What the file must be for this document: the forwarder's path, drawn by its kind (DR5 to DR7). */
function fileProblems(html: string, d: Doc): string[] {
  const drawn = fileOn(html);
  const src = fileOf(d.case_id, d.id);
  if (!d.has_file) return drawn.kinds.length === 0 ? [] : [`a document with no file draws ${drawn.kinds.join(", ")}`];
  const want = d.media_kind === "image" ? "picture" : d.media_kind === "video" ? "film" : "link";
  const name = want === "picture" ? DOCUMENT_WORDS.picture : want === "film" ? DOCUMENT_WORDS.film : DOCUMENT_WORDS.openFile;
  const found: string[] = [];
  if (JSON.stringify(drawn.kinds) !== JSON.stringify([want])) found.push(`the file is drawn as ${JSON.stringify(drawn.kinds)}, not as a ${want}`);
  if (drawn.file?.src !== src) found.push(`the file's address is ${JSON.stringify(drawn.file?.src)}, not ${src}`);
  if (drawn.name !== name) found.push(`the file is named ${JSON.stringify(drawn.name)}, not ${JSON.stringify(name)}`);
  return found;
}

/** What a failed read must be (DR11): the words, as an alert, and no text, mark or table. */
const failedProblems = (html: string): string[] => {
  const found: string[] = [];
  if (!/<p role="alert">[^<]*could not be read/.test(mainOf(html))) found.push("the failure is not said as an alert");
  if (/<table|<mark|id="document-text"|<img|<video/.test(mainOf(html))) found.push("a failed read draws the document or part of it");
  return found;
};

const callProblems = (made: string[], want: string[]): string[] => (JSON.stringify(made) === JSON.stringify(want) ? [] : [`the page asked ${JSON.stringify(made)}, not ${JSON.stringify(want)}`]);

// ------------------------------------------------------------------------------------------------ the sources

const SOURCES = ["server/document.ts", "server/views/documentWords.ts", "tree-govuk/document.njk"];
const sourcesOfThePage = (): { name: string; text: string }[] => SOURCES.map((name) => ({ name, text: read(PAGES_DIR, name) }));
const withoutComments = (text: string): string => text.replace(/\/\*[\s\S]*?\*\/|\/\/.*$|\{#[\s\S]*?#\}/gm, "");
/** The page does not choose what is drawn: no call in its code removes, cuts, sorts or turns a span round (decision 5). The census's own
 * `NOT_SENT`-free required list is built with a spread, not a filter, so the words module holds no `.filter` at all. */
const CHOOSING = /\.(?:filter|slice|splice|sort|toSorted|reverse|toReversed|shift|pop|substring|substr)\s*\(|\b(?:continue|break)\s*;|\|\s*(?:sort|reverse|first|last|batch|slice|reject|select|selectattr|rejectattr|truncate)\b/;
const choosingProblems = (sources: { name: string; text: string }[]): string[] =>
  sources.filter((s) => CHOOSING.test(withoutComments(s.text))).map((s) => `${s.name} chooses what is drawn: ${CHOOSING.exec(withoutComments(s.text))?.[0] ?? ""}`);
const AMERICAN = /\b(?:color|colors|organization|organizations|center|centers|authorize|authorized|behavior|license|licenses|analyze|favorite|catalog)\b/i;

// ------------------------------------------------------------------------------------------------ the bodies, for the census and the reader

/** A document with every field of both models given a value that is drawn, or would be. */
const CENSUS_DOC: Doc = base({
  id: "d-census",
  title: "Census note",
  text: "Ada met Brook at the quay.",
  spans: [span(0, 3, "Person", "asserted", "n-cen-1"), span(8, 13, "Person", "inferred", "n-cen-2")],
  sent_at: "2026-04-05T06:07:00Z",
  sender_id: "n-cen-from",
  recipient_id: "n-cen-to",
  edge_id: "e-cen",
  event_id: "ev-cen",
  media_kind: "image",
  has_file: true,
  file: { bytes: PNG, type: "image/png" },
});
const sampleReader = { clearance: CLEARANCE };
const censusBody = (): Record<string, unknown> & { spans: Record<string, unknown>[] } => readerViewOf(CENSUS_DOC, sampleReader) as never;

/** A different valid value for each field of each model: a drawn field must change the page with it, a left-out field must not. */
const OTHER: Record<string, Record<string, unknown>> = {
  DocumentReaderView: {
    document_id: "d-another",
    title: "Another title",
    text: "Ada met Brook at the dock.",
    truncated: true,
    spans: [{ start: 4, end: 7, node_id: "n-cen-3", entity_type: "Event", provenance_state: "unresolved" }],
    sent_at: "2025-01-03T04:05:00Z",
    sender_id: "n-other-from",
    recipient_id: "n-other-to",
    edge_id: "e-other",
    event_id: "ev-other",
    media_kind: "video",
    has_file: false,
  },
  MessageSpan: { start: 1, end: 2, node_id: "n-cen-other", entity_type: "Location", provenance_state: "unresolved" },
};

/** The body with one field of one model changed (or removed, `value` undefined): for a span, the first. */
function withField(model: string, field: string, value: unknown): Record<string, unknown> {
  const b = censusBody();
  const target = model === "DocumentReaderView" ? b : (b.spans[0] as Record<string, unknown>);
  if (value === undefined) delete target[field];
  else target[field] = value;
  return b;
}

/** The page as the real service draws it from this body (the fixture serves it through its real refusals). */
async function drawn(body: unknown): Promise<{ html: string; status: number }> {
  const w = await world({ documents: [...DOCS, CENSUS_DOC], reader_answer: { status: 200, body } });
  const res = await getAs(w, pageOf(CASE, CENSUS_DOC.id));
  return { html: mainOf(res.text), status: res.status };
}

type Census = Record<string, { readonly drawn: readonly string[]; readonly left: readonly string[] }>;

/** Every field a census says is drawn that changes nothing, and every field it says is left out that changes the page, when the
 * field's value changes (DR17): the same function reads the real census and each planted one (DR19). */
async function censusProblems(census: Census): Promise<string[]> {
  const found: string[] = [];
  const baseline = await drawn(censusBody());
  if (baseline.status !== 200) return [`the page answered ${baseline.status}`];
  for (const [model, { drawn: drawnFields, left }] of Object.entries(census)) {
    const fields = [...drawnFields, ...left];
    if (JSON.stringify(Object.keys(OTHER[model] ?? {}).sort()) !== JSON.stringify([...fields].sort())) found.push(`the census of ${model} is not the fields the test can change`);
    for (const field of fields) {
      const changed = await drawn(withField(model, field, (OTHER[model] as Record<string, unknown>)[field]));
      if (changed.status !== 200) {
        found.push(`${model}.${field} changed is a page that answers ${changed.status}`);
        continue;
      }
      const moved = changed.html !== baseline.html;
      if (drawnFields.includes(field) && !moved) found.push(`${model}.${field} is drawn but changes nothing`);
      if (!drawnFields.includes(field) && moved) found.push(`${model}.${field} is left out but changes the page`);
    }
  }
  return found;
}

const viewOf = (body: unknown) => documentView(CASE, CENSUS_DOC.id, body);

// ------------------------------------------------------------------------------------------------ the cases

describe("one document of a case in the reader, on the GOV.UK tree (scenario DR)", () => {
  it("DR1: the title, the text with each span marked in place, and a table of the marked words with their type and how each was marked", async () => {
    const w = await world();
    const res = await getAs(w, pageOf(CASE, LEDGER.id));
    expect(res.status).toBe(200);
    expect(headings(mainOf(res.text))[0]).toEqual({ level: 1, text: "Quay ledger note" });
    expect(markProblems(res.text, LEDGER)).toEqual([]);
    expect(tableOf(res.text)?.rows.map((r) => r.how)).toEqual([HOW.asserted, HOW.inferred, HOW.asserted, HOW.unresolved]);
    expect(DOCUMENT_WORDS.provenance).toEqual(HOW);
    expect(DOCUMENT_WORDS.columns).toEqual(["Words", "Type", "How it was marked"]);
    // The span whose node the reader may not see is not sent (the route's rule 3), and so not drawn, as a mark or a row.
    expect(neverProblems(res.text)).toEqual([]);
    expect(drawnText(res.text)?.marks).not.toContain("Brook Vale");
    // No span: said in words, with no table.
    const none = await getAs(w, pageOf(CASE, UNTITLED.id));
    expect(markProblems(none.text, UNTITLED)).toEqual([]);
    expect(mainText(none.text)).toContain("No words are marked in this document.");
  });

  it("DR2: touching spans are two marks, overlapping ones one, the text whole with its line breaks, places counted as the Conduit counts", async () => {
    const w = await world();
    const res = await getAs(w, pageOf(CASE, OVERLAP.id));
    expect(markProblems(res.text, OVERLAP)).toEqual([]);
    expect(drawnText(res.text)?.marks).toEqual(["Ada", "Quill", "Harbour Board", "Pier Nine"]);
    expect(tableOf(res.text)?.rows.map((r) => r.words)).toEqual(["Ada", "Quill", "Harbour Board", "Board", "Pier Nine"]);
    expect(mainOf(res.text)).toContain("<br>");
  });

  it("DR3: an email says when it was sent, and names neither its sender nor its recipient", async () => {
    const w = await world();
    const res = await getAs(w, pageOf(CASE, EMAIL.id));
    expect(mainText(res.text)).toContain("Sent on 3 March 2026 at 14:05 UTC");
    expect(DOCUMENT_WORDS.sentOn("2026-11-26T09:05:00Z")).toBe("Sent on 26 November 2026 at 09:05 UTC");
    // A time with no offset (Pydantic's for a plain datetime) is UTC, the Conduit's, whatever the server's own zone.
    const zone = process.env["TZ"];
    process.env["TZ"] = "Asia/Tokyo";
    try {
      expect(new Date("2026-07-03T14:05:00").getUTCHours()).toBe(5); // the engine reads it as local time: the zone took
      expect(DOCUMENT_WORDS.sentOn("2026-07-03T14:05:00")).toBe("Sent on 3 July 2026 at 14:05 UTC");
      expect(DOCUMENT_WORDS.sentOn("2026-07-03T14:05:00+01:00")).toBe("Sent on 3 July 2026 at 13:05 UTC");
    } finally {
      if (zone === undefined) delete process.env["TZ"];
      else process.env["TZ"] = zone;
    }
    expect(neverProblems(res.text)).toEqual([]);
    const ledger = await getAs(w, pageOf(CASE, LEDGER.id));
    expect(mainText(ledger.text)).not.toContain("Sent on");
  });

  it("DR4: a cut text says so above the text, and an uncut one does not", async () => {
    const w = await world();
    const cut = mainOf((await getAs(w, pageOf(CASE, EMAIL.id))).text);
    const sentence = "This is the start of the message: the rest was not loaded.";
    expect(DOCUMENT_WORDS.truncated).toBe(sentence);
    expect(cut.indexOf(sentence)).toBeGreaterThan(-1);
    expect(cut.indexOf(sentence)).toBeLessThan(cut.indexOf('id="document-text"'));
    expect(mainOf((await getAs(w, pageOf(CASE, LEDGER.id))).text)).not.toContain(sentence);
  });

  it("DR5: a picture is an <img> named for what it is, from the forwarder's path, which answers with the file; none with no file", async () => {
    const w = await world();
    const res = await getAs(w, pageOf(CASE, PHOTO.id));
    expect(fileProblems(res.text, PHOTO)).toEqual([]);
    expect(DOCUMENT_WORDS.picture).toBe("A picture from the document");
    expect(markProblems(res.text, PHOTO)).toEqual([]);
    const src = fileOn(res.text).file?.src as string;
    const file = await getAs(w, src).buffer(true).parse((r, done) => {
      const parts: Buffer[] = [];
      r.on("data", (c: Buffer) => parts.push(c));
      r.on("end", () => done(null, Buffer.concat(parts)));
    });
    expect(file.status).toBe(200);
    expect(file.headers["content-type"]).toBe("image/png");
    expect(Buffer.compare(file.body as Buffer, PNG)).toBe(0);
    const gone = await getAs(w, pageOf(CASE, NO_FILE.id));
    expect(fileProblems(gone.text, NO_FILE)).toEqual([]);
    expect(fileOn(gone.text).kinds).toEqual([]);
  });

  it("DR6: a film is a <video controls> named for what it is, from the forwarder's path, never an <img>", async () => {
    const w = await world();
    const res = await getAs(w, pageOf(CASE, FILM.id));
    expect(fileProblems(res.text, FILM)).toEqual([]);
    expect(DOCUMENT_WORDS.film).toBe("A film from the document");
  });

  it("DR7: a file of any other kind is a link to it, and is not shown", async () => {
    const w = await world();
    for (const d of [KEPT, ODD]) {
      const res = await getAs(w, pageOf(CASE, d.id));
      expect(fileProblems(res.text, d), d.id).toEqual([]);
    }
    expect(DOCUMENT_WORDS.openFile).toBe("Open the document's file");
  });

  it("DR8: a document with no title is headed in words, never by its id", async () => {
    const w = await world();
    const res = await getAs(w, pageOf(CASE, UNTITLED.id));
    expect(headings(mainOf(res.text))[0]).toEqual({ level: 1, text: "A document with no title" });
    expect(mainText(res.text)).not.toContain(UNTITLED.id);
    expect(/<title>([^<]*)<\/title>/.exec(res.text)?.[1]).toContain("A document with no title");
  });

  it("DR9: hidden, in another case, missing, no level, another unit, no right: the very page of a path nothing serves, after one call", async () => {
    const w = await world();
    const unknown = await getAs(w, NOWHERE);
    expect(unknown.status).toBe(404);
    const refused: [string, string][] = [
      [CASE, SECRET.id],
      [CASE, ELSEWHERE.id],
      [CASE, "d-no-such-document"],
      [CASE, PERSON.id],
      ["c-unshared", UNSHARED.id],
      ["c-away", AWAY.id],
      ["c-no-such-case", LEDGER.id],
    ];
    for (const [caseId, documentId] of refused) {
      w.conduit.calls.splice(0);
      const res = await getAs(w, pageOf(caseId, documentId));
      expect(refusalProblems(res, unknown), `${caseId} ${documentId}`).toEqual([]);
      expect(calls(w.conduit), `${caseId} ${documentId}`).toEqual([`GET ${readerOf(caseId, documentId)}`]);
    }
    const unrighted = await world({ rights: [] });
    const res = await getAs(unrighted, pageOf(CASE, LEDGER.id));
    expect(refusalProblems(res, await getAs(unrighted, NOWHERE))).toEqual([]);
    const odd = await world({ reader_answer: { status: 403, body: { detail: "this needs the viewer level on the case" } } });
    expect(refusalProblems(await getAs(odd, pageOf(CASE, LEDGER.id)), await getAs(odd, NOWHERE))).toEqual([]);
    const queries = [
      "",
      `?case=${CASE}`,
      `?document=${LEDGER.id}`,
      `?case=&document=${LEDGER.id}`,
      `?case=${CASE}&document=`,
      `?case=${CASE}&case=c-ferry&document=${LEDGER.id}`,
      `?case=${CASE}&document=${LEDGER.id}&document=${EMAIL.id}`,
      `?case=.&document=${LEDGER.id}`,
      `?case=..&document=${LEDGER.id}`,
      `?case=${CASE}&document=.`,
      `?case=${CASE}&document=..`,
      `?case=${CASE}&document=%2E%2E`,
    ];
    for (const query of queries) {
      w.conduit.calls.splice(0);
      const res2 = await getAs(w, `${PATH}${query}`);
      expect(refusalProblems(res2, unknown), query).toEqual([]);
      expect(calls(w.conduit), query).toEqual([]);
    }
  });

  it("DR10: the Conduit is asked once per render, as the person, nothing of the browser's, no write, nothing unsigned", async () => {
    const w = await world();
    await getAs(w, pageOf(CASE, LEDGER.id)).set("Origin", "http://example.invalid").set("Referer", "http://example.invalid/x");
    expect(callProblems(calls(w.conduit), [`GET ${readerOf(CASE, LEDGER.id)}`])).toEqual([]);
    for (const call of w.conduit.calls) {
      expect(call.headers["authorization"]).toBe(`Bearer ${w.reader.token}`);
      for (const header of ["cookie", "origin", "referer", "x-csrf-token", "x-forwarded-for"]) expect(call.headers[header], header).toBeUndefined();
    }
    w.conduit.calls.splice(0);
    const unsigned = await request(w.app).get(pageOf(CASE, LEDGER.id));
    expect(unsigned.status).toBe(302);
    expect(unsigned.headers["location"]).toBe("/session/sign-in");
    const unknown = await getAs(w, NOWHERE);
    for (const method of ["post", "put", "patch", "delete"] as const) {
      const res = await request(w.app)[method](pageOf(CASE, LEDGER.id)).set("Cookie", w.cookie).set("X-CSRF-Token", w.csrf).type("form").send({ _csrf: w.csrf });
      expect(res.status, method).toBe(unknown.status);
    }
    expect(calls(w.conduit)).toEqual([]);
  });

  it("DR11: a failed read draws nothing of the document (502); an ended session says to sign in again (401)", async () => {
    const failures: WorldOptions[] = [
      // Any 4xx but a refusal (403, 404) or a 401 says nothing of the document: could not be read, never "not found".
      { reader_answer: { status: 429, body: { detail: "slow down" } } },
      { reader_answer: { status: 409, body: { detail: "conflict" } } },
      { reader_answer: { status: 422, body: { detail: [] } } },
      { reader_answer: { status: 500, body: { detail: "boom" } } },
      { reader_answer: { status: 503, body: { detail: "down" } } },
      { reader_answer: { status: 200, body: "not json" } },
      { reader_no_answer: true },
      { conduitUrl: await closedAddress() },
    ];
    for (const options of failures) {
      const w = await world(options);
      const res = await getAs(w, pageOf(CASE, LEDGER.id));
      expect(res.status, JSON.stringify(options)).toBe(502);
      expect(mainText(res.text)).toContain(DOCUMENT_WORDS.unreadable.replace(/&#39;/g, "'"));
      expect(failedProblems(res.text)).toEqual([]);
      expect(mainText(res.text)).not.toContain("Quay ledger note");
    }
    const ended = unescape(refusalWords(401, undefined, ""));
    for (const options of [{ unknownBearer: true }, { reader_answer: { status: 401, body: { detail: "Not authenticated" } } }] as WorldOptions[]) {
      const w = await world(options);
      const res = await getAs(w, pageOf(CASE, LEDGER.id));
      expect(res.status, JSON.stringify(options)).toBe(401);
      expect(mainText(res.text)).toContain(ended);
    }
  });

  it("DR12: a body missing any field the route's models send, of the wrong shape, or with a span the page cannot place, is could not be read", async () => {
    expect(viewOf(censusBody())).toBeDefined();
    const models = Object.keys(REQUIRED) as (keyof typeof REQUIRED)[];
    expect([...models].sort()).toEqual(["DocumentReaderView", "MessageSpan"]);
    let tried = 0;
    for (const model of models) {
      for (const field of REQUIRED[model]) {
        expect(viewOf(withField(model, field, undefined)), `${model}.${field} removed`).toBeUndefined();
        expect(viewOf(withField(model, field, { wrong: true })), `${model}.${field} of the wrong shape`).toBeUndefined();
        tried += 1;
      }
    }
    expect(tried).toBe(17);
    const wrong: [string, string, unknown][] = [
      ["DocumentReaderView", "title", 7],
      ["DocumentReaderView", "text", null],
      ["DocumentReaderView", "truncated", "yes"],
      ["DocumentReaderView", "spans", {}],
      ["DocumentReaderView", "spans", [null]],
      ["DocumentReaderView", "sent_at", "soon"],
      ["DocumentReaderView", "sent_at", 0],
      ["DocumentReaderView", "media_kind", 5],
      ["DocumentReaderView", "has_file", "true"],
      ["DocumentReaderView", "document_id", null],
      ["DocumentReaderView", "sender_id", 9],
      ["MessageSpan", "start", -1],
      ["MessageSpan", "start", 1.5],
      ["MessageSpan", "start", "0"],
      ["MessageSpan", "provenance_state", "confirmed"],
      ["MessageSpan", "entity_type", null],
      ["MessageSpan", "node_id", 3],
    ];
    for (const [model, field, value] of wrong) {
      expect(viewOf(withField(model, field, value)), `${model}.${field} = ${JSON.stringify(value)}`).toBeUndefined();
    }
    // Spans out of the Conduit's order (by their start), and a span that ends where it starts.
    const reversed = censusBody();
    reversed.spans = [reversed.spans[1] as Record<string, unknown>, reversed.spans[0] as Record<string, unknown>];
    expect(viewOf(reversed)).toBeUndefined();
    // A span whose place is not in the text (past its end, or ending where it starts) is no fault of the body: the real route can send
    // one. It marks nothing, keeps its row, said in words, and the page says so above the text.
    for (const end of [999, 0]) {
      const view = viewOf(withField("MessageSpan", "end", end));
      expect(view, `end ${end}`).toBeDefined();
      expect(view?.someNotPlaced, `end ${end}`).toBe(true);
      expect(view?.rows[0]?.lines, `end ${end}`).toBeUndefined();
      expect(view?.pieces.filter((p) => p.marked).map((p) => p.lines.join("\n")), `end ${end}`).toEqual(["Brook"]);
    }
    expect(viewOf(censusBody())?.someNotPlaced).toBe(false);
    const w = await world();
    const stale = await getAs(w, pageOf(CASE, STALE.id));
    expect(stale.status).toBe(200);
    expect(markProblems(stale.text, STALE)).toEqual([]);
    expect(drawnText(stale.text)?.marks).toEqual(["Ada"]);
    expect(tableOf(stale.text)?.rows.map((r) => r.words)).toEqual(["Ada", "Not in the text as it is now", "Not in the text as it is now"]);
    // A span's end is counted in characters as the Conduit counts them: one past a character outside the basic plane is still inside.
    const astral = censusBody();
    astral["text"] = "📦ab";
    astral["spans"] = [{ start: 0, end: 3, node_id: "n-a", entity_type: "Thing", provenance_state: "asserted" }];
    expect(viewOf(astral)).toBeDefined();
    expect(viewOf(astral)?.rows[0]?.lines).toEqual(["📦ab"]);
    astral["spans"] = [{ start: 0, end: 4, node_id: "n-a", entity_type: "Thing", provenance_state: "asserted" }];
    expect(viewOf(astral)?.rows[0]?.lines).toBeUndefined();
    for (const top of [null, {}, "x", [], [null]]) expect(viewOf(top), JSON.stringify(top)).toBeUndefined();
    // And through the service: one missing field of each model is the 502 page.
    for (const [model, field] of [["DocumentReaderView", "spans"], ["MessageSpan", "provenance_state"]] as const) {
      expect((await drawn(withField(model, field, undefined))).status, `${model}.${field}`).toBe(502);
    }
  });

  it("DR13: no graph id is in the page, in any text or attribute", async () => {
    const w = await world();
    for (const d of [LEDGER, OVERLAP, EMAIL, PHOTO, FILM, KEPT, ODD, UNTITLED, MARKUP, STALE]) {
      const res = await getAs(w, pageOf(CASE, d.id));
      expect(res.status, d.id).toBe(200);
      expect(neverProblems(res.text), d.id).toEqual([]);
    }
  });

  it("DR14: a title, a text and a type that look like markup are drawn as text", async () => {
    const w = await world();
    const res = await getAs(w, pageOf(CASE, MARKUP.id));
    expect(headings(mainOf(res.text))[0]?.text).toBe("<b>Bold</b> & co");
    expect(markProblems(res.text, MARKUP)).toEqual([]);
    expect(mainOf(res.text)).not.toMatch(/<b>|<script>alert|<img src=x|<i>Type/);
    expect(scriptsOffProblems(res.text)).toEqual([]);
  });

  it("DR15: the forwarder's answer for the file carries nosniff and the file's own content type", async () => {
    const w = await world();
    for (const d of [PHOTO, FILM, KEPT, ODD]) {
      const res = await getAs(w, fileOf(CASE, d.id)).buffer(true);
      expect(res.status, d.id).toBe(200);
      expect(res.headers["x-content-type-options"], d.id).toBe("nosniff");
      expect(res.headers["content-type"], d.id).toContain(d.file?.type as string);
    }
  });

  it("DR16: the page is whole in structure, read-only, scripts off, and its stops come in order", async () => {
    const w = await world();
    const stops = (html: string): (string | undefined)[] => focusable(html).map((s) => s.href ?? `${s.tag}: ${s.text}`);
    const back = `/cases?case=${CASE}`;
    for (const d of [LEDGER, OVERLAP, EMAIL, PHOTO, FILM, KEPT, UNTITLED, MARKUP]) {
      const res = await getAs(w, pageOf(CASE, d.id));
      expect(structureProblems(res.text), d.id).toEqual([]);
      expect(scriptsOffProblems(res.text), d.id).toEqual([]);
      expect(res.text).toMatch(/<script type="application\/json" id="page-data"[^>]*>\{"page":"document"\}<\/script>/);
    }
    expect(stops((await getAs(w, pageOf(CASE, LEDGER.id))).text)).toEqual(["#main", "button: Sign out", back, "/"]);
    expect(stops((await getAs(w, pageOf(CASE, PHOTO.id))).text)).toEqual(["#main", "button: Sign out", back, "/"]);
    expect(stops((await getAs(w, pageOf(CASE, FILM.id))).text)).toEqual(["#main", "button: Sign out", `video: ${DOCUMENT_WORDS.film}`, back, "/"]);
    expect(stops((await getAs(w, pageOf(CASE, KEPT.id))).text)).toEqual(["#main", "button: Sign out", fileOf(CASE, KEPT.id), back, "/"]);
    const ledger = (await getAs(w, pageOf(CASE, LEDGER.id))).text;
    expect(focusable(ledger).map((s) => s.text).slice(2)).toEqual([DOCUMENT_WORDS.toCase, DOCUMENT_WORDS.back]);
    expect(headings(mainOf(ledger)).map((h) => h.level)).toEqual([1, 2, 2]);
  });

  it("DR17: every field of the two models is drawn or named as left out; a drawn field changes the page and a left-out one does not", async () => {
    expect(await censusProblems(CENSUS)).toEqual([]);
  });

  it("DR18: the GOV.UK tree serves the page and the Default tree does not; the lists name it; its words are its own and British", async () => {
    const w = await world({ tree: "default" });
    const unknown = await getAs(w, NOWHERE);
    const res = await getAs(w, pageOf(CASE, LEDGER.id));
    expect(res.status).toBe(404);
    expect(withoutNonce(res.text)).toBe(withoutNonce(unknown.text));
    expect(calls(w.conduit)).toEqual([]);
    const page = PAGES.find((p) => p.path === PATH);
    expect(page?.id).toBe("documents");
    expect(page?.trees).toEqual(["govuk"]);
    expect(page?.methods).toEqual(["GET"]);
    expect(read(PAGES_DIR, "tree-govuk", "routes.yaml")).toMatch(/^ {2}- \/cases\/document$/m);
    const sources = sourcesOfThePage();
    for (const s of sources) expect([...withoutComments(s.text).matchAll(new RegExp(AMERICAN.source, "gi"))].map((m) => m[0]), s.name).toEqual([]);
    expect(choosingProblems(sources)).toEqual([]);
  });

  describe("DR19: each check is red against the real page with one thing changed", () => {
    it("DR19: the marks' check fails for a proposed span drawn as confirmed, a span shifted, text doubled, a mark split, a hidden span drawn", async () => {
      const w = await world();
      const real = (await getAs(w, pageOf(CASE, LEDGER.id))).text;
      expect(markProblems(real, LEDGER)).toEqual([]);
      const stale = (await getAs(w, pageOf(CASE, STALE.id))).text;
      expect(markProblems(stale, STALE)).toEqual([]);
      const overlap = (await getAs(w, pageOf(CASE, OVERLAP.id))).text;
      expect(markProblems(overlap, OVERLAP)).toEqual([]);
      const plants: [string, string, Doc][] = [
        ["a proposed span drawn as confirmed", real.replace(HOW.inferred, HOW.asserted), LEDGER],
        ["a span marked one character late", real.replace("<mark>Ada Quill</mark> ", "A<mark>da Quill </mark>"), LEDGER],
        ["a span's words doubled", real.replace("<mark>Ada Quill</mark>", "<mark>Ada Quill</mark>Ada Quill"), LEDGER],
        ["a span the page was not sent drawn", real.replace("Brook Vale", "<mark>Brook Vale</mark>"), LEDGER],
        ["a span whose place is not in the text left unsaid", stale.replace(DOCUMENT_WORDS.someNotPlaced, ""), STALE],
        ["a span whose place is not in the text drawn as other words", stale.replace(`<th scope="row">${DOCUMENT_WORDS.notInText}</th>`, '<th scope="row">board.</th>'), STALE],
        ["a row of the table dropped", real.replace(/<tr><th scope="row">Harbour Board<\/th>[\s\S]*?<\/tr>/, ""), LEDGER],
        ["overlapping spans each marked, the overlap doubled", overlap.replace("<mark>Harbour Board</mark>", "<mark>Harbour Board</mark><mark>Board</mark>"), OVERLAP],
        ["touching spans joined", overlap.replace("<mark>Ada</mark><mark>Quill</mark>", "<mark>AdaQuill</mark>"), OVERLAP],
        ["a line break lost", overlap.replace("<br>", " "), OVERLAP],
      ];
      for (const [label, html, d] of plants) {
        expect(html, label).not.toBe(d === LEDGER ? real : d === STALE ? stale : overlap);
        expect(markProblems(html, d), label).not.toEqual([]);
      }
    });

    it("DR19: the file's check fails for a picture inlined, a film as a picture, any file embedded, a file drawn with none, another address", async () => {
      const w = await world();
      const photo = (await getAs(w, pageOf(CASE, PHOTO.id))).text;
      const film = (await getAs(w, pageOf(CASE, FILM.id))).text;
      const kept = (await getAs(w, pageOf(CASE, KEPT.id))).text;
      const gone = (await getAs(w, pageOf(CASE, NO_FILE.id))).text;
      const src = fileOf(CASE, PHOTO.id);
      expect(fileProblems(photo, PHOTO)).toEqual([]);
      const plants: [string, string, Doc][] = [
        ["a picture inlined as data:", photo.replace(`src="${src}"`, `src="data:image/png;base64,${PNG.toString("base64")}"`), PHOTO],
        ["a film drawn as a picture", film.replace(/<video\b[^>]*>[\s\S]*?<\/video>/, `<img src="${fileOf(CASE, FILM.id)}" alt="${DOCUMENT_WORDS.film}">`), FILM],
        ["a film without its controls", film.replace(" controls", ""), FILM],
        ["a kept text embedded", kept.replace(/<p><a href="\/v1\/[^"]*">[^<]*<\/a><\/p>/, `<object data="${fileOf(CASE, KEPT.id)}"></object>`), KEPT],
        ["a picture for a document with no file", gone.replace("</h1>", `</h1><img src="${fileOf(CASE, NO_FILE.id)}" alt="${DOCUMENT_WORDS.picture}">`), NO_FILE],
        ["the picture from the Conduit's own address", photo.replace(`src="${src}"`, `src="http://conduit.invalid${src}"`), PHOTO],
        ["the picture named by its title", photo.replace(`alt="${DOCUMENT_WORDS.picture}"`, 'alt="Gate photograph"'), PHOTO],
      ];
      for (const [label, html, d] of plants) {
        expect(fileProblems(html, d), label).not.toEqual([]);
      }
    });

    it("DR19: the refusal's check fails for its own words, the 403 passed through; the calls' for a second read; the failure's for an empty text", async () => {
      const w = await world();
      const unknown = await getAs(w, NOWHERE);
      const refused = await getAs(w, pageOf(CASE, SECRET.id));
      expect(refusalProblems(refused, unknown)).toEqual([]);
      expect(refusalProblems({ status: 404, text: refused.text.replace("That page could not be found.", "You cannot see this document.") }, unknown)).not.toEqual([]);
      expect(refusalProblems({ status: 403, text: refused.text }, unknown)).not.toEqual([]);
      expect(neverProblems(refused.text.replace("</main>", "<p>document_not_found</p></main>"))).not.toEqual([]);
      const one = `GET ${readerOf(CASE, LEDGER.id)}`;
      expect(callProblems([one, one], [one])).not.toEqual([]);
      const failedWorld = await world({ reader_answer: { status: 500, body: {} } });
      const failed = (await getAs(failedWorld, pageOf(CASE, LEDGER.id))).text;
      expect(failedProblems(failed)).toEqual([]);
      expect(failedProblems(failed.replace('<p role="alert">', "<p>"))).not.toEqual([]);
      expect(failedProblems(failed.replace("</h1>", '</h1><p id="document-text"></p>'))).not.toEqual([]);
    });

    it("DR19: the never-list fails for a sender's id or a data-node; the structure for a control or a skipped heading; scripts off for a script", async () => {
      const w = await world();
      const email = (await getAs(w, pageOf(CASE, EMAIL.id))).text;
      expect(neverProblems(email)).toEqual([]);
      expect(neverProblems(email.replace("Sent on", `Sent by ${EMAIL.sender_id as string} on`))).not.toEqual([]);
      expect(neverProblems(email.replace("<mark>", '<mark data-node="n-berth-6">'))).not.toEqual([]);
      expect(neverProblems(email.replace("</main>", `<a href="/x?e=${EMAIL.edge_id as string}">x</a></main>`))).not.toEqual([]);
      const ledger = (await getAs(w, pageOf(CASE, LEDGER.id))).text;
      expect(structureProblems(ledger.replace("</h1>", '</h1><form method="post" action="/x"><button>Mark</button></form>'))).not.toEqual([]);
      expect(structureProblems(ledger.replace("</h1>", "</h1><h3>Skipped</h3>"))).not.toEqual([]);
      expect(structureProblems(ledger.replace('scope="row"', ""))).not.toEqual([]);
      expect(structureProblems(ledger.replace(/<caption[^>]*>[^<]*<\/caption>/, ""))).not.toEqual([]);
      expect(focusable(ledger.replace('<a class="skip-link" href="#main">Skip to main content</a>', "")).map((s) => s.href)[0]).not.toBe("#main");
      expect(scriptsOffProblems(ledger.replace("</main>", '<script src="/x.js"></script></main>'))).not.toEqual([]);
      expect(scriptsOffProblems(ledger.replace("<mark>", '<mark style="color: red">'))).not.toEqual([]);
      expect(scriptsOffProblems(ledger.replace("<a ", '<a onclick="x()" '))).not.toEqual([]);
      // Markup written unescaped: the real page's escaped text given back raw is seen by the same checks.
      const markup = (await getAs(w, pageOf(CASE, MARKUP.id))).text;
      // (The span marks "<script>", so the anchor is the text after it; the plant must change the page, or it proves nothing.)
      const raw = markup.replace("&lt;img src=x onerror=y&gt;", "<img src=x onerror=y>");
      expect(raw).not.toBe(markup);
      expect(scriptsOffProblems(raw)).not.toEqual([]);
    });

    it("DR19: the census fails for a left-out field claimed as drawn, and a drawn field claimed as left out", async () => {
      const moved = (model: keyof typeof CENSUS, field: string, to: "drawn" | "left"): Census => {
        const { drawn: d, left: l } = CENSUS[model];
        const without = (list: readonly string[]): string[] => list.filter((f) => f !== field);
        return { ...CENSUS, [model]: to === "drawn" ? { drawn: [...d, field], left: without(l) } : { drawn: without(d), left: [...l, field] } };
      };
      expect(await censusProblems(moved("DocumentReaderView", "sender_id", "drawn"))).toEqual(["DocumentReaderView.sender_id is drawn but changes nothing"]);
      expect(await censusProblems(moved("MessageSpan", "node_id", "drawn"))).toEqual(["MessageSpan.node_id is drawn but changes nothing"]);
      expect(await censusProblems(moved("MessageSpan", "provenance_state", "left"))).toEqual(["MessageSpan.provenance_state is left out but changes the page"]);
      expect(await censusProblems(moved("DocumentReaderView", "truncated", "left"))).toEqual(["DocumentReaderView.truncated is left out but changes the page"]);
    });

    it("DR19: the source checks fail for a filter, a sort or a cut in the page's code", () => {
      const sources = sourcesOfThePage();
      expect(choosingProblems(sources)).toEqual([]);
      const planted = (name: string, change: (text: string) => string): { name: string; text: string }[] => sources.map((s) => (s.name === name ? { ...s, text: change(s.text) } : s));
      expect(choosingProblems(planted("server/views/documentWords.ts", (t) => `${t}\nconst x = [].filter(Boolean);\n`))).not.toEqual([]);
      expect(choosingProblems(planted("server/views/documentWords.ts", (t) => `${t}\nconst y = "".slice(0, 4000);\n`))).not.toEqual([]);
      expect(choosingProblems(planted("tree-govuk/document.njk", (t) => t.replace("in view.rows %}", 'in view.rows | sort(attribute="type") %}')))).not.toEqual([]);
      expect(choosingProblems(planted("tree-govuk/document.njk", (t) => t.replace("{{ line }}", "{{ line | truncate(40) }}")))).not.toEqual([]);
    });

    it("DR19: the fixture Conduit refuses what the real routes refuse, in their order", async () => {
      const w = await world({ rights: [] });
      const ask = async (path: string, init: RequestInit = {}): Promise<{ status: number; body: unknown }> => {
        const res = await fetch(`${w.conduit.url}${path}`, init);
        return { status: res.status, body: await res.json() };
      };
      const as = { headers: { Authorization: `Bearer ${w.reader.token}` } };
      const ledger = readerOf(CASE, LEDGER.id);
      expect(await ask(ledger)).toEqual({ status: 401, body: { detail: "Not authenticated" } });
      expect(await ask(ledger, { headers: { Authorization: "Bearer someone-else" } })).toEqual({ status: 401, body: { detail: UNKNOWN_BEARER } });
      expect(await ask(`${ledger}?access_token=${w.reader.token}`)).toEqual({ status: 401, body: { detail: "Not authenticated" } });
      expect(await ask(ledger, { method: "POST", ...as })).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
      expect(await ask(fileOf(CASE, PHOTO.id), { method: "DELETE" })).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
      // Routes the real Conduit serves under a case and the fixture does not model: never a 404 the real router would not give.
      expect((await ask(`/v1/investigations/${CASE}/documents/${LEDGER.id}/designations`, { method: "POST", ...as })).status).toBe(500);
      expect((await ask(`/v1/investigations/${CASE}`, as)).status).toBe(500);
      expect(await ask("/v1/investigation", as)).toEqual({ status: 404, body: { detail: "Not Found" } });
      // The right is checked before the case's gate, as the route-level dependency runs first.
      expect(await ask(readerOf("c-no-such-case", LEDGER.id), as)).toEqual({ status: 403, body: RIGHT_REFUSAL });
      expect(await ask(ledger, as)).toEqual({ status: 403, body: RIGHT_REFUSAL });
      const w2 = await world();
      const as2 = { headers: { Authorization: `Bearer ${w2.reader.token}` } };
      const ask2 = async (path: string): Promise<{ status: number; body: unknown }> => {
        const res = await fetch(`${w2.conduit.url}${path}`, as2);
        return { status: res.status, body: res.headers.get("content-type")?.includes("json") ? await res.json() : null };
      };
      for (const [caseId, documentId] of [["c-unshared", UNSHARED.id], ["c-away", AWAY.id], ["c-no-such-case", LEDGER.id]]) {
        expect(await ask2(readerOf(caseId as string, documentId as string)), caseId).toEqual({ status: 404, body: NOT_FOUND_CASE });
      }
      for (const documentId of [SECRET.id, ELSEWHERE.id, "d-no-such-document", PERSON.id]) {
        expect(await ask2(readerOf(CASE, documentId)), documentId).toEqual({ status: 404, body: NOT_FOUND_DOCUMENT });
        expect(await ask2(fileOf(CASE, documentId)), `${documentId} file`).toEqual({ status: 404, body: NOT_FOUND_DOCUMENT });
      }
      expect(await ask2(fileOf(CASE, NO_FILE.id))).toEqual({ status: 404, body: NOT_FOUND_DOCUMENT });
      expect(await ask2(fileOf(CASE, LEDGER.id))).toEqual({ status: 404, body: NOT_FOUND_DOCUMENT });
      // A span whose node the reader may not see is left out of the answer, and every field of the model is sent.
      const sent = (await ask2(ledger)).body as { spans: { node_id: string }[] } & Record<string, unknown>;
      expect(sent.spans.map((s) => s.node_id)).toEqual(["n-ada-1", "n-board-2", "n-pier-3", "n-signed-5"]);
      expect(Object.keys(sent).sort()).toEqual([...REQUIRED.DocumentReaderView].sort());
    });
  });
});
