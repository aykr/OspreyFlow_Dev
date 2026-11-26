/**
 * Making, sharing and deleting a drawing board on the GOV.UK pages, as scripts-off forms (slice GG4c; ADR-143 decision 5; ADR-152
 * decisions 1, 4, 5, 6 and 12; FUNCTIONS row `drawing-boards`; scenario BD18 onward of `spec/08_ACCEPTANCE_SCENARIOS.md`, written first
 * from the owner's rulings of 26 November 2026 on GG4c's draft: every proposal (a), no unshare route).
 * `tests/glass_trees/test_govuk_boards_scenario.py` holds the scenario and this file in step.
 *
 * The proof is the real service started for the GOV.UK tree, the real page list and a fixture Conduit that refuses a write as the real
 * routes do, in their order (`boardsConduit.ts`: the rights, the case's gate, the body with `extra="forbid"`, the board, its creator),
 * records every call with its body, and records one audit row for each write it carries out. The words asserted are written here as the
 * owner ruled them, not read from the page's own module, so a changed word is a failure.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - the form offered without both rights, or not offered with both, or a second read made for it                         -> BD18
 *  - a make that sends more than the name and the start (`_csrf` among them), renders on the post, or lands elsewhere    -> BD19
 *  - a name empty or over 200 characters sent, its words lost, or the Conduit's 422 detail shown                         -> BD20
 *  - a refusal for the right or the level said in other words than the page's own, or with the Conduit's                 -> BD21
 *  - a share that renders on the post (a reload sends it again), or offered without saying it cannot be undone           -> BD22
 *  - a share or delete offered to a reader who may not draw on the board; a non-creator told other than "not found"      -> BD23
 *  - a delete sent before its confirmation, a banner for no delete, or a banner shown again on reload                    -> BD24
 *  - a write carried out without this session's anti-forgery token                                                       -> BD25
 *  - a banner or a redirect after a failed write; an ended session not said                                              -> BD26
 *  - a write that asks the Conduit more than once (a read-back among them)                                               -> BD27
 *  - a control that is not a native one in the page's order, or a field without its label                                -> BD28
 *  - a write that needs a script                                                                                          -> BD29
 *  - a fixture that grants what the real route refuses, or refuses in another order                                       -> BD30
 * Every planted fault is the real page or the real calls with one thing changed, run through the same function that finds nothing in
 * the real one (BD31, rule 15).
 */
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

import type { Express } from "express";
import { afterEach, describe, expect, it } from "vitest";

