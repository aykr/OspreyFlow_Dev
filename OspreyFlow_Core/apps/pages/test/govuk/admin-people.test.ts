/**
 * The Admin People list, a read-only page of the GOV.UK tree (slice AD3a; ADR-152 decisions 1, 4, 5, 6, 7 and 12; FUNCTIONS row `admin`;
 * scenario AP of `spec/08_ACCEPTANCE_SCENARIOS.md`, written first). `tests/glass_trees/test_govuk_admin_people_scenario.py` holds the
 * scenario and this file in step: each case's id is a row of the scenario.
 *
 * There is no React-first proof (the React People section has controls and no scenario of its own): the proof is the real service
 * started for the GOV.UK tree, the real page list and a fixture Conduit that refuses what the real routes refuse (`adminPeopleConduit.ts`).
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a person missing, out of order, a column other than Person, Roles and State, a table with no caption or header   -> AP1
 *  - a role shown as its identifier, a right with no name, a grant that is not said in words                         -> AP2
 *  - a state said other than Enabled, Disabled, Invited, the organisation's sign-in or a guest's mark left out          -> AP3
 *  - an empty or failed read drawn as a table, a partial table, a failure said as a refusal                          -> AP4
 *  - a person without the right who learns the page is there, or sees the Conduit's words, or the right's name      -> AP5
 *  - a person the page removed, skipped, cut, added or sorted (for any clearance or unit, at any length), a count of people -> AP6
 *  - a call that carries the browser's headers, a route other than the two, a query, a write, an unsigned read       -> AP7
 *  - a form, a control, a script, a handler, an inline style, a stop out of order                                     -> AP8
 *  - an American spelling, a sentence of roles.ts written again, the session's words not the Studio's                  -> AP9
 *  - the page in the Default tree, left out of the route list, or the `admin` row given a route while incomplete      -> AP10
 * Every planted fault is the real page (or the real file) with one thing changed, run through the same function that finds nothing in
 * the real one (AP11, rule 15).
 */
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Express } from "express";
import { afterEach, describe, expect, it } from "vitest";
import { rightName } from "@ospreyflow/glass-shared";

