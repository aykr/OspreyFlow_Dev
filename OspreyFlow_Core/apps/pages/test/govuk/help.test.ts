/**
 * The Help page, the first page of the GOV.UK tree (slice GR2a; ADR-152 decisions 6, 7, 12 and 13; FUNCTIONS row `help`), and
 * the tree's switch, its route list and its first template folder.
 *
 * There is no React-first proof for a GOV.UK page (decision 12 asks for one only where a React screen has a scenario, and the
 * React Help page, `apps/workspace/src/help/RolesHelpPage.tsx`, has none): each case's id is a scenario of
 * `spec/08_ACCEPTANCE_SCENARIOS.md` ("Scenario HP"), written first. `tests/glass_trees/test_govuk_help_scenario.py` holds the
 * two in step.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a role, place, level, team sentence or right missing from the page, or worded other than `roles.ts` words it   -> HP1
 *  - a text that `roles.ts` already holds, written again in `server/` or `tree-govuk/`                              -> HP6
 *  - no skip link first, two headings of the first level, a table with no caption, a skipped heading level            -> HP2
 *  - a person with no rights refused, or an unsigned request served                                                  -> HP3
 *  - a call to the Conduit, a form that writes, a method that is not GET answered                                    -> HP4
 *  - a script, a handler, an inline style, a tab stop above 0, a stop before the skip link                           -> HP5
 *  - the tree chosen by anything but `OSPREY_PAGES_TREE`, read in more than one place, an unknown value accepted     -> HP7
 *  - a route the tree has no page for answered other than as an unknown path                                         -> HP8
 *  - a route list that is not the paths the tree has pages for                                                       -> HP9
 * Every planted fault is the real page (or the real file) with one thing changed, run through the same function that finds
 * nothing in the real one (HP10, rule 15).
 */
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Express } from "express";
import { afterEach, describe, expect, it } from "vitest";
import {
  HELP_TITLE,
  LEVEL_WORDS,
  PLACE_WORDS,
  RIGHT_WORDS,
  ROLE_WORDS,
  TEAM_WORDS,
  rightName,
  rightSays,
} from "@ospreyflow/glass-shared";

import type * as Real from "@ospreyflow/glass-shared";

import { createApp } from "../../server/app.js";
import { loadConfig } from "../../server/config.js";
import { alertMonitoring } from "../../server/alertMonitoring.js";
import { help } from "../../server/help.js";
import { PAGES } from "../../server/pageList.js";
import type { PageModule } from "../../server/pages.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import type * as Stub from "../../server/types/glassShared.js";
import { captureOutput } from "../support/capture.js";
import { fakeConduit } from "../support/fakeConduit.js";
import type { FakeConduit } from "../support/fakeConduit.js";
import { csrfFromPage, cookieFrom, request } from "../support/http.js";
import { testClock } from "../support/clock.js";
import { generateSecret } from "../support/secret.js";
import { bearer, providerFor, textOf } from "../support/studioWorld.js";

// The compiled service is checked against `server/types/glassShared.d.ts`, not the package's source (`tsconfig.build.json`); this holds
// each declaration to the package's own type, so that a shape `roles.ts` changes and the stub still has as it was fails `npm run typecheck`.
type Conforms<Real, Stub> = Real extends Stub ? true : never;
export const STUB_CONFORMS_TO_THE_PACKAGE: [
  Conforms<typeof Real.HELP_TITLE, typeof Stub.HELP_TITLE>,
  Conforms<typeof Real.PLACE_WORDS, typeof Stub.PLACE_WORDS>,
  Conforms<typeof Real.ROLE_WORDS, typeof Stub.ROLE_WORDS>,
  Conforms<typeof Real.LEVEL_WORDS, typeof Stub.LEVEL_WORDS>,
  Conforms<typeof Real.TEAM_WORDS, typeof Stub.TEAM_WORDS>,
  Conforms<typeof Real.RIGHT_WORDS, typeof Stub.RIGHT_WORDS>,
  Conforms<typeof Real.rightName, typeof Stub.rightName>,
  Conforms<typeof Real.rightSays, typeof Stub.rightSays>,
] = [true, true, true, true, true, true, true, true];

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CORE = join(PAGES_DIR, "..", "..");
const read = (...parts: string[]): string => readFileSync(join(...parts), "utf8");

// ------------------------------------------------------------------------------------------------ the running service

const running: Running[] = [];
const conduits: FakeConduit[] = [];
afterEach(async () => {
  while (running.length > 0) await running.pop()?.stop();
  while (conduits.length > 0) await conduits.pop()?.stop();
});

interface Channel {
  errors: string[];
  logs: string[];
  exits: number[];
}

function channel(): Channel & { io: { log(m: string): void; error(m: string): void; exit(c: number): void } } {
  const out: Channel = { errors: [], logs: [], exits: [] };
  return { ...out, io: { log: (m) => void out.logs.push(m), error: (m) => void out.errors.push(m), exit: (c) => void out.exits.push(c) }, errors: out.errors, logs: out.logs, exits: out.exits };
}