import { createApp } from "../../server/app.js";
import { PAGES } from "../../server/pageList.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { testClock } from "../support/clock.js";
import { cookieFrom, csrfFromPage, request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { bearer, providerFor, textOf } from "../support/studioWorld.js";
import { LEVEL_REFUSAL, NOT_CREATOR, NOT_FOUND_BOARD, NOT_FOUND_CASE, boardsConduit, rightRefusal } from "./boardsConduit.js";
import type { Board, BoardsConduit, BoardsConduitOptions, Call, Item, Reader } from "./boardsConduit.js";

// ------------------------------------------------------------------------------------------------ the owner's words

const CANNOT = "You cannot make boards in this case";
const DELETED = "The board was deleted. What was drawn on it stays in the case.";
const ASK_DELETE = "Delete this board?";
const STAYS = "What was drawn on it stays in the case.";
const SHARE = "Share with the case";
const NOT_UNDONE = "cannot be undone";
const NEW_BOARD = "New drawing board";
const PROBLEM = "There is a problem";

// ------------------------------------------------------------------------------------------------ the world

const PATH = "/cases/boards";
const NOWHERE = "/nothing-is-served-here";
const CASE = "c-harbour";
const UNIT = "harbour-unit";
const ALEX = "acct-alex";
const BLAKE = "acct-blake";
const listOf = (caseId = CASE): string => `${PATH}?case=${encodeURIComponent(caseId)}`;
const boardOfPath = (boardId: string, caseId = CASE): string => `${listOf(caseId)}&board=${encodeURIComponent(boardId)}`;
const confirmOf = (boardId: string): string => `${boardOfPath(boardId)}&delete=confirm`;

const CASES = [
  { id: CASE, owning_unit: UNIT },
  { id: "c-other", owning_unit: UNIT },
  { id: "c-unshared", owning_unit: UNIT },
];

const ITEMS: Item[] = [
  {
    id: "d-tall",
    type: "Person",
    properties: {},
    marking: "OFFICIAL",
    drawn: { label: "Tall man", grading: { scheme: "5x5x5", source: "B", intelligence: "2", handling: "1" }, source_note: "Seen from the wall", source_document: null, asserted_by: ALEX, item_id: "i-tall", board_id: "b-quay" },
  },
];

const BOARDS: Board[] = [
  { id: "b-quay", case_id: CASE, name: "Quay sketch", created_by: ALEX, created_at: "2026-11-10T09:30:00Z", shared: false, references: [], drawn: ["d-tall"] },
  { id: "b-shift", case_id: CASE, name: "Night shift", created_by: BLAKE, created_at: "2026-10-21T22:15:00Z", shared: true, references: [], drawn: [] },
  { id: "b-blake", case_id: CASE, name: "Blake's private board", created_by: BLAKE, created_at: "2026-10-22T08:00:00Z", shared: false, references: [], drawn: [] },
];

const conduits: BoardsConduit[] = [];
afterEach(async () => {
  while (conduits.length > 0) await conduits.pop()?.stop();
});

interface World {
  app: Express;
  conduit: BoardsConduit;
  options: BoardsConduitOptions;
  reader: Reader;
  cookie: string;
  csrf: string;
}

interface WorldOptions extends Partial<Omit<BoardsConduitOptions, "readers">> {
  rights?: string[];
  viewerCases?: string[];
  conduitUrl?: string;
  unknownBearer?: boolean;
}

const BOTH = ["investigate", "draw_on_boards"];

async function world(options: WorldOptions = {}): Promise<World> {
  const token = bearer();
  const { rights, viewerCases, conduitUrl, unknownBearer, ...rest } = options;
  const reader: Reader = { token, id: ALEX, unit: UNIT, rights: rights ?? BOTH, cases: [CASE, "c-other"], viewerCases: viewerCases ?? [], clearance: "OFFICIAL-SENSITIVE" };
  const conduitOptions: BoardsConduitOptions = { readers: unknownBearer === true ? [] : [reader], cases: CASES, boards: BOARDS, items: ITEMS.map((i) => ({ ...i })), links: [], ...rest };
  const conduit = await boardsConduit(conduitOptions);
  conduits.push(conduit);
  const app = createApp({
    store: new MemorySessionStore({ clock: testClock() }),
    identityProvider: providerFor(token),
    sessionSecret: generateSecret(48),
    pages: PAGES,
    tree: "govuk",
    forward: { conduitUrl: conduitUrl ?? conduit.url, bodyMaxBytes: 1024, uploadMaxBytes: 1024, upstreamTimeoutSeconds: 2 },
  });
  const { cookie, csrf } = await signInTo(app);
  conduit.calls.splice(0);
  return { app, conduit, options: conduitOptions, reader, cookie, csrf };
}

async function signInTo(app: Express): Promise<{ cookie: string; csrf: string }> {
  const res = await request(app).get("/session/sign-in");
  if (res.status !== 302) throw new Error(`sign-in answered ${res.status}`);
  const cookie = cookieFrom(res);
  const home = await request(app).get("/").set("Cookie", cookie);
  return { cookie, csrf: csrfFromPage(home.text) };
}

const getAs = (w: World, path: string) => request(w.app).get(path).set("Cookie", w.cookie);

/** A form posted as a browser posts it with no script: url-encoded, its anti-forgery token a field, no header of its own. */
const postAs = (w: World, path: string, fields: Record<string, string>) =>
  request(w.app).post(path).set("Cookie", w.cookie).type("form").send(new URLSearchParams(fields).toString());

const make = (w: World, name: string) => postAs(w, listOf(), { _csrf: w.csrf, action: "make", name });
const share = (w: World, boardId: string) => postAs(w, boardOfPath(boardId), { _csrf: w.csrf, action: "share" });
const remove = (w: World, boardId: string) => postAs(w, boardOfPath(boardId), { _csrf: w.csrf, action: "delete" });

const lines = (calls: readonly Call[]): string[] => calls.map((c) => `${c.method} ${c.url}`);
const writes = (calls: readonly Call[]): Call[] => calls.filter((c) => c.method !== "GET");
const base = (caseId = CASE): string => `/v1/investigations/${caseId}/boards`;
const RIGHTS_READ = "GET /v1/me/rights";

async function closedAddress(): Promise<string> {
  const server = createServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  await new Promise<void>((resolve) => server.close(() => resolve()));
  return `http://127.0.0.1:${port}`;
}

// ------------------------------------------------------------------------------------------------ reading a page

const strip = (html: string): string => html.replace(/<!--[\s\S]*?-->/g, "");
const unescape = (s: string): string => s.replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const attr = (tag: string, name: string): string | undefined => {
  const found = new RegExp(`\\s${name}="([^"]*)"`).exec(tag)?.[1];
  return found === undefined ? undefined : unescape(found);
};
const mainOf = (html: string): string => /<main\b[^>]*>([\s\S]*?)<\/main>/.exec(strip(html))?.[1] ?? "";
const mainText = (html: string): string => unescape(textOf(mainOf(html)));
const h1Of = (html: string): string => unescape(textOf(/<h1\b[^>]*>([\s\S]*?)<\/h1>/.exec(mainOf(html))?.[1] ?? ""));
const withoutNonce = (html: string): string => html.replace(/nonce="[^"]*"/g, 'nonce="N"');

interface Form {
  method: string;
  action: string;
  /** The hidden fields, by name. */
  hidden: Record<string, string>;
  inner: string;
}

/** The forms of the main landmark (the layout's sign-out is not among them). */
function formsOf(html: string): Form[] {
  return [...mainOf(html).matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/g)].map((found) => {
    const inner = found[2] as string;
    const hidden = Object.fromEntries(
      [...inner.matchAll(/<input\b([^>]*)>/g)].map((m) => m[1] as string).filter((a) => attr(a, "type") === "hidden").map((a) => [attr(a, "name") ?? "", attr(a, "value") ?? ""]),
    );
    return { method: attr(found[1] as string, "method") ?? "", action: attr(found[1] as string, "action") ?? "", hidden, inner };
  });
}
const formFor = (html: string, action: string): Form | undefined => formsOf(html).find((f) => f.hidden["action"] === action);

const linksOf = (html: string): { href: string; text: string }[] =>
  [...mainOf(html).matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)].map((m) => ({ href: attr(m[1] as string, "href") ?? "", text: unescape(textOf(m[2] as string)) }));

/** The names of the boards the list's table holds. */
const listed = (html: string): string[] => [...mainOf(html).matchAll(/<th scope="row"><a\b[^>]*>([\s\S]*?)<\/a><\/th>/g)].map((m) => unescape(textOf(m[1] as string)));

/** Every stop of the page, in its order: a link, a button, a field that is not hidden. */
function stops(html: string): string[] {
  const found: string[] = [];
  for (const m of strip(html).matchAll(/<(a|button)\b([^>]*)>([\s\S]*?)<\/\1>|<(input|select|textarea)\b([^>]*)>/g)) {
    const tag = (m[1] ?? m[4]) as string;
    const attrs = (m[2] ?? m[5]) as string;
    if (tag === "input" && attr(attrs, "type") === "hidden") continue;
    if (tag === "a" && attr(attrs, "href") === undefined) continue;
    found.push(tag === "input" ? `input: ${attr(attrs, "name") ?? ""}` : `${tag}: ${unescape(textOf(m[3] ?? ""))}`);
  }
  return found;
}

// ------------------------------------------------------------------------------------------------ the checks (BD31 plants on each)

/** What a make must send: one call, a POST to the case's boards, as the person, with the name and the start and nothing else. */
function makeProblems(calls: readonly Call[], name: string, token: string): string[] {
  const found: string[] = [];
  if (JSON.stringify(lines(calls)) !== JSON.stringify([`POST ${base()}`])) return [`the make asked ${JSON.stringify(lines(calls))}, not one POST ${base()}`];
  const call = calls[0] as Call;
  let body: unknown;
  try {
    body = JSON.parse(call.body);
  } catch {
    return ["the make's body is not JSON"];
  }
  if (JSON.stringify(body) !== JSON.stringify({ name, start: "blank" })) found.push(`the make sent ${call.body}`);
  if (call.headers["authorization"] !== `Bearer ${token}`) found.push("the make was not sent as the person");
  for (const header of ["cookie", "x-csrf-token", "origin", "referer"]) if (call.headers[header] !== undefined) found.push(`the make sent the browser's ${header}`);
  return found;
}