import { createApp } from "../../server/app.js";
import { PAGES } from "../../server/pageList.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { peopleView } from "../../server/views/adminPeopleWords.js";
import { refusalWords } from "../../server/views/studioWords.js";
import { testClock } from "../support/clock.js";
import { cookieFrom, csrfFromPage, request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { bearer, providerFor, textOf } from "../support/studioWorld.js";
import { BUILT_IN, MANAGE_PEOPLE, REFUSAL, account, adminConduit } from "./adminPeopleConduit.js";
import type { Account, AdminConduit, AdminConduitOptions } from "./adminPeopleConduit.js";

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CORE = join(PAGES_DIR, "..", "..");
const read = (...parts: string[]): string => readFileSync(join(...parts), "utf8");

const PATH = "/admin/people";
const NOWHERE = "/nothing-is-served-here";

// ------------------------------------------------------------------------------------------------ the world

const conduits: AdminConduit[] = [];
afterEach(async () => {
  while (conduits.length > 0) await conduits.pop()?.stop();
});

/** Four synthetic people, with no digit in any name (a test of AP6 looks for a count). */
const PEOPLE: Account[] = [
  account({ id: "p-alex", username: "alex.example", name: "Alex Example", roles: ["analyst"] }),
  account({ id: "p-blake", username: "blake.sample", name: "Blake Sample", roles: ["osprey-admin", "role:night-desk"] }),
  account({ id: "p-casey", username: "casey.test", name: "Casey Test", roles: [] }),
  account({ id: "p-drew", username: "drew.placeholder", name: "Drew Placeholder", enabled: false, roles: ["data_engineer"] }),
];
const CUSTOM = [{ id: "night-desk", name: "Night desk" }];

interface World {
  app: Express;
  conduit: AdminConduit;
  token: string;
  cookie: string;
  csrf: string;
}

interface WorldOptions extends Partial<Omit<AdminConduitOptions, "readers">> {
  /** The rights the signed-in person holds at the Conduit: the manage-people right by default. */
  rights?: string[];
  tree?: "govuk" | "default";
  /** Send the pages service to this address instead of the fixture's (an address nothing listens at). */
  conduitUrl?: string;
  /** The Conduit does not know this person's bearer: the session has outlived the person's token. */
  unknownBearer?: boolean;
}

async function world(options: WorldOptions = {}): Promise<World> {
  const token = bearer();
  const conduit = await adminConduit({
    readers: options.unknownBearer === true ? [] : [{ token, rights: options.rights ?? [MANAGE_PEOPLE] }],
    people: options.people ?? PEOPLE,
    custom: options.custom ?? CUSTOM,
    ...(options.people_answer ? { people_answer: options.people_answer } : {}),
    ...(options.roles_answer ? { roles_answer: options.roles_answer } : {}),
    ...(options.roles_no_answer ? { roles_no_answer: true } : {}),
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
  // What the sign-in itself sent the Conduit (the session-events record) is not the page's: the calls a test reads are the page's.
  conduit.calls.splice(0);
  return { app, conduit, token, cookie, csrf: csrfFromPage(home.text) };
}

const getAs = (w: World, path: string) => request(w.app).get(path).set("Cookie", w.cookie);
const people = (w: World) => getAs(w, PATH);
const calls = (c: AdminConduit): string[] => c.calls.map((call) => `${call.method} ${call.url}`);

/** An address nothing listens at: a server that was started and stopped. */
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

interface Table {
  caption: string;
  columns: string[];
  rows: { head: string; roles: string[]; state: string[] }[];
}

/** The items of a cell: each `li` of a list in it, or the cell's own text. */
function itemsOf(cell: string): string[] {
  const items = [...cell.matchAll(/<li\b[^>]*>([\s\S]*?)<\/li>/g)].map((m) => textOf(m[1] as string));
  return items.length > 0 ? items : [textOf(cell)];
}

/** The page's one table, read as the page draws it; `undefined` when there is none. */
function tableOf(html: string): Table | undefined {
  const found = /<table\b[^>]*>([\s\S]*?)<\/table>/.exec(mainOf(html));
  if (!found) return undefined;
  const inner = found[1] as string;
  const caption = textOf(/<caption\b[^>]*>([\s\S]*?)<\/caption>/.exec(inner)?.[1] ?? "");
  const head = /<thead\b[^>]*>([\s\S]*?)<\/thead>/.exec(inner)?.[1] ?? "";
  const columns = [...head.matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/g)].map((m) => textOf(m[1] as string));
  const body = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/.exec(inner)?.[1] ?? "";
  const rows = [...body.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((row) => {
    const cells = [...(row[1] as string).matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/g)].map((c) => c[1] as string);
    return { head: textOf(cells[0] ?? ""), roles: itemsOf(cells[1] ?? ""), state: itemsOf(cells[2] ?? "") };
  });
  return { caption, columns, rows };
}

/** Every fault in a page's structure, in words: the same function reads the real page and each planted one (AP8). */
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
  // The page is read-only: the layout's sign-out is the one form, and nothing in the main landmark is a control.
  const forms = [...page.matchAll(/<form\b([^>]*)>/g)].map((f) => `${attr(f[1] as string, "method") ?? ""} ${attr(f[1] as string, "action") ?? ""}`);
  if (forms.some((f) => f !== "post /session/sign-out")) found.push(`a form that is not the sign-out: ${forms.join("; ")}`);
  if (/<(form|button|input|select|textarea)\b/.test(mainOf(page))) found.push("the main landmark holds a control or a form");
  return found;
}

/** Every thing in a page that needs a script, an inline rule or a tab stop out of order (AP8). */
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

/** Identifiers the page must never show: a role's, a right's, a person's own id, and the Conduit's refusal. */
const IDENTIFIERS = ["osprey-admin", "data_engineer", "analyst", "role:", "right:", "night-desk", "create_case", "source_author", "p-alex", "p-blake", "right_required", MANAGE_PEOPLE];
const identifierProblems = (html: string): string[] => IDENTIFIERS.filter((id) => strip(html).includes(id)).map((id) => `the page shows ${JSON.stringify(id)}`);

/** A number in the main landmark's text: a count of people (the fixture's names, roles and words have no digit). */
const countProblems = (html: string): string[] => (/\d/.test(textOf(mainOf(html))) ? [`the main landmark's text holds a number: ${textOf(mainOf(html))}`] : []);

/** What the refusal must be: the unknown path's page, byte for byte but for the script nonce. */
const refusalProblems = (refused: { status: number; text: string }, unknown: { status: number; text: string }): string[] =>
  refused.status === unknown.status && withoutNonce(refused.text) === withoutNonce(unknown.text) ? [] : ["the refusal is not the page of a path nothing serves"];

// ------------------------------------------------------------------------------------------------ the sources

interface Source {
  name: string;
  text: string;
}

const SOURCES = ["server/adminPeople.ts", "server/views/adminPeopleWords.ts", "tree-govuk/admin-people.njk"];
const sourcesOfThePage = (): Source[] => SOURCES.map((name) => ({ name, text: read(PAGES_DIR, name) }));
const withoutComments = (text: string): string => text.replace(/\/\*[\s\S]*?\*\/|\/\/.*$|\{#[\s\S]*?#\}/gm, "");

/** The page does not choose who is drawn: no call in its code removes, cuts, sorts or turns a row round (AP6, decision 5). */
const CHOOSING = /\.(?:filter|slice|splice|sort|toSorted|reverse|toReversed|flatMap|shift|pop)\s*\(|\b(?:continue|break)\s*;/;
const choosingProblems = (sources: Source[]): string[] =>
  sources.filter((s) => CHOOSING.test(withoutComments(s.text))).map((s) => `${s.name} chooses which rows are drawn: ${CHOOSING.exec(withoutComments(s.text))?.[0] ?? ""}`);

function rolesLiterals(): string[] {
  const text = read(CORE, "packages", "glass-shared", "src", "help", "roles.ts");
  return [...text.matchAll(/(?<![\w$])"((?:[^"\\\n]|\\.){25,})"/g)].map((m) => m[1] as string).filter((s) => !/^(?:\.\.|\w+\/).*\.json$/.test(s));
}
const copiesOfRolesWords = (sources: Source[]): string[] => {
  const literals = rolesLiterals();
  expect(literals.length).toBeGreaterThan(40); // the scan reads what it says it reads
  return sources.flatMap((s) => literals.filter((l) => s.text.includes(l)).map((l) => `${s.name}: ${l}`));
};
const AMERICAN = /\b(?:color|colors|organization|organizations|center|centers|authorize|authorized|behavior|license|licenses|analyze|favorite|catalog)\b/i;
const americanSpellings = (text: string): string[] => [...text.matchAll(new RegExp(AMERICAN.source, "gi"))].map((m) => m[0]);

// ------------------------------------------------------------------------------------------------ a long and varied list

/** Letters only, so that no name of the list holds a digit (a count is looked for as a digit): 0 -> a, 25 -> z, 26 -> ba. */
const letters = (n: number): string => {
  let out = "";
  let rest = n;
  do {
    out = String.fromCharCode(97 + (rest % 26)) + out;
    rest = Math.floor(rest / 26);
  } while (rest > 0);
  return out;
};

/**
 * Far more people than any cap a page might carry (a hundred is the common one), and every field an access filter applied after
 * retrieval could key on: the clearance, the organisation unit, a service account, a disabled account, an invited one. The list is a
 * pattern that puts each kind at the start, the middle and the end, so that a skip and a cut both show.
 */
const LONG_SIZE = 260;
const CLEARANCES = ["official", "secret", "top-secret", null] as const;
const UNITS = ["ops", "intelligence", "finance", null] as const;
const LONG: Account[] = Array.from({ length: LONG_SIZE }, (_, i) =>
  account({
    id: `long-${letters(i)}`,
    username: `person.${letters(i)}`,
    name: `Person ${letters(i)}`,
    enabled: i % 7 !== 3,
    must_set_password: i % 11 === 5,
    system_account: i % 13 === 0,
    clearance: CLEARANCES[i % CLEARANCES.length] ?? null,
    org_unit: UNITS[(i >> 1) % UNITS.length] ?? null,
    roles: i % 5 === 0 ? [] : ["analyst"],
  }),
);
const CATALOGUE = { built_in: BUILT_IN.map((role) => ({ ...role, rights: [], gives: [] })), custom: [] };

/** What the page draws for a person: the name, or the username when the name is blank (the view's own rule). */
const drawnName = (p: Account): string => (p.name.trim() === "" ? p.username : p.name);

/** Every person sent that the view did not draw, or drew out of place: the same function reads the real view and each planted one. */
function viewProblems(view: (people: unknown, roles: unknown) => unknown, sent: Account[]): string[] {
  const drawn = view(sent, CATALOGUE) as { kind?: string; rows?: { name: string }[] } | undefined;
  if (drawn?.kind !== "table" || !drawn.rows) return [`the view is not a table: ${JSON.stringify(drawn)}`];
  const names = drawn.rows.map((r) => r.name);
  const found: string[] = [];
  if (names.length !== sent.length) found.push(`${names.length} rows were drawn for ${sent.length} people sent`);
  sent.forEach((p, i) => {
    if (names[i] !== drawnName(p)) found.push(`row ${i} is ${JSON.stringify(names[i])}, not ${JSON.stringify(drawnName(p))} (clearance ${String(p.clearance)}, unit ${String(p.org_unit)})`);
  });
  return found;
}

/**
 * The real `adminPeopleWords.ts` with one change, imported: the plant is in the real file's own loop, and the same function that finds
 * nothing in the real view (`viewProblems`) reads it. The copy lives in a folder of its own, away from the page's, and is removed.
 */
async function plantedView(change: (source: string) => string): Promise<(people: unknown, roles: unknown) => unknown> {
  const real = read(PAGES_DIR, "server", "views", "adminPeopleWords.ts");
  const planted = change(real);
  expect(planted, "the plant changed the file").not.toBe(real);
  const folder = mkdtempSync(join(tmpdir(), "ad3a-planted-"));
  try {
    const file = join(folder, "planted.ts");
    writeFileSync(file, planted.replace('"./helpWords.js"', JSON.stringify(join(PAGES_DIR, "server", "views", "helpWords"))));
    const module = (await import(/* @vite-ignore */ file)) as { peopleView: (people: unknown, roles: unknown) => unknown };
    return module.peopleView;
  } finally {
    rmSync(folder, { recursive: true, force: true });
  }
}

/** The loop that builds the rows, and the push that adds one: the anchors of the plants. */
const LOOP = "for (const person of people as unknown[]) {\n";
const PUSH = "rows.push({";

// ------------------------------------------------------------------------------------------------ the page

describe("the People list (the govuk tree)", () => {
  it("AP1: is a table of the people the Conduit sends, with a caption, column headers and a row header, in the order sent", async () => {
    const w = await world();
    const res = await people(w);
    expect(res.status).toBe(200);
    expect(res.type).toMatch(/html/);
    const table = tableOf(res.text);
    expect(table?.caption).toBe("People and their roles");
    expect(table?.columns).toEqual(["Person", "Roles", "State"]);
    expect(table?.rows.map((r) => r.head)).toEqual(PEOPLE.map((p) => p.name));
    expect(headings(mainOf(res.text))[0]).toEqual({ level: 1, text: "Admin: People" });
    expect(/<title>Admin: People · OspreyFlow<\/title>/.test(res.text)).toBe(true);
    expect(structureProblems(res.text)).toEqual([]);
  });

  it("AP2: says each role in words: a built-in role by its label, a custom role by its name, a single right by its name, an older grant as such", async () => {
    const odd = [
      account({ id: "p-eli", username: "eli.odd", name: "Eli Odd", roles: ["analyst", "role:night-desk", "right:create_case", "source_author", "role:gone"] }),
      account({ id: "p-fern", username: "fern.none", name: "Fern None", roles: [] }),
      account({ id: "p-gale", username: "gale.preset", name: "Gale Preset", roles: ["reports_viewer", "rule_author"] }),
    ];
    const w = await world({ people: odd });
    const res = await people(w);
    expect(res.status).toBe(200);
    const rows = tableOf(res.text)?.rows ?? [];
    expect(rows.map((r) => r.roles)).toEqual([
      ["Analyst", "Night desk", `Right: ${rightName("create_case")}`, "Older grant", "Older grant"],
      ["No roles"],
      ["Reports Viewer", "Rule author"],
    ]);
    expect(identifierProblems(res.text)).toEqual([]);
    expect(BUILT_IN.map((r) => r.label)).toContain("Analyst");
  });

  it("AP3: says each person's state in words: Enabled, Disabled, or Invited, and the organisation's sign-in beside it", async () => {
    const states = [
      account({ id: "s1", username: "state.one", name: "State One" }),
      account({ id: "s2", username: "state.two", name: "State Two", enabled: false }),
      account({ id: "s3", username: "state.three", name: "State Three", must_set_password: true }),
      account({ id: "s4", username: "state.four", name: "State Four", organisation_linked: true }),
      account({ id: "s5", username: "state.five", name: "State Five", enabled: false, organisation_linked: true, must_set_password: true }),
    ];
    const w = await world({ people: states });
    const rows = tableOf((await people(w)).text)?.rows ?? [];
    expect(rows.map((r) => r.state)).toEqual([
      ["Enabled"],
      ["Disabled"],
      ["Invited — must set a password"],
      ["Enabled", "Signs in through the organisation"],
      ["Disabled", "Signs in through the organisation"],
    ]);
  });

  it("AP3: a guest account is marked as one, in the React section's words, whatever else its state says; a person who has not signed in yet is not a guest", async () => {
    const guestWords = "Guest: homed outside this organisation's Entra ID; signs in only while guest accounts are admitted";
    const states = [
      account({ id: "g1", username: "guest.one", name: "Guest One", guest: true }),
      account({ id: "g2", username: "guest.two", name: "Guest Two", guest: true, enabled: false }),
      account({ id: "g3", username: "guest.three", name: "Guest Three", guest: true, must_set_password: true, organisation_linked: true }),
      account({ id: "g4", username: "entra.new", name: "Entra New", signed_in: false, email: "entra.new@example.test", access_read_at: "2026-11-01T09:00:00Z" }),
      account({ id: "g5", username: "plain.one", name: "Plain One", receivable_handling_codes: ["a"] }),
    ];
    const w = await world({ people: states });
    const rows = tableOf((await people(w)).text)?.rows ?? [];
    expect(rows.map((r) => r.state)).toEqual([
      ["Enabled", guestWords],
      ["Disabled", guestWords],
      ["Invited — must set a password", "Signs in through the organisation", guestWords],
      ["Enabled"],
      ["Enabled"],
    ]);
  });

  it("AP4: a list with no person says so and draws no table; a Conduit that failed says the people could not be read, and draws no part of a table", async () => {
    const none = await world({ people: [] });
    const empty = await people(none);
    expect(empty.status).toBe(200);
    expect(textOf(mainOf(empty.text))).toContain("There are no people to list.");
    expect(tableOf(empty.text)).toBeUndefined();

    const failures: [string, WorldOptions][] = [
      ["the people route failing", { people_answer: { status: 503, body: { detail: "Service Unavailable" } } }],
      ["the people route answering what is not a list", { people_answer: { status: 200, body: { people: [] } } }],
      ["the people route answering text", { people_answer: { status: 200, body: "<html>an error page</html>" } }],
      ["a person with no roles field", { people_answer: { status: 200, body: [{ id: "x", username: "x.y", name: "X Y", enabled: true }] } }],
      ["a person that is not an object", { people_answer: { status: 200, body: [PEOPLE[0], "Casey Test"] } }],
      ["a person whose name is not text", { people_answer: { status: 200, body: [{ ...PEOPLE[0], name: 7 }] } }],
      ["the roles route failing", { roles_answer: { status: 500, body: { detail: "Internal Server Error" } } }],
      ["the roles route answering what is not a catalogue", { roles_answer: { status: 200, body: [] } }],
      ["a catalogue with no built-in roles", { roles_answer: { status: 200, body: { custom: [] } } }],
      ["a custom role with no name", { roles_answer: { status: 200, body: { built_in: [], custom: [{ id: "night-desk" }] } } }],
    ];
    for (const [name, options] of failures) {
      const w = await world(options);
      const res = await people(w);
      expect(res.status, name).toBe(502);
      expect(textOf(mainOf(res.text)), name).toContain("The people could not be read just now");
      expect(tableOf(res.text), name).toBeUndefined();
      for (const person of PEOPLE) expect(res.text, name).not.toContain(person.name);
    }
    // No answer at all.
    const away = await world({ conduitUrl: await closedAddress() });
    const gone = await people(away);
    expect(gone.status).toBe(502);
    expect(textOf(mainOf(gone.text))).toContain("The people could not be read just now");
    expect(tableOf(gone.text)).toBeUndefined();
    // The session has outlived the person's token: the Conduit's 401 is said as the Studio says it.
    const ended = await world({ unknownBearer: true });
    const out = await people(ended);
    expect(out.status).toBe(401);
    expect(textOf(mainOf(out.text))).toContain(refusalWords(401, undefined, ""));
    expect(tableOf(out.text)).toBeUndefined();
    // The same two cases for the second read, the roles: the people route answered, and the roles route gave no answer or a 401.
    const rolesAway = await world({ roles_no_answer: true });
    const rolesGone = await people(rolesAway);
    expect(calls(rolesAway.conduit)).toEqual(["GET /v1/admin/people", "GET /v1/admin/roles"]);
    expect(rolesGone.status).toBe(502);
    expect(textOf(mainOf(rolesGone.text))).toContain("The people could not be read just now");
    expect(tableOf(rolesGone.text)).toBeUndefined();
    for (const person of PEOPLE) expect(rolesGone.text).not.toContain(person.name);
    const rolesEnded = await world({ roles_answer: { status: 401, body: { detail: "Not authenticated" } } });
    const rolesOut = await people(rolesEnded);
    expect(calls(rolesEnded.conduit)).toEqual(["GET /v1/admin/people", "GET /v1/admin/roles"]);
    expect(rolesOut.status).toBe(401);
    expect(textOf(mainOf(rolesOut.text))).toContain(refusalWords(401, undefined, ""));
    expect(textOf(mainOf(rolesOut.text))).not.toContain("The people could not be read just now");
    expect(tableOf(rolesOut.text)).toBeUndefined();
    for (const person of PEOPLE) expect(rolesOut.text).not.toContain(person.name);
  });

  it("AP5: a person without the right, and any other refusal, gets the page of a path nothing serves, with none of the Conduit's words", async () => {
    for (const rights of [[], ["create_case", "edit_pipelines"], ["manage_models", "read_audit"]]) {
      const w = await world({ rights });
      const refused = await people(w);
      const unknown = await getAs(w, NOWHERE);
      expect(refused.status, rights.join()).toBe(404);
      expect(refusalProblems(refused, unknown), rights.join()).toEqual([]);
      for (const said of ["right_required", MANAGE_PEOPLE, "manage people", "Missing right", "not available to you", "People"]) {
        expect(textOf(mainOf(refused.text)), said).not.toContain(said);
      }
      expect(tableOf(refused.text)).toBeUndefined();
      // The Conduit was asked once, for the people: the roles are not asked of a person refused.
      expect(calls(w.conduit), rights.join()).toEqual(["GET /v1/admin/people"]);
    }
    // A refusal other than the right's: the same page, whatever the Conduit says in its body.
    for (const [status, body] of [[404, { detail: "Not Found" }], [403, REFUSAL], [409, { detail: "a conflict, in words" }], [422, { detail: [{ msg: "field required" }] }]] as const) {
      const w = await world({ people_answer: { status, body } });
      const refused = await people(w);
      expect(refusalProblems(refused, await getAs(w, NOWHERE)), String(status)).toEqual([]);
      expect(refused.text, String(status)).not.toContain("a conflict, in words");
      expect(calls(w.conduit), String(status)).toEqual(["GET /v1/admin/people"]);
    }
    // The roles route refusing a person the people route did not: the same page, with no table.
    const split = await world({ roles_answer: { status: 403, body: REFUSAL } });
    expect(refusalProblems(await people(split), await getAs(split, NOWHERE))).toEqual([]);
    // A person without the right is refused before a failing Conduit's own fault is told: the 404, never the 502.
    const failing = await world({ rights: [], people_answer: { status: 503, body: {} } });
    expect((await people(failing)).status).toBe(404);
  });

  it("AP6: draws whatever the Conduit sends, whole and in its order, and says no count of people anywhere", async () => {
    const sent = [
      account({ id: "z1", username: "zed.last", name: "Zed Last", roles: ["analyst"] }),
      account({ id: "z2", username: "amy.first", name: "Amy First", enabled: false, roles: [] }),
      account({ id: "z3", username: "inv.ited", name: "Inv Ited", must_set_password: true, roles: ["rule_author"] }),
      account({ id: "z4", username: "svc.probe", name: "Svc Probe", system_account: true, roles: ["reports_viewer"] }),
      account({ id: "z5", username: "zed.last", name: "Zed Last", roles: [] }),
    ];
    const w = await world({ people: sent });
    const res = await people(w);
    expect(tableOf(res.text)?.rows.map((r) => r.head)).toEqual(["Zed Last", "Amy First", "Inv Ited", "Svc Probe", "Zed Last"]);
    expect(countProblems(res.text)).toEqual([]);
    const one = await world({ people: [PEOPLE[0] as Account] });
    expect(tableOf((await people(one)).text)?.rows.length).toBe(1);
    expect(countProblems((await people(one)).text)).toEqual([]);
    // The page's code holds nothing that chooses who is drawn.
    expect(choosingProblems(sourcesOfThePage())).toEqual([]);
  });

  it("AP6: draws everyone, whole, whatever their clearance or unit and however many there are: no cap, and nothing keyed on who the person is", async () => {
    const w = await world({ people: LONG });
    const res = await people(w);
    expect(res.status).toBe(200);
    expect(tableOf(res.text)?.rows.map((r) => r.head)).toEqual(LONG.map((p) => p.name));
    expect(tableOf(res.text)?.rows.length).toBe(LONG_SIZE);
    expect(countProblems(res.text)).toEqual([]);
    // The same list through the view alone, and the same check that is red below.
    expect(viewProblems(peopleView, LONG)).toEqual([]);
  });

  it("AP7: asks the Conduit as the person and nothing of the browser's, for the people and the roles once each, and writes nothing", async () => {
    const w = await world();
    const res = await getAs(w, `${PATH}?unit=another&limit=1&token=abc`)
      .set("Origin", "https://browser.example.test")
      .set("Referer", "https://browser.example.test/somewhere")
      .set("X-CSRF-Token", w.csrf)
      .set("X-Forwarded-For", "203.0.113.7");
    expect(res.status).toBe(200);
    expect(calls(w.conduit)).toEqual(["GET /v1/admin/people", "GET /v1/admin/roles"]);
    const allowed = new Set(["authorization", "accept", "host", "connection", "user-agent", "accept-language", "accept-encoding", "sec-fetch-mode"]);
    for (const call of w.conduit.calls) {
      expect(call.headers["authorization"]).toBe(`Bearer ${w.token}`);
      expect(call.headers["accept"]).toBe("application/json");
      expect(Object.keys(call.headers).filter((name) => !allowed.has(name))).toEqual([]);
    }
    // No sign-in: sent to sign-in, and the Conduit is asked nothing.
    const bare = await world();
    const unsigned = await request(bare.app).get(PATH);
    expect(unsigned.status).toBe(302);
    expect(unsigned.headers["location"]).toBe("/session/sign-in");
    expect(unsigned.text).not.toContain("People and their roles");
    expect(bare.conduit.calls).toEqual([]);
    // Nothing is written, and no method but GET is answered: a path nothing serves, though the anti-forgery token is valid.
    for (const method of ["post", "put", "patch", "delete"] as const) {
      const sent = await request(bare.app)[method](PATH).set("Cookie", bare.cookie).set("X-CSRF-Token", bare.csrf).type("form").send({ _csrf: bare.csrf });
      expect(sent.status, method).toBe(404);
    }
    expect(bare.conduit.calls).toEqual([]);
    const page = PAGES.find((p) => p.path === PATH);
    expect(page?.methods).toEqual(["GET"]);
  });

  it("AP8: has the structure a reader moves by, no control but the sign-out, no script, and the stops in the page's order: skip link, sign-out, Help, Home", async () => {
    const w = await world();
    const res = await people(w);
    expect(res.status).toBe(200);
    expect(structureProblems(res.text)).toEqual([]);
    expect(scriptsOffProblems(res.text)).toEqual([]);
    expect(res.headers["content-security-policy"]).not.toMatch(/unsafe-inline|unsafe-eval/);
    const stops = focusable(res.text);
    expect(stops.map((s) => s.text)).toEqual(["Skip to main content", "Sign out", "What each role and right lets a person do", "Back to Home"]);
    expect(stops.map((s) => s.href)).toEqual(["#main", undefined, "/help", "/"]);
    // The same for an empty list and for a failure: no control, in the main landmark, in either.
    for (const options of [{ people: [] }, { people_answer: { status: 503, body: {} } }] as WorldOptions[]) {
      const other = await people(await world(options));
      expect(structureProblems(other.text)).toEqual([]);
      expect(scriptsOffProblems(other.text)).toEqual([]);
    }
  });

  it("AP9: the page's words are British English and its own: roles.ts's are not written again, and the session's words are the Studio's", () => {
    expect(copiesOfRolesWords(sourcesOfThePage())).toEqual([]);
    expect(americanSpellings(sourcesOfThePage().map((s) => s.text).join("\n"))).toEqual([]);
    const words = read(PAGES_DIR, "server", "views", "adminPeopleWords.ts");
    expect(words).toContain("./helpWords.js");
    expect(withoutComments(read(PAGES_DIR, "server", "adminPeople.ts"))).toContain("refusalWords");
  });
});

// ------------------------------------------------------------------------------------------------ the switch and the lists

/** The paths of `tree-govuk/routes.yaml`'s `routes:` list. */
function listedRoutes(text: string): string[] {
  const lines = text.split("\n").filter((l) => !/^\s*(#|$)/.test(l));
  expect(lines[0]).toBe("routes:");
  return lines.slice(1).map((l) => /^\s+-\s+"?(\/[^"\s]*)"?\s*$/.exec(l)?.[1] ?? `NOT A ROUTE: ${l}`);
}

/** The `admin` row of `FUNCTIONS.yaml`: its scenario ids and its route. */
function adminRow(functionsText: string): { scenario: string; route: string } | undefined {
  const found = /- id: admin\n(?:    .*\n)*?    scenario: "([^"]*)"\n    route: "([^"]*)"/.exec(functionsText);
  return found ? { scenario: found[1] as string, route: found[2] as string } : undefined;
}

/** What the list, the rows and the page module must say together while the `admin` function is not complete. */
function listProblems(routesText: string, functionsText: string): string[] {
  const found: string[] = [];
  if (!listedRoutes(routesText).includes(PATH)) found.push(`${PATH} is not in the route list`);
  const row = adminRow(functionsText);
  if (!row) return [...found, "the admin row of FUNCTIONS.yaml has no scenario and route"];
  const ids = row.scenario.split(",").map((s) => s.trim());
  const wanted = Array.from({ length: 11 }, (_, i) => `AP${i + 1}`);
  if (ids.join() !== wanted.join()) found.push(`the admin row's scenario is ${JSON.stringify(row.scenario)}, not ${wanted.join(", ")}`);
  if (row.route !== "") found.push(`the admin row has the route ${JSON.stringify(row.route)} while the function is not complete`);
  return found;
}

describe("the tree that serves the page, and the lists that name it", () => {
  it("AP10: the govuk tree serves it; the Default tree and an unset tree answer it as a path nothing serves, and ask the Conduit nothing", async () => {
    const w = await world({ tree: "govuk" });
    expect((await people(w)).status).toBe(200);
    for (const tree of ["default"] as const) {
      const other = await world({ tree });
      for (const signed of [true, false]) {
        const there = signed ? await people(other) : await request(other.app).get(PATH);
        const nowhere = signed ? await getAs(other, NOWHERE) : await request(other.app).get(NOWHERE);
        expect(there.status, `${tree}, signed in: ${signed}`).toBe(404);
        expect(refusalProblems(there, nowhere), `${tree}, signed in: ${signed}`).toEqual([]);
      }
      expect(other.conduit.calls).toEqual([]);
    }
    const page = PAGES.find((p) => p.path === PATH);
    expect(page).toBeDefined();
    expect([page?.id, page?.trees]).toEqual(["admin", ["govuk"]]);
  });

  it("AP10: the route list holds the path, and the admin row carries the scenario's ids and an empty route", () => {
    const routesText = read(PAGES_DIR, "tree-govuk", "routes.yaml");
    const functionsText = read(PAGES_DIR, "FUNCTIONS.yaml");
    expect(listProblems(routesText, functionsText)).toEqual([]);
    expect(listedRoutes(routesText)).toEqual(["/help", PATH, "/packs/trends"]);
  });
});

// ------------------------------------------------------------------------------------------------ planted faults (rule 15)

describe("each check above is red against the real page, file or fixture with one thing changed", () => {
  const without = (html: string, pattern: RegExp): string => {
    expect(pattern.test(html), `the plant's anchor ${String(pattern)} is in the page`).toBe(true);
    return html.replace(pattern, "");
  };

  it("AP11: the structure and scripts-off checks find each fault the real page does not have", async () => {
    const html = (await people(await world())).text;
    expect(structureProblems(html)).toEqual([]);
    expect(scriptsOffProblems(html)).toEqual([]);
    const structural: [string, string, RegExp][] = [
      ["a table with no caption", without(html, /<caption\b[^>]*>[\s\S]*?<\/caption>/), /no caption/],
      ["a column header with no scope", html.replace(/<th scope="col"/, "<th"), /column header/],
      ["a row with no row header", html.replace(/<th scope="row"/, "<th"), /row does not start/],
      ["a button in the main landmark", html.replace("</main>", '<button type="submit">Invite</button></main>'), /control or a form/],
      ["an invite form", html.replace("</main>", '<form method="post" action="/admin/people/invite"><input name="email"></form></main>'), /a form that is not the sign-out/],
      ["a second heading of the first level", html.replace("</main>", "<h1>Again</h1></main>"), /headings of the first level/],
      ["no skip link", without(html, /<a\b[^>]*href="#main"[^>]*>[^<]*<\/a>/), /first stop is not the skip link/],
      ["no main landmark", html.replace(/<main\b/, "<div").replace("</main>", "</div>"), /main landmarks/],
    ];
    for (const [name, planted, expected] of structural) {
      const found = structureProblems(planted);
      expect(found.length, name).toBeGreaterThan(0);
      expect(found.join("\n"), name).toMatch(expected);
    }
    const scripts: [string, string, RegExp][] = [
      ["an executable script", html.replace("</body>", '<script nonce="x">window.x=1</script></body>'), /not a data block/],
      ["an event handler", html.replace(/<a /, '<a onclick="go()" '), /event-handler/],
      ["an inline style", html.replace(/<main\b/, '<main style="color:red"'), /inline style/],
      ["a tab stop of 3", html.replace(/<main\b/, '<main tabindex="3"'), /tab stop of 3/],
    ];
    for (const [name, planted, expected] of scripts) {
      const found = scriptsOffProblems(planted);
      expect(found.length, name).toBeGreaterThan(0);
      expect(found.join("\n"), name).toMatch(expected);
    }
  });

  it("AP11: the identifier, count, refusal and choosing checks find a role identifier, a count, the Conduit's words and a filter", async () => {
    const w = await world();
    const html = (await people(w)).text;
    expect(identifierProblems(html)).toEqual([]);
    expect(countProblems(html)).toEqual([]);
    expect(identifierProblems(html.replace("Analyst", "analyst"))[0]).toMatch(/"analyst"/);
    expect(identifierProblems(html.replace("Night desk", "role:night-desk")).join()).toMatch(/role:/);
    expect(identifierProblems(html.replace("Enabled", "right:create_case")).join()).toMatch(/right:/);
    expect(countProblems(html.replace("</main>", "<p>4 people</p></main>"))[0]).toMatch(/holds a number/);
    expect(countProblems(html.replace("People and their roles", "People and their roles (4)"))[0]).toMatch(/holds a number/);

    const refused = await world({ rights: [] });
    const real = await people(refused);
    const unknown = await getAs(refused, NOWHERE);
    expect(refusalProblems(real, unknown)).toEqual([]);
    const said = { status: real.status, text: real.text.replace("</main>", `<p>${MANAGE_PEOPLE} is required</p></main>`) };
    expect(refusalProblems(said, unknown)).toHaveLength(1);
    expect(refusalProblems({ status: 403, text: real.text }, unknown)).toHaveLength(1);
    expect(refusalProblems({ status: 200, text: (await people(w)).text }, unknown)).toHaveLength(1);

    const real_sources = sourcesOfThePage();
    expect(choosingProblems(real_sources)).toEqual([]);
    // Planted at the real call site: the loop that builds the rows, in the file that has it (not a statement added beside it).
    const WORDS = "server/views/adminPeopleWords.ts";
    const inLoop = (planted: string): Source[] => real_sources.map((s) => (s.name === WORDS ? { ...s, text: planted } : s));
    const words = (real_sources.find((s) => s.name === WORDS) as Source).text;
    expect(words).toContain(LOOP);
    expect(words).toContain(PUSH);
    const calls: [string, string][] = [
      [".filter(", words.replace(LOOP, "for (const person of (people as unknown[]).filter((p) => p !== null)) {\n")],
      [".slice(", words.replace(LOOP, "for (const person of (people as unknown[]).slice(0, 100)) {\n")],
      [".sort(", words.replace(LOOP, "for (const person of (people as unknown[]).sort()) {\n")],
      [".reverse(", words.replace(LOOP, "for (const person of (people as unknown[]).reverse()) {\n")],
      [".flatMap(", words.replace(LOOP, "for (const person of (people as unknown[]).flatMap((p) => [p])) {\n")],
      ["continue;", words.replace(LOOP, `${LOOP}    if (isObject(person) && person["org_unit"] === "ops") continue;\n`)],
      ["break;", words.replace(LOOP, `${LOOP}    if (rows.length >= 100) break;\n`)],
    ];
    for (const [name, planted] of calls) {
      expect(planted, name).not.toBe(words);
      expect(choosingProblems(inLoop(planted)).join("\n"), name).toMatch(/chooses which rows are drawn/);
    }
    // The scan reads code, not a sentence about it.
    const talked = real_sources.map((s) => (s.name === "server/adminPeople.ts" ? { ...s, text: `${s.text}\n// never .filter( a row\n` } : s));
    expect(choosingProblems(talked)).toEqual([]);
    // The copy scan finds a sentence of roles.ts written again.
    const literal = rolesLiterals()[0] as string;
    const copied = real_sources.map((s) => (s.name.endsWith("adminPeopleWords.ts") ? { ...s, text: `${s.text}\nconst copy = "${literal}";\n` } : s));
    expect(copiesOfRolesWords(copied)).toEqual([expect.stringContaining(literal)]);
    expect(americanSpellings("The organization's color")).toEqual(["organization", "color"]);
  });

  it("AP11: the whole-list check finds a person skipped, cut or removed by a change in the real loop, whatever the person's clearance or unit", async () => {
    // The real view finds nothing, on the long and varied list and on the short one.
    expect(viewProblems(peopleView, LONG)).toEqual([]);
    expect(viewProblems(peopleView, PEOPLE)).toEqual([]);
    const plants: [string, (source: string) => string, RegExp][] = [
      ["a skip by organisation unit", (t) => t.replace(LOOP, `${LOOP}    if (isObject(person) && person["org_unit"] === "ops") continue;\n`), /row \d+ is/],
      ["a skip by clearance", (t) => t.replace(LOOP, `${LOOP}    if (isObject(person) && person["clearance"] === "secret") continue;\n`), /clearance/],
      ["a skip of everyone above a clearance", (t) => t.replace(LOOP, `${LOOP}    if (isObject(person) && person["clearance"] !== null && person["clearance"] !== "official") continue;\n`), /rows were drawn/],
      ["a skip of the service accounts", (t) => t.replace(LOOP, `${LOOP}    if (isObject(person) && person["system_account"] === true) continue;\n`), /rows were drawn/],
      ["a skip of the disabled", (t) => t.replace(LOOP, `${LOOP}    if (isObject(person) && person["enabled"] === false) continue;\n`), /rows were drawn/],
      ["a cut at a hundred, by a break", (t) => t.replace(LOOP, `${LOOP}    if (rows.length >= 100) break;\n`), /100 rows were drawn for 260/],
      ["a cut at a hundred, by a conditional push", (t) => t.replace(PUSH, `if (rows.length < 100) ${PUSH}`), /100 rows were drawn for 260/],
      ["a cut at fifty, by the loop's own list", (t) => t.replace(LOOP, "for (const person of (people as unknown[]).slice(0, 50)) {\n"), /50 rows were drawn for 260/],
    ];
    for (const [name, change, expected] of plants) {
      const found = viewProblems(await plantedView(change), LONG);
      expect(found.length, name).toBeGreaterThan(0);
      expect(found.join("\n"), name).toMatch(expected);
    }
    // A plant that no list of the earlier tests could meet: the fixtures of AP1 to AP5 carry no clearance and no unit, so a skip keyed
    // on one draws all four of them; the long list is what shows it.
    const keyedOnUnit = await plantedView((t) => t.replace(LOOP, `${LOOP}    if (isObject(person) && person["org_unit"] === "ops") continue;\n`));
    expect(viewProblems(keyedOnUnit, PEOPLE)).toEqual([]);
    expect(viewProblems(keyedOnUnit, LONG).length).toBeGreaterThan(0);
  });

  it("AP11: the list check finds a path left out of the route list, an admin row given a route, and a scenario left unwritten", () => {
    const routesText = read(PAGES_DIR, "tree-govuk", "routes.yaml");
    const functionsText = read(PAGES_DIR, "FUNCTIONS.yaml");
    expect(listProblems(routesText, functionsText)).toEqual([]);
    expect(listProblems("routes:\n  - /help\n", functionsText).join("\n")).toMatch(/is not in the route list/);
    const routed = functionsText.replace(/(- id: admin\n(?:    .*\n)*?    route: )""/, `$1"${PATH}"`);
    expect(routed).not.toBe(functionsText);
    expect(listProblems(routesText, routed).join("\n")).toMatch(/while the function is not complete/);
    const unwritten = functionsText.replace(/(- id: admin\n(?:    .*\n)*?    scenario: )"[^"]*"/, '$1""');
    expect(unwritten).not.toBe(functionsText);
    expect(listProblems(routesText, unwritten).join("\n")).toMatch(/scenario is ""/);
  });

  it("AP11: the fixture Conduit refuses what the real one refuses and serves what it serves: no bearer, an unknown bearer, a bearer in the query, a missing right, a method, a body, a path", async () => {
    const token = bearer();
    const holder = bearer();
    const conduit = await adminConduit({ readers: [{ token, rights: ["create_case"] }, { token: holder, rights: [MANAGE_PEOPLE] }], people: PEOPLE });
    conduits.push(conduit);
    const ask = async (path: string, init: RequestInit = {}) => {
      const res = await fetch(`${conduit.url}${path}`, init);
      return { status: res.status, body: (await res.json()) as unknown };
    };
    const as = (who: string, method = "GET", body?: string): RequestInit => ({ method, headers: { Authorization: `Bearer ${who}` }, ...(body === undefined ? {} : { body }) });
    const NOT_AUTHENTICATED = { status: 401, body: { detail: "Not authenticated" } };
    const NOT_ALLOWED = { status: 405, body: { detail: "Method Not Allowed" } };
    for (const route of ["/v1/admin/people", "/v1/admin/people/rows", "/v1/admin/roles"]) {
      expect(await ask(route), route).toEqual(NOT_AUTHENTICATED);
      expect(await ask(route, as(bearer())), route).toEqual(NOT_AUTHENTICATED);
      expect(await ask(`${route}?access_token=${holder}`), route).toEqual(NOT_AUTHENTICATED);
      expect(await ask(route, as(token)), route).toEqual({ status: 403, body: REFUSAL });
      expect((await ask(route, as(holder))).status, route).toBe(200);
      // No route serves these on a collection: the router answers first, for anyone.
      for (const method of ["PUT", "PATCH"]) expect(await ask(route, as(holder, method, "{}")), `${method} ${route}`).toEqual(NOT_ALLOWED);
      expect(await ask(route, { method: "PUT" }), `PUT ${route}, no bearer`).toEqual(NOT_ALLOWED);
    }
    // The real routes serve a POST on the people (the invite) and the roles (a custom role): the same bearer and right first, then the
    // body's own model (`InviteInput` needs clearance, org_unit and a username, in the order pydantic lists them: the parent `AccessInput`'s fields first; `CustomRoleInput` a name and rights). A POST on the rows route is not served.
    for (const [route, fields] of [["/v1/admin/people", ["clearance", "org_unit", "username"]], ["/v1/admin/roles", ["name", "rights"]]] as const) {
      expect(await ask(route, { method: "POST", body: "{}" }), `POST ${route}, no bearer`).toEqual(NOT_AUTHENTICATED);
      expect(await ask(route, as(bearer(), "POST", "{}")), `POST ${route}, unknown bearer`).toEqual(NOT_AUTHENTICATED);
      expect(await ask(route, as(token, "POST", "{}")), `POST ${route}, no right`).toEqual({ status: 403, body: REFUSAL });
      expect(await ask(route, as(token, "POST", "not json")), `POST ${route}, no right, bad body`).toEqual({ status: 403, body: REFUSAL });
      const refused = await ask(route, as(holder, "POST", "{}"));
      expect(refused.status, `POST ${route}`).toBe(422);
      expect((refused.body as { detail: { type: string; loc: unknown[]; msg: string }[] }).detail.map((d) => [d.type, d.loc, d.msg]), `POST ${route}`).toEqual(
        fields.map((field) => ["missing", ["body", field], "Field required"]),
      );
      expect((await ask(route, as(holder, "POST", "not json"))).status, `POST ${route}, not json`).toBe(422);
    }
    // A body with only the username (what the fixture once let through) is refused for the two fields `AccessInput` requires.
    const partial = await ask("/v1/admin/people", as(holder, "POST", JSON.stringify({ username: "new.person" })));
    expect(partial.status, "POST /v1/admin/people with a username alone").toBe(422);
    expect((partial.body as { detail: { loc: unknown[] }[] }).detail.map((d) => d.loc)).toEqual([["body", "clearance"], ["body", "org_unit"]]);
    expect(await ask("/v1/admin/people/rows", as(holder, "POST", "{}")), "POST on the rows route").toEqual(NOT_ALLOWED);
    expect(await ask("/v1/admin/nothing", as(holder))).toEqual({ status: 404, body: { detail: "Not Found" } });
    expect(((await ask("/v1/admin/people", as(holder))).body as unknown[]).length).toBe(PEOPLE.length);
    // Every one of those calls was recorded, so that a page's test can say what it asked.
    expect(conduit.calls.length).toBeGreaterThan(30);
  });
});