/** Starts the service as `main.ts` does (the real settings, the real page list), with the in-memory store and a free loopback port. */
async function start(env: NodeJS.ProcessEnv) {
  const heard = channel();
  const captured = captureOutput();
  let result: Running | undefined;
  try {
    result = await main(
      { OSPREY_PAGES_PORT: "0", OSPREY_PAGES_SESSION_SECRET: generateSecret(48), ...env },
      heard.io,
      { store: new MemorySessionStore(), host: "127.0.0.1", assets: null, identityProvider: providerFor(bearer()) },
    );
  } finally {
    captured.restore();
  }
  if (result) running.push(result);
  return { result, heard };
}

interface Person {
  cookie: string;
  csrf: string;
}

/** Signs in through the real route and reads the anti-forgery token off the real Home page of the tree being served. */
async function signIn(server: Running["server"] | Express): Promise<Person> {
  const target = server as Parameters<typeof request>[0];
  const res = await request(target).get("/session/sign-in");
  if (res.status !== 302) throw new Error(`sign-in answered ${res.status}`);
  const cookie = cookieFrom(res);
  const home = await request(target).get("/").set("Cookie", cookie);
  return { cookie, csrf: csrfFromPage(home.text) };
}

async function govuk() {
  const { result } = await start({ OSPREY_PAGES_TREE: "govuk" });
  if (!result) throw new Error("the govuk tree did not start");
  return { server: result.server, who: await signIn(result.server) };
}

async function defaultTree(env: NodeJS.ProcessEnv = {}) {
  const { result } = await start(env);
  if (!result) throw new Error("the default tree did not start");
  return { server: result.server, who: await signIn(result.server) };
}

const getAs = (server: Running["server"], who: Person, path: string) => request(server).get(path).set("Cookie", who.cookie);

// ------------------------------------------------------------------------------------------------ reading a page

const strip = (html: string): string => html.replace(/<!--[\s\S]*?-->/g, "");
const attr = (tag: string, name: string): string | undefined => new RegExp(`\\s${name}="([^"]*)"`).exec(tag)?.[1];

/** The text between `<main …>` and `</main>`. */
function mainOf(html: string): string {
  const found = /<main\b[^>]*>([\s\S]*?)<\/main>/.exec(strip(html));
  return found ? (found[1] as string) : "";
}

interface Stop {
  tag: string;
  href: string | undefined;
  text: string;
}

/** Every stop a keyboard has, in document order: links with an address, buttons, inputs, and anything with a tab stop of 0. */
function focusable(html: string): Stop[] {
  const stops: Stop[] = [];
  // A link or a button holds its text up to its own closing tag; an input, select or textarea is read from its opening tag alone.
  for (const m of strip(html).matchAll(/<(a|button)\b([^>]*)>([\s\S]*?)<\/\1>|<(input|select|textarea)\b([^>]*)>/g)) {
    const tag = (m[1] ?? m[4]) as string;
    const attrs = (m[2] ?? m[5]) as string;
    if (tag === "input" && /\stype="hidden"/.test(attrs)) continue;
    if (tag === "a" && attr(attrs, "href") === undefined) continue;
    stops.push({ tag, href: attr(attrs, "href"), text: textOf(m[3] ?? "") });
  }
  return stops;
}

const headings = (html: string): { level: number; id: string | undefined; text: string }[] =>
  [...strip(html).matchAll(/<h([1-6])\b([^>]*)>([\s\S]*?)<\/h\1>/g)].map((m) => ({ level: Number(m[1]), id: attr(m[2] as string, "id"), text: textOf(m[3] as string) }));

/** Every fault in a page's structure, in words: the same function reads the real page and each planted one (HP2). */
function structureProblems(html: string): string[] {
  const page = strip(html);
  const found: string[] = [];
  if (!/<html\b[^>]*\slang="en-GB"/.test(page)) found.push('the page is not lang="en-GB"');
  if (!/<title>[^<]+<\/title>/.test(page)) found.push("the page has no title");
  const mains = [...page.matchAll(/<main\b([^>]*)>/g)];
  if (mains.length !== 1) found.push(`the page has ${mains.length} main landmarks, not one`);
  const mainId = attr((mains[0]?.[1] as string | undefined) ?? "", "id");
  if ([...page.matchAll(/<header\b/g)].length !== 1) found.push("the page has not exactly one header (banner) landmark");
  const stops = focusable(page);
  const first = stops[0];
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
  for (const dl of mainOf(page).matchAll(/<dl\b[^>]*>([\s\S]*?)<\/dl>/g)) {
    const terms = [...(dl[1] as string).matchAll(/<dt\b/g)].length;
    const defs = [...(dl[1] as string).matchAll(/<dd\b/g)].length;
    if (terms === 0 || terms !== defs) found.push(`a definition list has ${terms} terms and ${defs} definitions`);
  }
  // The section links: a nav with a name, one link for each second-level heading, each to an id that is there.
  const nav = /<nav\b([^>]*)>([\s\S]*?)<\/nav>/.exec(mainOf(page));
  if (!nav || !attr(nav[1] as string, "aria-label")) found.push("the page has no named navigation to its sections");
  else {
    const targets = [...(nav[2] as string).matchAll(/<a\b([^>]*)>/g)].map((a) => attr(a[1] as string, "href"));
    const sections = h.filter((x) => x.level === 2);
    if (sections.length === 0) found.push("the page has no sections");
    for (const s of sections) if (!s.id || !targets.includes(`#${s.id}`)) found.push(`the section ${JSON.stringify(s.text)} has no link in the navigation`);
    for (const t of targets) if (!t || !new RegExp(`\\sid="${t.slice(1)}"`).test(page)) found.push(`the link ${String(t)} goes to no id`);
  }
  return found;
}