/** One write, one call: the write's own, and no other (no read-back, with the write's verb or any other). */
const oneCallProblems = (calls: readonly Call[], want: string): string[] =>
  JSON.stringify(lines(calls)) === JSON.stringify([want]) ? [] : [`the write asked ${JSON.stringify(lines(calls))}, not just ${want}`];

/** A write answered by post-then-redirect: a 303 to a GET, and nothing drawn on the POST (so a reload sends nothing again). */
const redirectProblems = (res: { status: number; headers: Record<string, unknown> }, to: string): string[] =>
  res.status === 303 && res.headers["location"] === to ? [] : [`the write answered ${res.status} to ${String(res.headers["location"])}, not 303 to ${to}`];

/** The GOV.UK error summary for the name, with the words kept in the field. */
function errorProblems(html: string, kept: string): string[] {
  const found: string[] = [];
  const main = mainOf(html);
  const summary = /<div class="govuk-error-summary"[^>]*>\s*<div role="alert">([\s\S]*?)<\/div>\s*<\/div>\s*<\/div>/.exec(main)?.[1];
  if (summary === undefined) return ["there is no GOV.UK error summary"];
  if (!/<h2 class="govuk-error-summary__title">\s*There is a problem\s*<\/h2>/.test(summary)) found.push("the summary has no title");
  if (!/<a href="#board-name">[^<]+<\/a>/.test(summary)) found.push("the summary does not link to the field");
  if (main.indexOf("govuk-error-summary") > main.indexOf("<h1")) found.push("the summary is not above the heading");
  if (!/<title>Error: /.test(html)) found.push("the title does not say there is an error");
  const field = /<input\b([^>]*\sid="board-name"[^>]*)>/.exec(main)?.[1];
  if (field === undefined) found.push("there is no field to correct");
  else if (attr(field, "value") !== kept) found.push(`the field holds ${JSON.stringify(attr(field, "value"))}, not the words typed`);
  if (/\smaxlength=|\srequired\b/.test(field ?? "")) found.push("the browser would cut or hold back the words before the page can say why");
  if (/string_too|extra_forbidden|"loc"|Input should|String should/.test(main)) found.push("the Conduit's detail is shown");
  return found;
}

/** The refusal for the right or the level: the page's own words, none of the Conduit's, and nothing said to have been done. */
function cannotProblems(res: { status: number; text: string }): string[] {
  const found: string[] = [];
  if (res.status !== 403) found.push(`the refusal answered ${res.status}`);
  if (!mainText(res.text).includes(CANNOT)) found.push("the refusal does not say the page's own words");
  for (const word of ["right_required", "draw_on_boards", "investigate", "editor access", "this account has", "not_the_boards_creator"]) {
    if (mainOf(res.text).replace(/<input type="hidden"[^>]*>/g, "").includes(word)) found.push(`the refusal says ${word}`);
  }
  if (mainText(res.text).includes("was deleted")) found.push("the refusal says something was deleted");
  return found;
}

const notFoundProblems = (res: { status: number; text: string }, unknown: { status: number; text: string }): string[] =>
  res.status === 404 && unknown.status === 404 && withoutNonce(res.text) === withoutNonce(unknown.text) ? [] : ["the refusal is not the page of a path nothing serves"];

/** Share and delete: offered only to a reader who may draw on the board. */
function noControlProblems(html: string): string[] {
  const found: string[] = [];
  if (formsOf(html).length > 0) found.push("a form is offered");
  if (linksOf(html).some((l) => l.href.includes("delete="))) found.push("a delete is offered");
  if (mainText(html).includes(SHARE)) found.push("a share is offered");
  return found;
}

/** The delete's banner, a GOV.UK notification banner with the ruled sentence. */
const hasBanner = (html: string): boolean =>
  /<div class="govuk-notification-banner govuk-notification-banner--success" role="alert"/.test(mainOf(html)) && mainText(html).includes(DELETED);

/** A failed write: said as not read with nothing changed, as an alert, and never as done. */
function failedProblems(res: { status: number; text: string; headers: Record<string, unknown> }): string[] {
  const found: string[] = [];
  if (res.status !== 502) found.push(`the failed write answered ${res.status}`);
  if (res.headers["location"] !== undefined) found.push("a failed write redirects");
  if (!/<p role="alert">[^<]*could not be read[^<]*nothing has changed/i.test(mainOf(res.text))) found.push("it does not say it could not be read and nothing has changed");
  if (/govuk-notification-banner|was deleted/.test(mainOf(res.text))) found.push("a failed write shows a success banner");
  return found;
}

/** Every thing that would stop a keyboard or a browser with no script: each form a POST (or none) to this page with this session's
 * token, each field labelled, each button a submit button in the tab order, no script, handler or inline style. */
function formProblems(html: string, csrf: string): string[] {
  const page = strip(html);
  const found: string[] = [];
  for (const form of formsOf(html)) {
    if (form.method !== "post") found.push(`a form with the method ${form.method}`);
    if (!form.action.startsWith(`${PATH}?case=`)) found.push(`a form to ${form.action}`);
    if (form.hidden["_csrf"] !== csrf) found.push("a form without this session's anti-forgery token");
    if (!/<button type="submit"[^>]*>[^<]+<\/button>/.test(form.inner)) found.push("a form with no submit button");
    for (const field of form.inner.matchAll(/<input\b([^>]*)>/g)) {
      const attrs = field[1] as string;
      if (attr(attrs, "type") === "hidden") continue;
      const id = attr(attrs, "id");
      if (id === undefined || !new RegExp(`<label\\b[^>]*\\sfor="${id}"`).test(form.inner)) found.push("a field with no label");
    }
  }
  for (const control of mainOf(page).matchAll(/<(button|input|select|textarea)\b([^>]*)>/g)) {
    const attrs = control[2] as string;
    if (/\sdisabled\b/.test(attrs)) found.push("a disabled control");
    if (attr(attrs, "tabindex") !== undefined) found.push("a control with its own tab stop");
  }
  if (/<(div|span)\b[^>]*\srole="button"/.test(page)) found.push("a thing made to look like a button");
  for (const s of page.matchAll(/<script\b([^>]*)>/g)) if (attr(s[1] as string, "type") !== "application/json") found.push("a script");
  if (/\son[a-z]+\s*=/i.test(page)) found.push("an event-handler attribute");
  if (/\sstyle\s*=|<style\b|javascript:/i.test(page)) found.push("an inline style or a javascript: address");
  return found;
}