/** Every thing in a page that needs a script, an inline rule or a tab stop out of order (HP5). */
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
  return found;
}

/** The page with what changes between two people or two requests taken out: the anti-forgery token and the script nonce. */
const withoutNonce = (html: string): string => html.replace(/nonce="[^"]*"/g, 'nonce="N"');
const sameFor = (html: string, csrf: string): string => html.split(csrf).join("CSRF").replace(/nonce="[^"]*"/g, 'nonce="N"');

// ------------------------------------------------------------------------------------------------ the page

describe("the tree's own Help page (the govuk tree)", () => {
  it("HP1: lists the places, the roles with what each does and opens, the levels, the teams and every right, in roles.ts's words", async () => {
    const { server, who } = await govuk();
    const res = await getAs(server, who, "/help");
    expect(res.status).toBe(200);
    expect(res.type).toMatch(/html/);
    const page = textOf(mainOf(res.text));
    const words: string[] = [HELP_TITLE, ...Object.values(PLACE_WORDS).flatMap((p) => [p.name, p.says])];
    for (const r of Object.values(ROLE_WORDS)) words.push(r.name, r.says);
    for (const l of Object.values(LEVEL_WORDS)) words.push(l.name, l.says);
    words.push(TEAM_WORDS.team, TEAM_WORDS.lead, TEAM_WORDS.authors);
    for (const right of Object.keys(RIGHT_WORDS)) words.push(rightName(right), rightSays(right));
    const missing = words.filter((w) => !page.includes(w));
    expect(missing).toEqual([]);
    // Each role's row says which places it opens, by the places' names (`placesByRole.json`, never typed here).
    const roles = /<table\b[^>]*>([\s\S]*?)<\/table>/.exec(mainOf(res.text));
    const rows = roles ? [...(roles[1] as string).matchAll(/<tbody\b[^>]*>([\s\S]*?)<\/tbody>/g)].flatMap((b) => [...(b[1] as string).matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)]) : [];
    expect(rows.length).toBe(Object.keys(ROLE_WORDS).length);
    for (const [row, role] of rows.map((r, i) => [r, Object.values(ROLE_WORDS)[i]] as const)) {
      const cells = [...(row[1] as string).matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/g)].map((c) => textOf(c[1] as string));
      expect(cells).toEqual([role?.name, role?.says, role?.places.map((p) => PLACE_WORDS[p].name).join(", ")]);
    }
    // One row for each right the words name, and the rights are the second table.
    const tables = [...mainOf(res.text).matchAll(/<table\b[^>]*>([\s\S]*?)<\/table>/g)];
    expect(tables.length).toBe(2);
    expect([...(tables[1]?.[1] as string).matchAll(/<tbody\b[^>]*>([\s\S]*?)<\/tbody>/g)].flatMap((b) => [...(b[1] as string).matchAll(/<tr\b/g)]).length).toBe(Object.keys(RIGHT_WORDS).length);
    // The React page's section headings are this page's, in the same order.
    const react = read(CORE, "apps", "workspace", "src", "help", "RolesHelpPage.tsx");
    const reactHeadings = [...react.matchAll(/<h3 id="help-[a-z]+">([^<]+)<\/h3>/g)].map((m) => m[1]);
    expect(reactHeadings.length).toBe(5);
    expect(headings(mainOf(res.text)).filter((h) => h.level === 2).map((h) => h.text)).toEqual(reactHeadings);
  });

  it("HP2: a heading, a skip link first, the landmarks, captioned tables, definition lists and links to the sections", async () => {
    const { server, who } = await govuk();
    const html = (await getAs(server, who, "/help")).text;
    expect(structureProblems(html)).toEqual([]);
    expect(headings(mainOf(html))[0]).toMatchObject({ level: 1, text: "Help" });
    expect(/<title>Help · OspreyFlow<\/title>/.test(html)).toBe(true);
    // The places and the levels are definition lists; the roles and the rights are the two tables.
    expect([...mainOf(html).matchAll(/<dl\b/g)].length).toBe(2);
  });

  it("HP3: needs no sign-in beyond the session: an unsigned request goes to sign-in, and anyone signed in sees the same page, whatever their rights", async () => {
    const { server, who } = await govuk();
    const unsigned = await request(server).get("/help");
    expect(unsigned.status).toBe(302);
    expect(unsigned.headers["location"]).toBe("/session/sign-in");
    expect(textOf(unsigned.text)).not.toContain("Roles, teams and Authors");
    // A person with no right at all, against the fake Conduit's: the page names no right and asks the Conduit nothing, so it is the same page.
    const bare = await getAs(server, who, "/help");
    expect(bare.status).toBe(200);
    const conduit = await fakeConduit([{ token: "unused", rights: [], cases: [] }]);
    conduits.push(conduit);
    const other = createApp({
      store: new MemorySessionStore({ clock: testClock() }),
      identityProvider: providerFor("unused-bearer"),
      sessionSecret: generateSecret(48),
      pages: PAGES,
      tree: "govuk",
      forward: { conduitUrl: conduit.url, bodyMaxBytes: 1024, uploadMaxBytes: 1024, upstreamTimeoutSeconds: 2 },
    });
    const person = await signIn(other);
    const seen = await request(other).get("/help").set("Cookie", person.cookie);
    expect(seen.status).toBe(200);
    expect(sameFor(seen.text, person.csrf)).toBe(sameFor(bare.text, who.csrf));
  });

  it("HP4: makes no call to the Conduit and writes nothing: GET only, and no form but sign-out", async () => {
    const conduit = await fakeConduit([{ token: "unused", rights: [], cases: [] }]);
    conduits.push(conduit);
    const app = createApp({
      store: new MemorySessionStore({ clock: testClock() }),
      identityProvider: providerFor("unused-bearer"),
      sessionSecret: generateSecret(48),
      pages: PAGES,
      tree: "govuk",
      forward: { conduitUrl: conduit.url, bodyMaxBytes: 1024, uploadMaxBytes: 1024, upstreamTimeoutSeconds: 2 },
    });
    const who = await signIn(app);
    const page = await request(app).get("/help").set("Cookie", who.cookie);
    expect(page.status).toBe(200);
    expect(conduit.calls).toEqual([]);
    // The one form the page has is the layout's sign-out, which posts to the service's own route.
    const forms = [...strip(page.text).matchAll(/<form\b([^>]*)>/g)].map((f) => [attr(f[1] as string, "method"), attr(f[1] as string, "action")]);
    expect(forms).toEqual([["post", "/session/sign-out"]]);
    expect(mainOf(page.text)).not.toMatch(/<form\b|<button\b|<input\b/);
    for (const method of ["post", "put", "patch", "delete"] as const) {
      const sent = await request(app)[method]("/help").set("Cookie", who.cookie).set("X-CSRF-Token", who.csrf).type("form").send({ _csrf: who.csrf });
      expect(sent.status, method).toBe(404);
    }
    expect(help.methods).toEqual(["GET"]);
    expect(conduit.calls).toEqual([]);
  });

  it("HP5: is complete with scripts off: no script, handler, inline style or tab stop above 0, and the stops come in the page's order", async () => {
    const { server, who } = await govuk();
    const res = await getAs(server, who, "/help");
    expect(scriptsOffProblems(res.text)).toEqual([]);
    expect(res.headers["content-security-policy"]).not.toMatch(/unsafe-inline|unsafe-eval/);
    const stops = focusable(res.text);
    const sections = headings(mainOf(res.text)).filter((h) => h.level === 2);
    expect(stops.map((s) => s.text)).toEqual(["Skip to main content", "Sign out", ...sections.map((s) => s.text), "Back to Home"]);
    expect(stops[0]?.href).toBe("#main");
    expect(stops.at(-1)?.href).toBe("/");
    expect(stops.slice(2, -1).map((s) => s.href)).toEqual(sections.map((s) => `#${s.id}`));
  });

  it("HP6: the page's own words are British English and its own: nothing roles.ts says is written again in server/ or tree-govuk/", () => {
    expect(copiesOfRolesWords(sourcesOfThePage())).toEqual([]);
    const words = read(PAGES_DIR, "server", "views", "helpWords.ts");
    expect(words).toContain("@ospreyflow/glass-shared");
    expect(americanSpellings(words + sourcesOfThePage().map((s) => s.text).join("\n"))).toEqual([]);
  });
});

// ------------------------------------------------------------------------------------------------ copied text, American spellings

/** A sentence or a phrase of roles.ts: each string literal of 25 characters or more, which is what the page's words must never repeat. */
function rolesLiterals(): string[] {
  const text = read(CORE, "packages", "glass-shared", "src", "help", "roles.ts");
  return [...text.matchAll(/(?<![\w$])"((?:[^"\\\n]|\\.){25,})"/g)].map((m) => m[1] as string).filter((s) => !/^(?:\.\.|\w+\/).*\.json$/.test(s));
}

interface Source {
  name: string;
  text: string;
}

/** The files that hold the page's own words and markup: `server/help.ts`, `server/views/helpWords.ts` and everything of `tree-govuk/`. */
function sourcesOfThePage(): Source[] {
  const files = [join(PAGES_DIR, "server", "help.ts"), join(PAGES_DIR, "server", "views", "helpWords.ts")];
  const walk = (dir: string): string[] =>
    readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(join(dir, e.name)) : [join(dir, e.name)]));
  return [...files, ...walk(join(PAGES_DIR, "tree-govuk"))].map((name) => ({ name, text: readFileSync(name, "utf8") }));
}

function copiesOfRolesWords(sources: Source[]): string[] {
  const literals = rolesLiterals();
  expect(literals.length).toBeGreaterThan(40); // the scan reads what it says it reads
  return sources.flatMap((s) => literals.filter((l) => s.text.includes(l)).map((l) => `${s.name}: ${l}`));
}