// ------------------------------------------------------------------------------------------------ the cases

describe("making, sharing and deleting a drawing board on the GOV.UK tree (scenario BD)", () => {
  it("BD18: New drawing board is offered when the person's rights hold both, from one more read; without draw_on_boards it is not", async () => {
    const w = await world();
    const res = await getAs(w, listOf());
    expect(res.status).toBe(200);
    expect(lines(w.conduit.calls)).toEqual([`GET ${base()}`, RIGHTS_READ]);
    const form = formFor(res.text, "make");
    expect(form).toBeDefined();
    expect(form?.method).toBe("post");
    expect(form?.action).toBe(listOf());
    expect(form?.hidden).toEqual({ _csrf: w.csrf, action: "make" });
    expect(form?.inner).toMatch(/<label\b[^>]*for="board-name"[^>]*>\s*Board name\s*<\/label>/);
    expect(form?.inner).toMatch(/<input\b[^>]*id="board-name"[^>]*name="name"/);
    expect(mainText(res.text)).toContain(NEW_BOARD);
    // A case with no board offers it too, beside the sentence.
    const empty = await world({ boards: [] });
    const emptyPage = (await getAs(empty, listOf())).text;
    expect(mainText(emptyPage)).toContain("No boards in this case yet.");
    expect(formFor(emptyPage, "make")).toBeDefined();
    // Without the right to draw, no form, whatever the case level (case 3). A Viewer who holds the right is offered it (Q2 a): the
    // route refuses, and the refusal is said (BD21).
    const without = await world({ rights: ["investigate"] });
    const withoutPage = await getAs(without, listOf());
    expect(withoutPage.status).toBe(200);
    expect(formsOf(withoutPage.text)).toEqual([]);
    expect(mainText(withoutPage.text)).not.toContain(NEW_BOARD);
    expect(formFor((await getAs(await world({ viewerCases: [CASE] }), listOf())).text, "make")).toBeDefined();
    // A rights read that fails offers nothing and says so; one that says the session ended says to sign in again.
    for (const options of [{ rights_answer: { status: 500, body: {} } }, { rights_answer: { status: 200, body: { rights: "all" } } }, { rights_no_answer: true }] as WorldOptions[]) {
      const failed = await world(options);
      const page = await getAs(failed, listOf());
      expect(page.status, JSON.stringify(options)).toBe(200);
      expect(listed(page.text)).toEqual(["Quay sketch", "Night shift"]);
      expect(formsOf(page.text)).toEqual([]);
      expect(mainText(page.text)).toContain("Whether you can make a board here could not be checked just now.");
    }
    const ended = await world({ rights_answer: { status: 401, body: { detail: "Not authenticated" } } });
    const endedPage = await getAs(ended, listOf());
    expect(endedPage.status).toBe(401);
    expect(mainText(endedPage.text)).toMatch(/Sign in again/);
    // A refused list asks nothing more.
    const refused = await world();
    await getAs(refused, listOf("c-unshared"));
    expect(lines(refused.conduit.calls)).toEqual([`GET ${base("c-unshared")}`]);
  });

  it("BD19: making Supply routes sends one POST with its name and a blank start, then 303 to its board, listed, a reload sending nothing", async () => {
    const w = await world();
    const res = await make(w, "Supply routes");
    expect(redirectProblems(res, boardOfPath("b-made-1"))).toEqual([]);
    expect(makeProblems(w.conduit.calls, "Supply routes", w.reader.token)).toEqual([]);
    expect(w.conduit.audits).toEqual([{ action: "make_board", board_id: "b-made-1", start: "blank" }]);
    w.conduit.calls.splice(0);
    const board = await getAs(w, res.headers["location"] as string);
    expect(board.status).toBe(200);
    expect(h1Of(board.text)).toBe("Supply routes");
    await getAs(w, res.headers["location"] as string);
    expect(writes(w.conduit.calls)).toEqual([]);
    expect(listed((await getAs(w, listOf())).text)).toEqual(["Quay sketch", "Night shift", "Supply routes"]);
    // The words typed go as typed: quotes, an ampersand, and 200 characters counted as the route counts them (code points).
    for (const name of [`O'Hara & "Sons" <depot>`, "a".repeat(200), "\u{1F6A2}".repeat(200)]) {
      const one = await world();
      const answered = await make(one, name);
      expect(answered.status, name.slice(0, 20)).toBe(303);
      expect(makeProblems(one.conduit.calls, name, one.reader.token), name.slice(0, 20)).toEqual([]);
    }
    // A 201 the page cannot read: the board was made, so it goes to the case's boards, which show what there is.
    const odd = await world({ write_answer: { status: 201, body: { id: "../x" } } });
    expect(redirectProblems(await make(odd, "Supply routes"), listOf())).toEqual([]);
  });

  it("BD20: an empty name or one of 201 characters is the GOV.UK error summary with the words kept, and nothing is sent", async () => {
    for (const name of ["", "a".repeat(201), `${"b".repeat(150)}"<x>&'${"c".repeat(100)}`]) {
      const w = await world();
      const res = await make(w, name);
      expect(res.status, name.slice(0, 20)).toBe(422);
      expect(errorProblems(res.text, name), name.slice(0, 20)).toEqual([]);
      expect(lines(w.conduit.calls), name.slice(0, 20)).toEqual([]);
      const form = formFor(res.text, "make");
      expect(form?.action).toBe(listOf());
      expect(form?.hidden["_csrf"]).toBe(w.csrf);
      expect(linksOf(res.text).map((l) => l.href)).toContain(listOf());
    }
    // A post with no name at all is the same.
    const none = await world();
    const unnamed = await postAs(none, listOf(), { _csrf: none.csrf, action: "make" });
    expect(errorProblems(unnamed.text, "")).toEqual([]);
    expect(lines(none.conduit.calls)).toEqual([]);
    // Were the route to refuse the name (422 naming it), the same summary, with the words kept and none of its detail.
    const detail = { detail: [{ type: "string_too_long", loc: ["body", "name"], msg: "String should have at most 200 characters" }] };
    const w = await world({ write_answer: { status: 422, body: detail } });
    const res = await make(w, "Supply routes");
    expect(res.status).toBe(422);
    expect(errorProblems(res.text, "Supply routes")).toEqual([]);
    // A 422 about anything else is not the name's: the could-not-be-read page, never a wrong thing to correct.
    const other = await world({ write_answer: { status: 422, body: { detail: [{ type: "extra_forbidden", loc: ["body", "_csrf"], msg: "Extra inputs are not permitted" }] } } });
    expect(failedProblems(await make(other, "Supply routes"))).toEqual([]);
  });

  it("BD21: a refusal for the right or the level, for a make, a share or a delete posted by hand, is the page's own words", async () => {
    const bodies: string[] = [];
    for (const options of [{ rights: ["investigate"] }, { viewerCases: [CASE] }] as WorldOptions[]) {
      for (const [label, post, want] of [
        ["make", (w: World) => make(w, "Supply routes"), `POST ${base()}`],
        ["share", (w: World) => share(w, "b-quay"), `POST ${base()}/b-quay/share`],
        ["delete", (w: World) => remove(w, "b-quay"), `DELETE ${base()}/b-quay`],
      ] as const) {
        const w = await world(options);
        const res = await post(w);
        expect(cannotProblems(res), `${label} ${JSON.stringify(options)}`).toEqual([]);
        expect(oneCallProblems(w.conduit.calls, want)).toEqual([]);
        expect(w.conduit.audits).toEqual([]);
        expect(linksOf(res.text).map((l) => l.href)).toContain(listOf());
        bodies.push(mainText(res.text));
      }
    }
    // The right and the level are told alike.
    expect(new Set(bodies).size).toBe(1);
  });

  it("BD22: the creator shares with the case, told it cannot be undone: one POST, 303, the board shown as shared, a reload sending nothing", async () => {
    const w = await world();
    const before = await getAs(w, boardOfPath("b-quay"));
    const form = formFor(before.text, "share");
    expect(form?.method).toBe("post");
    expect(form?.action).toBe(boardOfPath("b-quay"));
    expect(form?.hidden).toEqual({ _csrf: w.csrf, action: "share" });
    expect(form?.inner).toMatch(new RegExp(`<button type="submit"[^>]*>\\s*${SHARE}\\s*</button>`));
    expect(mainText(before.text)).toContain(NOT_UNDONE);
    expect(lines(w.conduit.calls)).toEqual([`GET ${base()}/b-quay`]);
    w.conduit.calls.splice(0);
    const res = await share(w, "b-quay");
    expect(redirectProblems(res, boardOfPath("b-quay"))).toEqual([]);
    expect(oneCallProblems(w.conduit.calls, `POST ${base()}/b-quay/share`)).toEqual([]);
    expect(w.conduit.calls[0]?.body).toBe("");
    expect(w.conduit.audits).toEqual([{ action: "share_board", board_id: "b-quay" }]);
    w.conduit.calls.splice(0);
    const after = await getAs(w, boardOfPath("b-quay"));
    expect(mainText(after.text)).toContain("Shared with the case");
    // A shared board has nothing to share again; it may still be deleted.
    expect(formFor(after.text, "share")).toBeUndefined();
    expect(mainText(after.text)).not.toContain(NOT_UNDONE);
    expect(linksOf(after.text).map((l) => l.href)).toContain(confirmOf("b-quay"));
    await getAs(w, boardOfPath("b-quay"));
    expect(writes(w.conduit.calls)).toEqual([]);
    // No unshare is offered, and nothing names who made the board.
    expect(mainText(after.text)).not.toMatch(/unshare|make (?:it )?private|acct-/i);
  });

  it("BD23: share and delete are offered only where the board says may_draw; a non-creator's, posted by hand, is a missing board's page", async () => {
    // Blake's board, shared with the case: Alex reads it and is offered neither.
    const w = await world();
    const shared = await getAs(w, boardOfPath("b-shift"));
    expect(shared.status).toBe(200);
    expect(noControlProblems(shared.text)).toEqual([]);
    // Alex's own board, to a reader without the right to draw: neither.
    expect(noControlProblems((await getAs(await world({ rights: ["investigate"] }), boardOfPath("b-quay"))).text)).toEqual([]);
    const unknown = await getAs(w, NOWHERE);
    const missing = await share(w, "b-no-such-board");
    expect(notFoundProblems(missing, unknown)).toEqual([]);
    for (const boardId of ["b-shift", "b-blake", "b-no-such-board"]) {
      for (const post of [share, remove]) {
        w.conduit.calls.splice(0);
        const res = await post(w, boardId);
        expect(notFoundProblems(res, unknown), boardId).toEqual([]);
        expect(w.conduit.calls, boardId).toHaveLength(1);
      }
      // The confirmation page is never offered to a non-creator either, and reading it changes nothing.
      w.conduit.calls.splice(0);
      expect(notFoundProblems(await getAs(w, confirmOf(boardId)), unknown), boardId).toEqual([]);
      expect(lines(w.conduit.calls)).toEqual([`GET ${base()}/${boardId}`]);
    }
    expect(w.conduit.audits).toEqual([]);
    // A case the reader holds no level on: the same page.
    expect(notFoundProblems(await postAs(w, listOf("c-unshared"), { _csrf: w.csrf, action: "make", name: "x" }), unknown)).toEqual([]);
    // A post that names none of the page's writes, or the wrong address for one, is a path nothing serves and asks nothing.
    w.conduit.calls.splice(0);
    const none: [string, Record<string, string>][] = [
      [listOf(), {}],
      [listOf(), { action: "unshare" }],
      [listOf(), { action: "share" }],
      [listOf(), { action: "delete" }],
      [boardOfPath("b-quay"), { action: "make", name: "x" }],
      [PATH, { action: "make", name: "x" }],
      [`${PATH}?case=c-harbour&board=b-quay%2Fshare`, { action: "delete" }],
      [`${PATH}?case=..`, { action: "make", name: "x" }],
      [`${listOf()}&board=b-quay&board=b-shift`, { action: "delete" }],
    ];
    for (const [path, fields] of none) {
      expect(notFoundProblems(await postAs(w, path, { _csrf: w.csrf, ...fields }), unknown), `${path} ${JSON.stringify(fields)}`).toEqual([]);
    }
    for (const query of [`${boardOfPath("b-quay")}&delete=now`, `${listOf()}&delete=confirm`]) {
      expect(notFoundProblems(await getAs(w, query), unknown), query).toEqual([]);
    }
    expect(lines(w.conduit.calls)).toEqual([]);
  });

  it("BD24: delete asks first on its own page; the post sends one DELETE, 303 to the case's boards with the banner, said once", async () => {
    const w = await world();
    const board = await getAs(w, boardOfPath("b-quay"));
    // No form deletes from the board's own page: its link goes to the confirmation.
    expect(formFor(board.text, "delete")).toBeUndefined();
    const link = linksOf(board.text).find((l) => l.href === confirmOf("b-quay"));
    expect(link?.text).toBe("Delete this board");
    w.conduit.calls.splice(0);
    const asked = await getAs(w, confirmOf("b-quay"));
    expect(asked.status).toBe(200);
    expect(h1Of(asked.text)).toBe(ASK_DELETE);
    expect(mainText(asked.text)).toContain(STAYS);
    expect(mainText(asked.text)).toContain("Quay sketch");
    const form = formFor(asked.text, "delete");
    expect(form?.action).toBe(boardOfPath("b-quay"));
    expect(form?.hidden).toEqual({ _csrf: w.csrf, action: "delete" });
    expect(linksOf(asked.text).map((l) => l.href)).toContain(boardOfPath("b-quay"));
    expect(lines(w.conduit.calls)).toEqual([`GET ${base()}/b-quay`]);
    expect(w.conduit.audits).toEqual([]);
    w.conduit.calls.splice(0);
    const res = await remove(w, "b-quay");
    expect(redirectProblems(res, listOf())).toEqual([]);
    expect(oneCallProblems(w.conduit.calls, `DELETE ${base()}/b-quay`)).toEqual([]);
    expect(w.conduit.audits).toEqual([{ action: "delete_board", board_id: "b-quay" }]);
    // Another case's list does not take this case's banner.
    expect(hasBanner((await getAs(w, listOf("c-other"))).text)).toBe(false);
    const list = await getAs(w, listOf());
    expect(hasBanner(list.text)).toBe(true);
    expect(listed(list.text)).toEqual(["Night shift"]);
    expect(mainText(list.text)).not.toContain("Quay sketch");
    // Said once: a reload says nothing and sends nothing again.
    w.conduit.calls.splice(0);
    expect(hasBanner((await getAs(w, listOf())).text)).toBe(false);
    expect(writes(w.conduit.calls)).toEqual([]);
    // What was drawn on it stays in the case.
    expect(w.options.items.map((i) => [i.id, i.withdrawn ?? false])).toEqual([["d-tall", false]]);
    // An address alone cannot make the page say a board was deleted.
    const fresh = await world();
    for (const query of ["&deleted=1", "&banner=deleted", "&deleted=b-quay"]) expect(hasBanner((await getAs(fresh, `${listOf()}${query}`)).text), query).toBe(false);
    // A delete whose list then cannot be read keeps its banner for when the list is read.
    const later = await world();
    await remove(later, "b-quay");
    later.options.list_answer = { status: 500, body: {} };
    expect(hasBanner((await getAs(later, listOf())).text)).toBe(false);
    delete later.options.list_answer;
    expect(hasBanner((await getAs(later, listOf())).text)).toBe(true);
  });

  it("BD25: a write without this session's anti-forgery token is refused before anything is asked", async () => {
    const w = await world();
    const other = await signInTo(w.app);
    expect(other.csrf).not.toBe(w.csrf);
    w.conduit.calls.splice(0);
    for (const [path, fields] of [
      [listOf(), { action: "make", name: "Supply routes" }],
      [boardOfPath("b-quay"), { action: "share" }],
      [boardOfPath("b-quay"), { action: "delete" }],
    ] as [string, Record<string, string>][]) {
      for (const token of [undefined, other.csrf, ""]) {
        const res = await postAs(w, path, token === undefined ? fields : { _csrf: token, ...fields });
        expect(res.status, `${path} ${String(token)}`).toBe(403);
        expect(mainText(res.text)).toContain("This request could not be checked");
      }
      const unsigned = await request(w.app).post(path).type("form").send(new URLSearchParams({ _csrf: w.csrf, ...fields }).toString());
      expect(unsigned.status).toBe(403);
    }
    expect(lines(w.conduit.calls)).toEqual([]);
    expect(w.conduit.audits).toEqual([]);
  });

  it("BD26: a write with no answer, or a failing one, says nothing was changed (502) and shows no banner; a 401 says to sign in again", async () => {
    const posts = [(w: World) => make(w, "Supply routes"), (w: World) => share(w, "b-quay"), (w: World) => remove(w, "b-quay")];
    const failures: WorldOptions[] = [{ write_no_answer: true }, { write_answer: { status: 500, body: { detail: "boom" } } }, { write_answer: { status: 503, body: "down" } }, { write_answer: { status: 409, body: { detail: "conflict" } } }];
    for (const options of failures) {
      for (const post of posts) {
        const w = await world(options);
        const res = await post(w);
        expect(failedProblems(res), JSON.stringify(options)).toEqual([]);
        expect(w.conduit.calls).toHaveLength(1);
        delete w.options.write_no_answer;
        delete w.options.write_answer;
        expect(hasBanner((await getAs(w, listOf())).text)).toBe(false);
      }
    }
    for (const post of posts) {
      const closed = await world({ conduitUrl: await closedAddress() });
      expect(failedProblems(await post(closed))).toEqual([]);
      for (const options of [{ unknownBearer: true }, { write_answer: { status: 401, body: { detail: "Not authenticated" } } }] as WorldOptions[]) {
        const w = await world(options);
        const res = await post(w);
        expect(res.status, JSON.stringify(options)).toBe(401);
        expect(mainText(res.text)).toMatch(/Sign in again/);
        expect(res.headers["location"]).toBeUndefined();
        expect(hasBanner(res.text)).toBe(false);
      }
    }
  });

  it("BD27: each write asks the Conduit once, its own call, and so is audited once", async () => {
    const w = await world();
    for (const [post, want] of [
      [() => make(w, "Supply routes"), `POST ${base()}`],
      [() => share(w, "b-quay"), `POST ${base()}/b-quay/share`],
      [() => remove(w, "b-quay"), `DELETE ${base()}/b-quay`],
    ] as const) {
      w.conduit.calls.splice(0);
      expect((await post()).status).toBe(303);
      expect(oneCallProblems(w.conduit.calls, want)).toEqual([]);
    }
    expect(w.conduit.audits.map((a) => a.action)).toEqual(["make_board", "share_board", "delete_board"]);
    // The browser's anti-forgery token never reaches the Conduit, in any write.
    expect(w.conduit.calls.concat().every((c) => !c.body.includes(w.csrf) && !c.url.includes(w.csrf))).toBe(true);
  });

  it("BD28: each write is a native form or link in the page's order, each field labelled, so a keyboard reaches and works it", async () => {
    const w = await world();
    const list = await getAs(w, listOf());
    expect(formProblems(list.text, w.csrf)).toEqual([]);
    expect(stops(list.text)).toEqual(["a: Skip to main content", "button: Sign out", "a: Quay sketch", "a: Night shift", "input: name", "button: Make a blank board", "a: Back to this case", "a: Back to Home"]);
    const board = await getAs(w, boardOfPath("b-quay"));
    expect(formProblems(board.text, w.csrf)).toEqual([]);
    expect(stops(board.text)).toEqual(["a: Skip to main content", "button: Sign out", `button: ${SHARE}`, "a: Delete this board", "a: Back to this case's boards", "a: Back to Home"]);
    const asked = await getAs(w, confirmOf("b-quay"));
    expect(formProblems(asked.text, w.csrf)).toEqual([]);
    expect(stops(asked.text)).toEqual(["a: Skip to main content", "button: Sign out", "button: Delete board", "a: Cancel and go back to the board", "a: Back to Home"]);
    const wrong = await make(w, "");
    expect(formProblems(wrong.text, w.csrf)).toEqual([]);
    expect(stops(wrong.text).slice(2)).toEqual([expect.stringMatching(/^a: /), "input: name", "button: Make a blank board", "a: Back to this case's boards", "a: Back to Home"]);
  });

  it("BD29: with scripts off every write completes by form: no script but the data block, no handler, no inline style on any page", async () => {
    const w = await world();
    const pages = [await getAs(w, listOf()), await getAs(w, boardOfPath("b-quay")), await getAs(w, confirmOf("b-quay")), await make(w, "")];
    await remove(w, "b-quay");
    const banner = await getAs(w, listOf());
    expect(hasBanner(banner.text)).toBe(true);
    pages.push(banner, await make(await world({ rights: ["investigate"] }), "x"));
    for (const page of pages) expect(formProblems(page.text, w.csrf)).toEqual([]);
  });

  it("BD30: the fixture Conduit refuses a write as the real route does, in its order: rights, the case's gate, the body, the board, its creator", async () => {
    const w = await world();
    const ask = async (conduit: BoardsConduit, token: string | undefined, method: string, path: string, body?: unknown, type = "application/json"): Promise<{ status: number; body: unknown }> => {
      const res = await fetch(`${conduit.url}${path}`, {
        method,
        headers: { ...(token === undefined ? {} : { Authorization: `Bearer ${token}` }), ...(body === undefined ? {} : { "Content-Type": type }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      const text = await res.text();
      return { status: res.status, body: text === "" ? null : JSON.parse(text) };
    };
    const good = { name: "x", start: "blank" };
    const unrighted = await world({ rights: [] });
    const viewer = await world({ viewerCases: [CASE] });
    for (const [method, path] of [["POST", base()], ["POST", `${base()}/b-quay/share`], ["DELETE", `${base()}/b-quay`]] as const) {
      expect((await ask(w.conduit, undefined, method, path)).status).toBe(401);
      // The rights first, `draw_on_boards` before `investigate`, even for a case and a body that are wrong.
      expect(await ask(unrighted.conduit, unrighted.reader.token, method, path.replace(CASE, "c-no-such-case"), { _csrf: "t" })).toEqual({ status: 403, body: rightRefusal("draw_on_boards") });
      // Then the case's gate, before the body and the board.
      expect(await ask(w.conduit, w.reader.token, method, path.replace(CASE, "c-unshared"), { _csrf: "t" })).toEqual({ status: 404, body: NOT_FOUND_CASE });
      expect(await ask(viewer.conduit, viewer.reader.token, method, path.replace("b-quay", "b-no-such-board"), { _csrf: "t" })).toEqual({ status: 403, body: LEVEL_REFUSAL });
    }
    // Then the body: a field the model has not, the anti-forgery token among them; the name; the start; not JSON.
    const refusedAt = async (body: unknown, type?: string): Promise<unknown> => {
      const answer = await ask(w.conduit, w.reader.token, "POST", base(), body, type);
      return answer.status === 422 ? (answer.body as { detail: { type: string; loc: string[] }[] }).detail.map((d) => `${d.type} ${d.loc.join(".")}`)[0] : answer.status;
    };
    expect(await refusedAt({ ...good, _csrf: "t" })).toBe("extra_forbidden body._csrf");
    expect(await refusedAt({ ...good, action: "make" })).toBe("extra_forbidden body.action");
    expect(await refusedAt({ start: "blank" })).toBe("missing body.name");
    expect(await refusedAt({ name: 7 })).toBe("string_type body.name");
    expect(await refusedAt({ name: "" })).toBe("string_too_short body.name");
    expect(await refusedAt({ name: "a".repeat(201) })).toBe("string_too_long body.name");
    expect(await refusedAt({ name: "x", start: "drawing" })).toBe("literal_error body.start");
    expect(await refusedAt({ name: "x", view_id: "v" })).toBe("value_error body");
    expect(await refusedAt(good, "text/plain")).toBe("model_attributes_type body");
    expect(w.conduit.audits).toEqual([]);
    // Then, for a share and a removal, the board before its creator.
    for (const [method, suffix] of [["POST", "/share"], ["DELETE", ""]] as const) {
      for (const id of ["b-blake", "b-no-such-board"]) expect(await ask(w.conduit, w.reader.token, method, `${base()}/${id}${suffix}`), id).toEqual({ status: 404, body: NOT_FOUND_BOARD });
      expect(await ask(w.conduit, w.reader.token, method, `${base()}/b-shift${suffix}`)).toEqual({ status: 403, body: NOT_CREATOR });
    }
    // A route there is not: no unshare.
    expect((await ask(w.conduit, w.reader.token, "DELETE", `${base()}/b-quay/share`)).status).toBe(405);
    // What passes is carried out and audited once each, with the route's statuses.
    expect((await ask(w.conduit, w.reader.token, "POST", base(), good)).status).toBe(201);
    expect((await ask(w.conduit, w.reader.token, "POST", `${base()}/b-quay/share`)).status).toBe(200);
    expect(await ask(w.conduit, w.reader.token, "DELETE", `${base()}/b-quay`)).toEqual({ status: 204, body: null });
    expect(w.conduit.audits.map((a) => a.action)).toEqual(["make_board", "share_board", "delete_board"]);
    // The signed-in person's rights, for anyone signed in.
    expect(await ask(unrighted.conduit, unrighted.reader.token, "GET", "/v1/me/rights")).toEqual({ status: 200, body: { rights: [] } });
    expect((await ask(w.conduit, undefined, "GET", "/v1/me/rights")).status).toBe(401);
  });

  describe("BD31: each check is red against the real page or calls with one thing changed", () => {
    it("BD31: the make's check fails for the form passed through, a second call, a render on the post", async () => {
      const w = await world();
      const res = await make(w, "Supply routes");
      const real = w.conduit.calls.slice();
      expect(makeProblems(real, "Supply routes", w.reader.token)).toEqual([]);
      const call = real[0] as Call;
      const passed = [{ ...call, body: JSON.stringify({ _csrf: w.csrf, action: "make", name: "Supply routes", start: "blank" }) }];
      expect(makeProblems(passed, "Supply routes", w.reader.token)).not.toEqual([]);
      expect(makeProblems([{ ...call, headers: { ...call.headers, cookie: "a=b" } }], "Supply routes", w.reader.token)).not.toEqual([]);
      expect(oneCallProblems([call, { ...call, url: `${base()}/b-made-1` }], `POST ${base()}`)).not.toEqual([]);
      expect(oneCallProblems([call, { ...call, method: "GET" }], `POST ${base()}`)).not.toEqual([]);
      expect(redirectProblems(res, boardOfPath("b-made-1"))).toEqual([]);
      expect(redirectProblems({ status: 200, headers: {} }, boardOfPath("b-made-1"))).not.toEqual([]);
      expect(redirectProblems({ status: 302, headers: { location: boardOfPath("b-made-1") } }, boardOfPath("b-made-1"))).not.toEqual([]);
    });

    it("BD31: the error's check fails for no summary, the words lost, the browser's own limit, the Conduit's detail", async () => {
      const w = await world();
      const name = "a".repeat(201);
      const real = (await make(w, name)).text;
      expect(errorProblems(real, name)).toEqual([]);
      for (const planted of [
        real.replace('class="govuk-error-summary"', 'class="notice"'),
        real.replace(`value="${name}"`, 'value=""'),
        real.replace('id="board-name"', 'id="board-name" maxlength="200"'),
        real.replace("</main>", "<p>String should have at most 200 characters</p></main>"),
        real.replace('href="#board-name"', 'href="#"'),
      ]) {
        expect(planted).not.toBe(real);
        expect(errorProblems(planted, name)).not.toEqual([]);
      }
    });

    it("BD31: the refusals' checks fail for the Conduit's words, a creator's 403 said in words, controls for every reader", async () => {
      const w = await world({ rights: ["investigate"] });
      const real = await make(w, "x");
      expect(cannotProblems(real)).toEqual([]);
      expect(cannotProblems({ status: 403, text: real.text.replace(CANNOT, LEVEL_REFUSAL.detail) })).not.toEqual([]);
      expect(cannotProblems({ status: 403, text: real.text.replace("</main>", "<p>right_required draw_on_boards</p></main>") })).not.toEqual([]);
      const unknown = await getAs(w, NOWHERE);
      expect(notFoundProblems({ status: 403, text: real.text.replace(CANNOT, NOT_CREATOR.detail) }, unknown)).not.toEqual([]);
      const reader = await world();
      const shift = (await getAs(reader, boardOfPath("b-shift"))).text;
      const quay = (await getAs(reader, boardOfPath("b-quay"))).text;
      expect(noControlProblems(shift)).toEqual([]);
      expect(noControlProblems(quay)).not.toEqual([]);
    });

    it("BD31: the banner's, the failure's and the form's checks fail for a success on a 502, a token missing, a button out of the tab order, a script", async () => {
      const w = await world({ write_answer: { status: 500, body: {} } });
      const real = await remove(w, "b-quay");
      expect(failedProblems(real)).toEqual([]);
      const banner = `<div class="govuk-notification-banner govuk-notification-banner--success" role="alert"><p>${DELETED}</p></div></main>`;
      expect(failedProblems({ ...real, text: real.text.replace("</main>", banner) })).not.toEqual([]);
      expect(failedProblems({ ...real, status: 200 })).not.toEqual([]);
      expect(hasBanner(real.text.replace("</main>", banner))).toBe(true);
      const ok = await world();
      const page = (await getAs(ok, boardOfPath("b-quay"))).text;
      expect(formProblems(page, ok.csrf)).toEqual([]);
      const inMain = (from: string, to: string): string => {
        const main = mainOf(page);
        return page.replace(main, main.replace(from, to));
      };
      for (const planted of [
        inMain('<button type="submit"', '<button type="submit" tabindex="-1"'),
        inMain(`name="_csrf" value="${ok.csrf}"`, 'name="_csrf" value=""'),
        inMain('method="post"', 'method="get"'),
        inMain('<button type="submit"', '<div role="button"></div><button type="submit"'),
        inMain("<form", '<form onsubmit="x()"'),
        page.replace("</main>", '<script src="/x.js"></script></main>'),
      ]) {
        expect(planted).not.toBe(page);
        expect(formProblems(planted, ok.csrf)).not.toEqual([]);
      }
      const list = (await getAs(ok, listOf())).text;
      const unlabelled = list.replace('for="board-name"', 'for="other"');
      expect(unlabelled).not.toBe(list);
      expect(formProblems(unlabelled, ok.csrf)).toContain("a field with no label");
    });
  });
});