const AMERICAN = /\b(?:color|colors|organization|organizations|center|centers|authorize|authorized|behavior|license|licenses|analyze|favorite|catalog)\b/i;
const americanSpellings = (text: string): string[] => [...text.matchAll(new RegExp(AMERICAN.source, "gi"))].map((m) => m[0]);

// ------------------------------------------------------------------------------------------------ the switch

describe("OSPREY_PAGES_TREE decides which tree serves every route, `/` included", () => {
  it("HP7: govuk serves the Help page and its own Home", async () => {
    const { server, who } = await govuk();
    const home = await getAs(server, who, "/");
    expect(home.status).toBe(200);
    expect(mainOf(home.text)).toContain("<h1>Home</h1>");
    expect(mainOf(home.text)).not.toContain("<h1>OspreyFlow</h1>");
    expect((await getAs(server, who, "/help")).status).toBe(200);
    expect((await request(server).get("/healthz")).body).toEqual({ status: "ok" });
    // The service's own pages, drawn in this tree: a refusal is the tree's error template, not the other tree's.
    const refused = await request(server).get("/session/callback");
    expect(refused.status).toBe(503);
    expect(refused.text).toContain("Sign-in not available");
    // The frame is the tree's own: a skip link first, the one main landmark, and nothing that needs a script.
    expect(focusable(home.text)[0]).toMatchObject({ href: "#main", text: "Skip to main content" });
    expect(scriptsOffProblems(home.text)).toEqual([]);
    expect(refused.text).toContain('data-tree="govuk"');
  });

  it.each([
    ["unset", {}],
    ["default", { OSPREY_PAGES_TREE: "default" }],
  ])("HP7: %s serves the Default tree: its Home, and no page at /help", async (_name, env) => {
    const { server, who } = await defaultTree(env);
    const home = await getAs(server, who, "/");
    expect(mainOf(home.text)).toContain("<h1>OspreyFlow</h1>");
    expect(mainOf(home.text)).not.toContain("<h1>Home</h1>");
    expect(home.text).not.toContain('data-tree="govuk"');
    for (const signed of [true, false]) {
      const res = signed ? await getAs(server, who, "/help") : await request(server).get("/help");
      expect(res.status, `signed in: ${signed}`).toBe(404);
      expect(textOf(res.text)).not.toContain("Roles, teams and Authors");
    }
    // The Default tree's own pages are where they were: a request with no session is sent to sign-in.
    const studio = await request(server).get("/studio");
    expect(studio.status).toBe(302);
    expect(studio.headers["location"]).toBe("/session/sign-in");
  });

  it.each(["GOVUK", "gov.uk", "govuk ", " default", "", "react", "both", "default,govuk", "0"])(
    "HP7: the value %j is refused at start, in words, and nothing is served",
    async (value) => {
      const { result, heard } = await start({ OSPREY_PAGES_TREE: value });
      expect(result).toBeUndefined();
      expect(heard.exits).toEqual([1]);
      expect(heard.logs.join("\n")).not.toMatch(/listening/);
      const said = heard.errors.join("\n");
      expect(said).toContain("OSPREY_PAGES_TREE");
      expect(said).toMatch(/default/);
      expect(said).toMatch(/govuk/);
      expect(() => loadConfig({ OSPREY_PAGES_SESSION_SECRET: generateSecret(48), OSPREY_PAGES_TREE: value })).toThrow(/OSPREY_PAGES_TREE/);
    },
  );

  it("HP7: the setting is read in one place, and the trees' pages come from one table of modules, each naming the trees it serves", () => {
    const readers = readdirSync(join(PAGES_DIR, "server"))
      .filter((f) => f.endsWith(".ts") && /\bOSPREY_PAGES_TREE\b/.test(read(PAGES_DIR, "server", f).replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "")))
      .sort();
    expect(readers).toEqual(["config.ts"]);
    expect(loadConfig({ OSPREY_PAGES_SESSION_SECRET: generateSecret(48) }).tree).toBe("default");
    expect(loadConfig({ OSPREY_PAGES_SESSION_SECRET: generateSecret(48), OSPREY_PAGES_TREE: "govuk" }).tree).toBe("govuk");
    // The table: Help (and the Admin People list, slice AD3a, and trends shown together, slice GR4a) are the govuk tree's alone, and every page that was there before them is the Default tree's alone.
    expect(help.trees).toEqual(["govuk"]);
    expect(PAGES).toContain(help);
    // Slice GR3a's alert monitoring page is the tree's third, and the Default tree's twin of it is not built; slice GR1a's cases page
    // is its fifth and slice GG4a's boards page its sixth, likewise.
    expect(alertMonitoring.trees).toEqual(["govuk"]);
    expect(PAGES).toContain(alertMonitoring);
    const govukOnly = ["/admin/people", "/packs/trends", "/cases", "/cases/boards"];
    // Slice RM1a's alert queue is the tree's seventh, and the Default tree has no twin of it either.
    for (const page of PAGES) {
      if (page.id === "alerts-rules-watches") expect(page.trees, page.id).toEqual(["govuk"]);
      else if (page !== help && page !== alertMonitoring && !govukOnly.includes(page.path)) expect(page.trees ?? ["default"], page.id).toEqual(["default"]);
    }
  });

  it("HP7: what decides a route's tree is the module's own list: the same Help page, named for both, is served by both (rule 15)", async () => {
    // The handler answers in words of its own, so that the Default tree (which has no Help template) is not what is being tested.
    const both: PageModule = { ...help, trees: ["default", "govuk"], handler: (_req, res) => void res.type("text/plain").send("served") };
    for (const tree of ["default", "govuk"] as const) {
      const app = createApp({
        store: new MemorySessionStore({ clock: testClock() }),
        identityProvider: providerFor("unused-bearer"),
        sessionSecret: generateSecret(48),
        pages: [both],
        tree,
      });
      const who = await signIn(app);
      const res = await request(app).get("/help").set("Cookie", who.cookie);
      expect([res.status, res.text], tree).toEqual([200, "served"]);
    }
    // And a page left to the default says no tree at all: it is the Default tree's, as every page was before there was a switch.
    const { trees: _named, ...plain } = both;
    const app = createApp({ store: new MemorySessionStore({ clock: testClock() }), identityProvider: providerFor("unused-bearer"), sessionSecret: generateSecret(48), pages: [plain], tree: "govuk" });
    const who = await signIn(app);
    expect((await request(app).get("/help").set("Cookie", who.cookie)).status).toBe(404);
  });

  it("HP8: a route a tree has no page for answers as it does today: as a path nothing serves, signed in or not", async () => {
    const { server, who } = await govuk();
    const unknown = async (path: string, signed: boolean) => (signed ? getAs(server, who, path) : request(server).get(path));
    for (const path of ["/studio", "/studio/dataset-map?case=c1", "/studio/model", "/studio/releases"]) {
      for (const signed of [true, false]) {
        const there = await unknown(path, signed);
        const nowhere = await unknown("/nothing-is-served-here", signed);
        expect(there.status, `${path} signed in: ${signed}`).toBe(404);
        expect(there.status).toBe(nowhere.status);
        expect(withoutNonce(there.text).replace(/\/studio[^<\s]*/g, "PATH")).toBe(withoutNonce(nowhere.text).replace("/nothing-is-served-here", "PATH"));
      }
    }
    // The same in the other tree, for the route the Default tree has no page for.
    const other = await defaultTree();
    const helpHere = await getAs(other.server, other.who, "/help");
    const nowhere = await getAs(other.server, other.who, "/nothing-is-served-here");
    expect(helpHere.status).toBe(nowhere.status);
    expect(withoutNonce(helpHere.text).replace("/help", "PATH")).toBe(withoutNonce(nowhere.text).replace("/nothing-is-served-here", "PATH"));
  });
});

// ------------------------------------------------------------------------------------------------ the route list

/** The paths of `tree-govuk/routes.yaml`'s `routes:` list (a plain list of paths, one to a line). */
function listedRoutes(text: string): string[] {
  const lines = text.split("\n").filter((l) => !/^\s*(#|$)/.test(l));
  expect(lines[0]).toBe("routes:");
  return lines.slice(1).map((l) => /^\s+-\s+"?(\/[^"\s]*)"?\s*$/.exec(l)?.[1] ?? `NOT A ROUTE: ${l}`);
}

/** A row whose function is not complete: its pages are in the list, and its own `route` stays empty until every section has one (slice AD3a: `admin`; slice GR4a:
 * `reports-trends-shown-together`, whose page is read-only until arranging is built; slice GR1a: `cases-and-views`; slice GG4a: `drawing-boards`;
 * slice RM1a: `alerts-rules-watches`, whose rules, watches and strength have no page yet). */
const INCOMPLETE_ROWS: ReadonlySet<string> = new Set(["admin", "reports-trends-shown-together", "cases-and-views", "drawing-boards", "alerts-rules-watches"]);

function routeListProblems(listText: string, pages: readonly PageModule[], functionsText: string): string[] {
  const found: string[] = [];
  const listed = listedRoutes(listText);
  const served = pages.filter((p) => (p.trees ?? ["default"]).includes("govuk")).map((p) => p.path);
  for (const route of listed) if (!served.includes(route)) found.push(`${route} is listed and no page of the tree serves it`);
  for (const route of served) if (!listed.includes(route)) found.push(`${route} is served and not listed`);
  if (new Set(listed).size !== listed.length) found.push("a route is listed twice");
  for (const page of pages.filter((p) => (p.trees ?? ["default"]).includes("govuk"))) {
    const row = new RegExp(`- id: ${page.id}\\n(?:    .*\\n)*?    route: "([^"]*)"`).exec(functionsText);
    const wanted = INCOMPLETE_ROWS.has(page.id) ? "" : page.path;
    if (row?.[1] !== wanted) found.push(`the row ${page.id} of FUNCTIONS.yaml has route ${JSON.stringify(row?.[1])}, not ${JSON.stringify(wanted)}`);
  }
  return found;
}

describe("the route list", () => {
  const listText = read(PAGES_DIR, "tree-govuk", "routes.yaml");
  const functionsText = read(PAGES_DIR, "FUNCTIONS.yaml");

  it("HP9: is the paths the govuk tree has pages for, and the rows of FUNCTIONS.yaml that name them carry the same route", () => {
    expect(routeListProblems(listText, PAGES, functionsText)).toEqual([]);
    expect(listedRoutes(listText)).toEqual(["/help", "/admin/people", "/reports", "/packs/trends", "/cases", "/cases/boards", "/alert-queue"]);
  });

  it("HP9: the route table registers each page under its own id and path, once: the list is one route a page", () => {
    const govukPages = PAGES.filter((p) => (p.trees ?? ["default"]).includes("govuk"));
    expect(govukPages.map((p) => [p.id, p.path, [...p.methods]])).toEqual([
      ["help", "/help", ["GET"]],
      ["admin", "/admin/people", ["GET"]],
      ["reports-figures", "/reports", ["GET"]],
      ["reports-trends-shown-together", "/packs/trends", ["GET"]],
      ["cases-and-views", "/cases", ["GET"]],
      ["drawing-boards", "/cases/boards", ["GET", "POST"]],
      ["alerts-rules-watches", "/alert-queue", ["GET"]], // the alert queue (slice RM1a), the seventh page of the tree
    ]);
  });
});

// ------------------------------------------------------------------------------------------------ planted faults (rule 15)

describe("each check above is red against the real page or file with one thing changed", () => {
  let real = "";
  const page = async (): Promise<string> => {
    if (real === "") {
      const { server, who } = await govuk();
      real = (await getAs(server, who, "/help")).text;
    }
    return real;
  };
  const without = (html: string, pattern: RegExp): string => {
    expect(pattern.test(html), `the plant's anchor ${String(pattern)} is in the page`).toBe(true);
    return html.replace(pattern, "");
  };
  const FIRST_STOP = /<a\b[^>]*href="#main"[^>]*>/;

  it("HP10: the structure check finds each fault the real page does not have", async () => {
    const html = await page();
    expect(structureProblems(html)).toEqual([]);
    const plants: [string, string, RegExp][] = [
      ["no skip link", without(html, /<a\b[^>]*href="#main"[^>]*>[^<]*<\/a>/), /first stop is not the skip link/],
      ["a stop before the skip link", html.replace(FIRST_STOP, (m) => `<a href="/">Elsewhere</a>${m}`), /first stop is not the skip link/],
      ["a second heading of the first level", html.replace("</main>", "<h1>Again</h1></main>"), /headings of the first level, not one/],
      ["a skipped heading level", html.replace("</main>", "<h4>Deep</h4></main>"), /skips from level/],
      ["a table with no caption", without(html, /<caption\b[^>]*>[\s\S]*?<\/caption>/), /no caption/],
      ["a column header with no scope", html.replace(/<th scope="col"/, "<th"), /column header/],
      ["a row with no row header", html.replace(/<th scope="row"/, "<th"), /row does not start/],
      ["a definition without its term", html.replace(/<dt\b[^>]*>[\s\S]*?<\/dt>/, ""), /terms and/],
      ["no main landmark", html.replace(/<main\b/, "<div").replace("</main>", "</div>"), /main landmarks/],
      ["no header landmark", html.replace(/<header\b/, "<div").replace("</header>", "</div>"), /header \(banner\)/],
      ["not British English", html.replace('lang="en-GB"', 'lang="en-US"'), /en-GB/],
      ["a section with no link", html.replace(/<li><a href="#help-[a-z]+">[^<]*<\/a><\/li>/, ""), /no link in the navigation/],
    ];
    for (const [name, planted, expected] of plants) {
      const found = structureProblems(planted);
      expect(found.length, name).toBeGreaterThan(0);
      expect(found.join("\n"), name).toMatch(expected);
    }
  });

  it("HP10: the scripts-off check finds each thing that needs a script, a style or a stop out of order", async () => {
    const html = await page();
    expect(scriptsOffProblems(html)).toEqual([]);
    const plants: [string, string, RegExp][] = [
      ["an executable script", html.replace("</body>", '<script nonce="x">window.x=1</script></body>'), /not a data block/],
      ["a module script", html.replace("</body>", '<script type="module" src="/assets/pages/x.js"></script></body>'), /not a data block/],
      ["an event handler", html.replace(/<a /, '<a onclick="go()" '), /event-handler/],
      ["an inline style", html.replace(/<main\b/, '<main style="color:red"'), /inline style/],
      ["a style element", html.replace("</head>", "<style>a{}</style></head>"), /style element/],
      ["a tab stop of 3", html.replace(/<main\b/, '<main tabindex="3"'), /tab stop of 3/],
      ["a javascript address", html.replace(/<a href="\/"/, '<a href="javascript:void(0)"'), /javascript:/],
      ["a stylesheet from another origin", html.replace("</head>", '<link rel="stylesheet" href="https://cdn.example.test/x.css"></head>'), /another origin/],
    ];
    for (const [name, planted, expected] of plants) {
      const found = scriptsOffProblems(planted);
      expect(found.length, name).toBeGreaterThan(0);
      expect(found.join("\n"), name).toMatch(expected);
    }
  });

  it("HP10: the copy scan finds a sentence of roles.ts written again in the page's own words, as the real scan reads the page's files", () => {
    const real = sourcesOfThePage();
    expect(real.map((s) => s.name.slice(PAGES_DIR.length + 1)).sort()).toEqual(
      expect.arrayContaining(["server/help.ts", "server/views/helpWords.ts"]),
    );
    expect(copiesOfRolesWords(real)).toEqual([]);
    const sentence = RIGHT_WORDS.create_case;
    expect(sentence).toBeDefined();
    const literal = rolesLiterals()[0] as string;
    const planted = real.map((s) => (s.name.endsWith("helpWords.ts") ? { ...s, text: `${s.text}\nconst copy = "${literal}";\n` } : s));
    expect(copiesOfRolesWords(planted)).toEqual([expect.stringContaining(literal)]);
    expect(americanSpellings("The organization's color")).toEqual(["organization", "color"]);
  });

  it("HP10: the route-list check finds a route nothing serves, a page left out, a duplicate and a row that names another route", () => {
    const listText = read(PAGES_DIR, "tree-govuk", "routes.yaml");
    const functionsText = read(PAGES_DIR, "FUNCTIONS.yaml");
    expect(routeListProblems(listText, PAGES, functionsText)).toEqual([]);
    const extra = `${listText.trimEnd()}\n  - /welcome\n`;
    expect(routeListProblems(extra, PAGES, functionsText).join("\n")).toMatch(/\/welcome is listed and no page of the tree serves it/);
    const empty = "routes:\n";
    expect(routeListProblems(empty, PAGES, functionsText).join("\n")).toMatch(/\/help is served and not listed/);
    const twice = `${listText.trimEnd()}\n  - /help\n`;
    expect(routeListProblems(twice, PAGES, functionsText).join("\n")).toMatch(/listed twice/);
    const moved = functionsText.replace(/(- id: help\n(?:    .*\n)*?    route: )"\/help"/, '$1"/helps"');
    expect(moved).not.toBe(functionsText);
    expect(routeListProblems(listText, PAGES, moved).join("\n")).toMatch(/row help of FUNCTIONS.yaml has route "\/helps"/);
    // The Admin People list's row is incomplete: a route given to it while its other sections have no page is a fault.
    const routedEarly = functionsText.replace(/(- id: admin\n(?:    .*\n)*?    route: )""/, '$1"/admin/people"');
    expect(routedEarly).not.toBe(functionsText);
    expect(routeListProblems(listText, PAGES, routedEarly).join("\n")).toMatch(/row admin of FUNCTIONS.yaml has route "\/admin\/people", not ""/);
    const unclaimed: PageModule = { ...help, id: "welcome", path: "/welcome", trees: ["govuk"] };
    expect(routeListProblems(listText, [...PAGES, unclaimed], functionsText).join("\n")).toMatch(/\/welcome is served and not listed/);
  });
});
