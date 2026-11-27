/**
 * New case as a GOV.UK form, scripts off (slice GR1b; ADR-152 decisions 1, 4, 5, 6, 7 and 12; ADR-099 Amendment 12 item 6; ADR-126;
 * FUNCTIONS row `cases-and-views`; scenario CS of `spec/08_ACCEPTANCE_SCENARIOS.md`, rows CS16 to CS33, written first; the owner's
 * rulings of 26 November 2026 on GR1b's draft, every proposal (a)). Rows CS16 to CS31 are the draft's table of cases 1 to 16.
 * `tests/glass_trees/test_govuk_cases_scenario.py` holds the scenario and this file in step: each case's id is a row of the scenario.
 *
 * The proof is the real service started for the GOV.UK tree, the real page list and a fixture Conduit that refuses what the real routes
 * refuse, in their order (`casesConduit.ts`). **A case is made as a browser makes it**: the form is read off the real page, filled by
 * its labels and sent with exactly the controls a browser would send, so a field the page names and the handler does not read, or the
 * other way round, fails here. A post "by hand" is what a person could send without the form.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - `dataset_ids` sent with a new dataset, or the dataset chosen before the radio was changed back remembered   -> CS16
 *  - the new dataset's name sent with an existing dataset                                                         -> CS17
 *  - an empty dataset name sent in place of the case's                                                            -> CS18
 *  - both names empty refused, or sent as anything but `Untitled case`                                            -> CS19
 *  - a pack's label sent in place of its id                                                                       -> CS20
 *  - `domains` left out with none ticked ("never chosen"), or the core model not said                             -> CS21
 *  - a taken name not said against the name field, words lost, or a case made                                     -> CS22
 *  - an existing dataset's refusal said as a name taken                                                           -> CS23
 *  - *New case* offered by the case level, or without `create_case`                                               -> CS24
 *  - an empty radio group, or datasets that could not be read drawn as none                                       -> CS25
 *  - the post outside the anti-forgery check                                                                      -> CS26
 *  - a failure said as a success, an ended session not said                                                       -> CS27
 *  - a second post (no 303), a banner said twice, by another case or by an address                                -> CS28
 *  - a control with no label, out of the tab order, or not native                                                 -> CS29
 *  - a script, or a field hidden until a script shows it                                                          -> CS30
 *  - a dataset's id printed                                                                                       -> CS31
 *  - a field of `Dataset` neither drawn nor left out, another address answered                                    -> CS32
 *  - a check that cannot fail, a fixture that grants what the route refuses                                       -> CS33
 */
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Express } from "express";
import { afterEach, describe, expect, it } from "vitest";
import type * as Real from "@ospreyflow/glass-shared";
import { DOMAIN_PACKS, POLE_LABEL } from "@ospreyflow/glass-shared";

import { createApp } from "../../server/app.js";
import { PAGES } from "../../server/pageList.js";
import type * as Stub from "../../server/types/glassShared.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { CREATE_FIELDS, NEW_CASE_CENSUS } from "../../server/views/casesWords.js";
import { refusalWords } from "../../server/views/studioWords.js";
import { testClock } from "../support/clock.js";
import { cookieFrom, csrfFromPage, request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { bearer, providerFor, textOf } from "../support/studioWorld.js";
import { DATASET_REFUSED, casesConduit, datasetOf, rightRefusal } from "./casesConduit.js";
import type { Case, CasesConduit, CasesConduitOptions, Reader, UnitDataset } from "./casesConduit.js";

// The compiled service is checked against `server/types/glassShared.d.ts`; this holds each declaration New case added to the package's
// own type, so that a shape the package changes and the stub still has as it was fails `npm run typecheck`.
type Conforms<R, S> = R extends S ? true : never;
export const NEW_CASE_STUB_CONFORMS_TO_THE_PACKAGE: [
  Conforms<typeof Real.UNTITLED_CASE, typeof Stub.UNTITLED_CASE>,
  Conforms<typeof Real.datasetChoiceLabel, typeof Stub.datasetChoiceLabel>,
] = [true, true];

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const read = (...parts: string[]): string => readFileSync(join(...parts), "utf8");

const LIST = "/cases";
const FORM = "/cases?new=1";
const NOWHERE = "/nothing-is-served-here";
const pageOf = (id: string): string => `/cases?case=${encodeURIComponent(id)}`;
const studioOf = (id: string): string => `/?investigation=${encodeURIComponent(id)}&from=case&view=ingest`;

/** The owner's ruled words, written out here and not read from the page's own list. */
const SAID = {
  newCase: "New case",
  cannot: "You cannot make cases",
  nameRefused: "A dataset with that name may already exist. Choose another name",
  datasetRefused: "That dataset cannot be used for a new case",
  made: "Case made. Its data is loaded in the Ingest Studio",
  question: "What data does this case read?",
  makeNew: "Make a new dataset — empty, loaded in the Ingest Studio",
  useExisting: "Use an existing dataset…",
  caseName: "Case name",
  datasetName: "Name of the new dataset",
  domains: "Domain models",
  create: "Create case",
} as const;

// ------------------------------------------------------------------------------------------------ the world

const conduits: CasesConduit[] = [];
afterEach(async () => {
  while (conduits.length > 0) await conduits.pop()?.stop();
});

const UNIT = "harbour-unit";
const CREATOR = ["create_case", "investigate"];

const QUAY = "ds-01HQUAY7";
const GATE = "ds-01HGATE3";
const BOTH = "ds-01HBOTH9";
const LIVE = "ds-01HLIVE5";
const DRAWN = "ds-01HDRAWN2";
const ELSEWHERE = "ds-01HOTHER8";
const DATASETS: UnitDataset[] = [
  { id: QUAY, name: "Quay ledger", owning_unit: UNIT },
  { id: BOTH, name: "Quay and gate together", owning_unit: UNIT, kind: "composite", members: [QUAY, GATE] },
  { id: LIVE, name: "Ledger with a model", owning_unit: UNIT, live_packs: ["stix"] },
  { id: GATE, name: "Gate camera log", owning_unit: UNIT },
  { id: DRAWN, name: "A board's drawing", owning_unit: UNIT, kind: "drawn" },
  { id: ELSEWHERE, name: "Another unit's extract", owning_unit: "other-unit" },
];
const EVERY_ID = DATASETS.map((d) => d.id);
/** The labels of the datasets the unit offers, in the order the route sends them (by name). */
const OFFERED_LABELS = ["Gate camera log", "Ledger with a model", "Quay and gate together (a composite of 2 datasets)", "Quay ledger"];

const CASES: Case[] = [
  {
    id: "c-harbour",
    name: "Wharf watch",
    created_at: "2026-08-01T09:05:00Z",
    created_by: "acct-blake",
    owning_unit: UNIT,
    domains: ["fibo"],
    datasets: [{ id: QUAY, name: "Quay ledger" }],
    brief: { priority: "", requirements: [] },
  },
];
const LEVELS: Reader["levels"] = { "c-harbour": "author" };

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
  tree?: "govuk" | "default";
  conduitUrl?: string;
}

async function signedIn(app: Express): Promise<{ cookie: string; csrf: string }> {
  const res = await request(app).get("/session/sign-in");
  if (res.status !== 302) throw new Error(`sign-in answered ${res.status}`);
  const cookie = cookieFrom(res);
  const home = await request(app).get("/").set("Cookie", cookie);
  return { cookie, csrf: csrfFromPage(home.text) };
}

async function world(options: WorldOptions = {}): Promise<World> {
  const token = bearer();
  const reader: Reader = { token, unit: UNIT, rights: options.rights ?? CREATOR, levels: { ...(options.levels ?? LEVELS) }, hidden: [] };
  const { rights: _r, levels: _l, tree: _t, conduitUrl: _c, ...answers } = options;
  const conduit = await casesConduit({ ...answers, readers: [reader], cases: options.cases ?? CASES, datasets: options.datasets ?? DATASETS });
  conduits.push(conduit);
  const app = createApp({
    store: new MemorySessionStore({ clock: testClock() }),
    identityProvider: providerFor(token),
    sessionSecret: generateSecret(48),
    pages: PAGES,
    tree: options.tree ?? "govuk",
    // The sign-in's report to the Conduit is not awaited and could arrive among a test's calls: this page's calls are what is counted.
    sessionEvents: { report: async () => undefined, settled: async () => undefined, misses: 0 },
    forward: { conduitUrl: options.conduitUrl ?? conduit.url, bodyMaxBytes: 1024, uploadMaxBytes: 1024, upstreamTimeoutSeconds: 2 },
  });
  const signed = await signedIn(app);
  conduit.calls.splice(0);
  return { app, conduit, reader, ...signed };
}

const getAs = (w: World, path: string) => request(w.app).get(path).set("Cookie", w.cookie);
/** A post of these pairs, in order, as the signed-in person; `_csrf` is the session's unless the pairs hold one or `token` is false. */
function postAs(w: World, path: string, pairs: [string, string][], token = true) {
  const all: [string, string][] = token && !pairs.some(([name]) => name === "_csrf") ? [["_csrf", w.csrf], ...pairs] : pairs;
  return request(w.app).post(path).set("Cookie", w.cookie).type("form").send(new URLSearchParams(all).toString());
}

const calls = (c: CasesConduit): string[] => c.calls.map((call) => `${call.method} ${call.url}`);
const posts = (c: CasesConduit): Record<string, unknown>[] => c.calls.filter((call) => call.method === "POST").map((call) => JSON.parse(call.body) as Record<string, unknown>);
const size = (c: CasesConduit): { cases: number; datasets: number } => ({ cases: c.cases.length, datasets: c.datasets.length });

async function closedAddress(): Promise<string> {
  const server = createServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  await new Promise<void>((resolve) => server.close(() => resolve()));
  return `http://127.0.0.1:${port}`;
}

// ------------------------------------------------------------------------------------------------ reading a page

const strip = (html: string): string => html.replace(/<!--[\s\S]*?-->/g, "");
const unescape = (s: string): string => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
const attr = (tag: string, name: string): string | undefined => {
  const found = new RegExp(`(?:^|\\s)${name}="([^"]*)"`).exec(tag)?.[1];
  return found === undefined ? undefined : unescape(found);
};
const flag = (tag: string, name: string): boolean => new RegExp(`(?:^|\\s)${name}(?=\\s|=|/|$)`).test(tag.replace(/="[^"]*"/g, '=""'));
const withoutNonce = (html: string): string => html.replace(/nonce="[^"]*"/g, 'nonce="N"');
const said = (html: string): string => unescape(textOf(html)).replace(/\s+/g, " ").trim();

function mainOf(html: string): string {
  const found = /<main\b[^>]*>([\s\S]*?)<\/main>/.exec(strip(html));
  return found ? (found[1] as string) : "";
}
const mainText = (html: string): string => said(mainOf(html));
const h1sOf = (html: string): string[] => [...mainOf(html).matchAll(/<h1\b[^>]*>([\s\S]*?)<\/h1>/g)].map((m) => said(m[1] as string));

interface Control {
  type: string;
  name: string;
  id: string;
  value: string;
  checked: boolean;
  label: string;
  tag: string;
}

function labelsOf(html: string): Map<string, string> {
  return new Map([...strip(html).matchAll(/<label\b([^>]*)>([\s\S]*?)<\/label>/g)].map((m) => [attr(m[1] as string, "for") ?? "", said(m[2] as string)]));
}

/** The New case form of a page: its method, its action and its inputs in the page's order; `undefined` when there is none. */
function formOf(html: string): { method: string; action: string; inner: string; controls: Control[] } | undefined {
  const forms = [...mainOf(html).matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/g)];
  if (forms.length !== 1) return undefined;
  const tag = (forms[0] as RegExpMatchArray)[1] as string;
  const inner = (forms[0] as RegExpMatchArray)[2] as string;
  const labels = labelsOf(html);
  const controls = [...inner.matchAll(/<input\b([^>]*)>/g)].map((m): Control => {
    const a = m[1] as string;
    const type = attr(a, "type") ?? "text";
    const id = attr(a, "id") ?? "";
    return { type, name: attr(a, "name") ?? "", id, value: attr(a, "value") ?? (type === "checkbox" ? "on" : ""), checked: flag(a, "checked"), label: labels.get(id) ?? "", tag: a };
  });
  return { method: attr(tag, "method") ?? "", action: attr(tag, "action") ?? "", inner, controls };
}

interface Edits {
  /** Text typed into the field with this label. */
  type?: Record<string, string>;
  /** Radios chosen, by label. */
  choose?: string[];
  /** Boxes ticked, by label. */
  tick?: string[];
}

/** What a browser would send for this form once filled so: each text and hidden field, each checked radio and box, in the page's order.
 * Throws when a label names no control of the page's form. */
function filled(html: string, edits: Edits = {}): [string, string][] {
  const form = formOf(html);
  if (!form) throw new Error(`the page has no one form: ${mainText(html).slice(0, 200)}`);
  const controls = form.controls.map((c) => ({ ...c }));
  const labelled = (label: string, types: string[]): Control => {
    const found = controls.filter((c) => types.includes(c.type) && c.label === label);
    if (found.length !== 1) throw new Error(`${found.length} ${types.join("/")} controls are labelled ${JSON.stringify(label)}`);
    return found[0] as Control;
  };
  for (const [label, text] of Object.entries(edits.type ?? {})) labelled(label, ["text"]).value = text;
  for (const label of edits.choose ?? []) {
    const radio = labelled(label, ["radio"]);
    for (const other of controls) if (other.type === "radio" && other.name === radio.name) other.checked = false;
    radio.checked = true;
  }
  for (const label of edits.tick ?? []) labelled(label, ["checkbox"]).checked = true;
  return controls.filter((c) => (c.type === "radio" || c.type === "checkbox" ? c.checked : true)).map((c) => [c.name, c.value]);
}

/** The form read off the real page, filled and sent where the form says. */
async function submit(w: World, edits: Edits = {}) {
  const page = await getAs(w, FORM);
  expect(page.status, "the form").toBe(200);
  const form = formOf(page.text);
  const pairs = filled(page.text, edits);
  w.conduit.calls.splice(0);
  const res = await request(w.app)[(form?.method ?? "get") === "post" ? "post" : "get"](form?.action ?? "")
    .set("Cookie", w.cookie)
    .type("form")
    .send(new URLSearchParams(pairs).toString());
  return { res, pairs, page: page.text };
}

// ------------------------------------------------------------------------------------------------ the checks, each shown red in CS33

/** The one create call's body is exactly this: the same fields, no other, the same values. */
function bodyProblems(sent: Record<string, unknown>[], want: Record<string, unknown>): string[] {
  if (sent.length !== 1) return [`${sent.length} POSTs were sent, not one`];
  const body = sent[0] as Record<string, unknown>;
  const ordered = (o: Record<string, unknown>): string => JSON.stringify(Object.keys(o).sort().map((k) => [k, o[k]]));
  return ordered(body) === ordered(want) ? [] : [`the page sent ${JSON.stringify(body)}, not ${JSON.stringify(want)}`];
}

const bannerOf = (html: string): string | undefined => /<div class="govuk-notification-banner\b[\s\S]*?govuk-notification-banner__content">([\s\S]*?)<\/div>/.exec(mainOf(html))?.[1];

/** The made case's banner: the ruled words, and a link to the Studio exactly when a new dataset was made (`studio` its address). */
function bannerProblems(html: string, studio: string | undefined): string[] {
  const banner = bannerOf(html);
  if (banner === undefined) return ["there is no banner"];
  const found: string[] = [];
  if (!said(banner).startsWith(SAID.made)) found.push(`the banner says ${JSON.stringify(said(banner))}`);
  const links = [...banner.matchAll(/<a\b([^>]*)>/g)].map((m) => attr(m[1] as string, "href"));
  if (JSON.stringify(links) !== JSON.stringify(studio === undefined ? [] : [studio])) found.push(`the banner's links are ${JSON.stringify(links)}, not ${JSON.stringify(studio ?? null)}`);
  if (studio !== undefined && !/<a\b[^>]*>[^<]*Ingest Studio[^<]*<\/a>/.test(banner)) found.push("the link does not name the Ingest Studio");
  return found;
}

const noBannerProblems = (html: string): string[] => (bannerOf(html) === undefined && !mainText(html).includes("Case made") ? [] : ["the page says a case was made"]);

/** The innermost fieldset holding the element with this id: its opening tag's attributes. */
function fieldsetAround(html: string, id: string): string | undefined {
  const page = strip(html);
  const at = page.indexOf(` id="${id}"`);
  const open: string[] = [];
  for (const m of page.matchAll(/<fieldset\b([^>]*)>|<\/fieldset>/g)) {
    if ((m.index ?? 0) > at) break;
    if (m[0] === "</fieldset>") open.pop();
    else open.push(m[1] as string);
  }
  return at === -1 ? undefined : open.at(-1);
}

/** Whether `tag`'s `aria-describedby` names an error message that says `sentence`. */
function describedByError(html: string, tag: string, sentence: string): boolean {
  const ids = (attr(tag, "aria-describedby") ?? "").split(/\s+/);
  return [...strip(html).matchAll(/<p\b([^>]*)>([\s\S]*?)<\/p>/g)].some(
    (m) => ids.includes(attr(m[1] as string, "id") ?? "none") && (attr(m[1] as string, "class") ?? "").includes("govuk-error-message") && said(m[2] as string).includes(sentence),
  );
}

/** A refused form: the GOV.UK error summary with the one sentence, linked to the thing it is against, and the same sentence there.
 * `against` is the new dataset's name field, or the choice of dataset. */
function errorProblems(html: string, sentence: string, against: "name" | "choice"): string[] {
  const found: string[] = [];
  if (!/<title>Error: /.test(html)) found.push("the title does not start with Error:");
  const summary = /<div class="govuk-error-summary">([\s\S]*?)<\/ul>/.exec(mainOf(html))?.[1];
  if (summary === undefined || !/role="alert"/.test(summary)) return [...found, "there is no error summary announced as an alert"];
  const links = [...summary.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)].map((m) => ({ href: attr(m[1] as string, "href") ?? "", text: said(m[2] as string) }));
  if (JSON.stringify(links.map((l) => l.text)) !== JSON.stringify([sentence])) found.push(`the summary says ${JSON.stringify(links.map((l) => l.text))}`);
  const other = sentence === SAID.nameRefused ? SAID.datasetRefused : SAID.nameRefused;
  if (mainText(html).includes(other)) found.push(`the page also says ${JSON.stringify(other)}`);
  const controls = formOf(html)?.controls ?? [];
  const id = (links[0]?.href ?? "").replace(/^#/, "");
  const target = controls.find((c) => c.id === id);
  if (!target) return [...found, `the summary links to ${JSON.stringify(links[0]?.href)}, which is no control of the form`];
  if (against === "name") {
    if (target.label !== SAID.datasetName) found.push(`the summary links to ${JSON.stringify(target.label)}, not the new dataset's name`);
    if (!describedByError(html, target.tag, sentence)) found.push("the name field is not described by the error");
  } else {
    const hasDatasets = controls.some((c) => c.name === "dataset_id");
    if (target.type !== "radio" || target.name !== (hasDatasets ? "dataset_id" : "data")) found.push(`the summary links to ${JSON.stringify(target.label)}, not the choice of dataset`);
    const fieldset = fieldsetAround(html, id);
    if (fieldset === undefined || !describedByError(html, fieldset, sentence)) found.push("the choice is not described by the error");
  }
  return found;
}

/** The refused form holds what was sent: sending it again unchanged sends the same. */
function keptProblems(html: string, sent: [string, string][]): string[] {
  const again = filled(html);
  return JSON.stringify(again) === JSON.stringify(sent) ? [] : [`the form holds ${JSON.stringify(again)}, not ${JSON.stringify(sent)}`];
}

const madeNothingProblems = (c: CasesConduit, before: { cases: number; datasets: number }): string[] =>
  JSON.stringify(size(c)) === JSON.stringify(before) ? [] : [`the store holds ${JSON.stringify(size(c))}, not ${JSON.stringify(before)}`];

/** The links to the New case form on a page's main landmark. */
const newCaseLinks = (html: string): string[] => [...mainOf(html).matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)].filter((m) => attr(m[1] as string, "href") === FORM || said(m[2] as string) === SAID.newCase).map((m) => `${attr(m[1] as string, "href") ?? ""} ${said(m[2] as string)}`);
const offeredProblems = (html: string, offered: boolean): string[] =>
  JSON.stringify(newCaseLinks(html)) === JSON.stringify(offered ? [`${FORM} ${SAID.newCase}`] : []) ? [] : [`New case's links are ${JSON.stringify(newCaseLinks(html))}`];

/** With no dataset sent: one radio, the new dataset, checked; no group of datasets, and no group with nothing in it. */
function noDatasetProblems(html: string): string[] {
  const found: string[] = [];
  const radios = (formOf(html)?.controls ?? []).filter((c) => c.type === "radio");
  if (JSON.stringify(radios.map((r) => [r.label, r.checked])) !== JSON.stringify([[SAID.makeNew, true]])) found.push(`the radios are ${JSON.stringify(radios.map((r) => r.label))}`);
  if (mainText(html).includes(SAID.useExisting)) found.push("an existing dataset is offered");
  for (const m of mainOf(html).matchAll(/<fieldset\b[^>]*>(?:(?!<fieldset\b)[\s\S])*?<\/fieldset>/g)) if (!/<input\b/.test(m[0])) found.push("a group has nothing in it");
  return found;
}

/** No dataset's id anywhere on the page but in a control's value. */
const idProblems = (html: string): string[] => {
  const rest = html.replace(/\svalue="[^"]*"/g, "");
  return EVERY_ID.filter((id) => rest.includes(id)).map((id) => `the page shows ${id} outside a value`);
};

const notMadeProblems = (res: { status: number; text: string }): string[] => {
  const found: string[] = [];
  if (res.status !== 502) found.push(`the status is ${res.status}`);
  const alert = /<p role="alert">([\s\S]*?)<\/p>/.exec(mainOf(res.text))?.[1] ?? "";
  if (!/could not be made/.test(said(alert)) || !/nothing was made/i.test(said(alert))) found.push(`the alert says ${JSON.stringify(said(alert))}`);
  if (!/<a href="\/cases">/.test(mainOf(res.text))) found.push("there is no way to the list of cases");
  return [...found, ...noBannerProblems(res.text)];
};

const formUnreadableProblems = (res: { status: number; text: string }): string[] => {
  const found: string[] = [];
  if (res.status !== 502) found.push(`the status is ${res.status}`);
  if (/<form\b/.test(mainOf(res.text)) || /<input\b/.test(mainOf(res.text))) found.push("a form is drawn from a read that failed");
  if (!/<p role="alert">[^<]*could not be read/.test(mainOf(res.text))) found.push("the failure is not said as an alert");
  return found;
};

/** One case made is one POST: nothing in these calls sends it again. */
const onePostProblems = (made: string[]): string[] => {
  const sent = made.filter((call) => call.startsWith("POST "));
  return sent.length === 1 && sent[0] === "POST /v1/investigations" ? [] : [`the POSTs are ${JSON.stringify(sent)}`];
};

/** The form's stops in the page's order, each said by its label, with the groups they are in. */
const FORM_STOPS = [
  "Skip to main content",
  "Sign out",
  SAID.caseName,
  SAID.makeNew,
  SAID.datasetName,
  SAID.useExisting,
  ...OFFERED_LABELS,
  ...DOMAIN_PACKS.map((p) => p.label),
  SAID.create,
  "Back to your cases",
  "Back to Home",
];

function stopProblems(html: string): string[] {
  const page = strip(html);
  const labels = labelsOf(html);
  const found: string[] = [];
  const stops: string[] = [];
  for (const m of page.matchAll(/<(a|button)\b([^>]*)>([\s\S]*?)<\/\1>|<(input|select|textarea)\b([^>]*)>/g)) {
    const a = (m[2] ?? m[5]) as string;
    if (attr(a, "type") === "hidden") continue;
    if (m[4] !== undefined) {
      const label = labels.get(attr(a, "id") ?? "");
      if (label === undefined || label === "") found.push(`a control with no label: ${a}`);
      stops.push(label ?? "");
    } else stops.push(said(m[3] as string));
    if (flag(a, "tabindex") || flag(a, "disabled")) found.push(`a stop taken out of the order or disabled: ${a}`);
  }
  if (JSON.stringify(stops) !== JSON.stringify(FORM_STOPS)) found.push(`the stops are ${JSON.stringify(stops)}`);
  const ids = [...page.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1] as string);
  if (new Set(ids).size !== ids.length) found.push("an id is used twice");
  const groups = (name: string): string[] => (formOf(html)?.controls ?? []).filter((c) => c.name === name).map((c) => `${c.type} ${c.label}`);
  if (JSON.stringify(groups("data")) !== JSON.stringify([`radio ${SAID.makeNew}`, `radio ${SAID.useExisting}`])) found.push(`the data group is ${JSON.stringify(groups("data"))}`);
  if (JSON.stringify(groups("dataset_id")) !== JSON.stringify(OFFERED_LABELS.map((l) => `radio ${l}`))) found.push(`the dataset group is ${JSON.stringify(groups("dataset_id"))}`);
  const legends = [...page.matchAll(/<fieldset\b[^>]*>\s*<legend\b[^>]*>([\s\S]*?)<\/legend>/g)].map((m) => said(m[1] as string));
  if (legends.length !== [...page.matchAll(/<fieldset\b/g)].length || legends[0] !== SAID.question || !legends.includes(SAID.domains)) found.push(`the groups' legends are ${JSON.stringify(legends)}`);
  if (!/<button\b[^>]*type="submit"[^>]*>\s*Create case\s*<\/button>/.test(formOf(html)?.inner ?? "")) found.push("the form has no submit button");
  return found;
}

/** Everything that needs a script, an inline rule, or shows a field only once a script has run. */
function scriptsOffProblems(html: string): string[] {
  const page = strip(html);
  const found: string[] = [];
  for (const s of page.matchAll(/<script\b([^>]*)>/g)) if (attr(s[1] as string, "type") !== "application/json") found.push(`a script element: ${s[0]}`);
  if (/\son[a-z]+\s*=/i.test(page)) found.push("an event-handler attribute");
  if (/\sstyle\s*=|<style\b/i.test(page)) found.push("an inline style");
  if (/javascript:/i.test(page)) found.push("a javascript: address");
  for (const m of mainOf(html).matchAll(/<(?!input\b)[a-z0-9]+\b([^>]*)>/g)) if (flag(m[1] as string, "hidden") || /--hidden/.test(m[1] as string)) found.push(`something hidden: ${m[0]}`);
  const form = formOf(html);
  if (!form || form.method !== "post" || form.action !== FORM) found.push("the form does not post to its own address");
  return found;
}

const sources = (): { name: string; text: string }[] => ["server/cases.ts", "server/views/casesWords.ts", "tree-govuk/cases.njk", "tree-govuk/new-case.njk"].map((name) => ({ name, text: read(PAGES_DIR, name) }));
const withoutComments = (text: string): string => text.replace(/\/\*[\s\S]*?\*\/|\/\/.*$|\{#[\s\S]*?#\}/gm, "");
const AMERICAN = /\b(?:color|colors|organization|organizations|center|centers|authorize|authorized|behavior|license|licenses|analyze|favorite|catalog)\b/gi;

// ------------------------------------------------------------------------------------------------ the cases

describe("New case on the GOV.UK tree (scenario CS)", () => {
  it("CS16: a new dataset is one POST with the case's name, the new dataset's name and the packs and nothing else, then a 303 to the case and the banner", async () => {
    const w = await world();
    const before = size(w.conduit);
    // A dataset chosen before the radio is back on "Make a new dataset" is forgotten: it is in the form and never sent.
    const { res, pairs } = await submit(w, { type: { [SAID.caseName]: "Harbour thefts", [SAID.datasetName]: "Harbour 2026" }, choose: ["Quay ledger"] });
    expect(pairs).toContainEqual(["dataset_id", QUAY]);
    expect(res.status).toBe(303);
    expect(res.headers["location"]).toBe(pageOf("c-made-1"));
    expect(calls(w.conduit)).toEqual(["POST /v1/investigations"]);
    expect(bodyProblems(posts(w.conduit), { name: "Harbour thefts", new_dataset_name: "Harbour 2026", domains: [] })).toEqual([]);
    const sent = w.conduit.calls[0] as CasesConduit["calls"][number];
    expect(sent.headers["authorization"]).toBe(`Bearer ${w.reader.token}`);
    for (const header of ["cookie", "origin", "referer", "x-csrf-token"]) expect(sent.headers[header], header).toBeUndefined();
    expect(sent.body).not.toContain(w.csrf);
    expect(sent.body).not.toContain("_csrf");
    expect(size(w.conduit)).toEqual({ cases: before.cases + 1, datasets: before.datasets + 1 });
    const made = await getAs(w, pageOf("c-made-1"));
    expect(made.status).toBe(200);
    expect(h1sOf(made.text)).toEqual(["Harbour thefts"]);
    expect(mainText(made.text)).toContain("Harbour 2026");
    expect(bannerProblems(made.text, studioOf("c-made-1"))).toEqual([]);
    // "Who made it" is left out for 0.7.0.
    expect(made.text).not.toContain("acct-made");
    expect(mainText(made.text)).not.toMatch(/made by|created by/i);
  });

  it("CS17: an existing dataset is sent by its id with no new dataset's name, whatever was typed there, and the banner has no link to the Studio", async () => {
    const w = await world();
    const before = size(w.conduit);
    const { res } = await submit(w, { type: { [SAID.caseName]: "Gate study", [SAID.datasetName]: "leftover words" }, choose: [SAID.useExisting, "Gate camera log"] });
    expect(res.status).toBe(303);
    expect(res.headers["location"]).toBe(pageOf("c-made-1"));
    expect(bodyProblems(posts(w.conduit), { name: "Gate study", dataset_ids: [GATE], domains: [] })).toEqual([]);
    expect(size(w.conduit)).toEqual({ cases: before.cases + 1, datasets: before.datasets });
    const made = await getAs(w, pageOf("c-made-1"));
    expect(bannerProblems(made.text, undefined)).toEqual([]);
    expect(mainText(made.text)).toContain("Gate camera log");
  });

  it("CS18: a new dataset's name left empty, or all spaces, takes the case's", async () => {
    for (const typed of ["", "   "]) {
      const w = await world();
      const { res } = await submit(w, { type: { [SAID.caseName]: "  Harbour thefts  ", [SAID.datasetName]: typed } });
      expect(res.status, JSON.stringify(typed)).toBe(303);
      expect(bodyProblems(posts(w.conduit), { name: "Harbour thefts", new_dataset_name: "Harbour thefts", domains: [] })).toEqual([]);
    }
  });

  it("CS19: both names left empty are `Untitled case`, for the case and for its new dataset, and nothing of the person's is refused", async () => {
    const w = await world();
    const { res } = await submit(w, { type: { [SAID.caseName]: "  " } });
    expect(res.status).toBe(303);
    expect(bodyProblems(posts(w.conduit), { name: "Untitled case", new_dataset_name: "Untitled case", domains: [] })).toEqual([]);
    expect(h1sOf((await getAs(w, pageOf("c-made-1"))).text)).toEqual(["Untitled case"]);
    // An existing dataset with no case name: the case is `Untitled case`.
    const second = await submit(w, { choose: [SAID.useExisting, "Gate camera log"] });
    expect(second.res.status).toBe(303);
    expect(bodyProblems(posts(w.conduit), { name: "Untitled case", dataset_ids: [GATE], domains: [] })).toEqual([]);
    // A dataset named and the case not: only the case is `Untitled case`.
    const third = await submit(w, { type: { [SAID.datasetName]: "Named all the same" } });
    expect(third.res.status).toBe(303);
    expect(bodyProblems(posts(w.conduit), { name: "Untitled case", new_dataset_name: "Named all the same", domains: [] })).toEqual([]);
    // Now a dataset called `Untitled case` exists: asking for it again is refused as a taken name is, the fields still empty.
    const again = await submit(w);
    expect(again.res.status).toBe(422);
    expect(errorProblems(again.res.text, SAID.nameRefused, "name")).toEqual([]);
    expect(keptProblems(again.res.text, again.pairs)).toEqual([]);
  });

  it("CS20: three boxes labelled as the shared package labels the packs; those ticked are sent by id, one as a list of one", async () => {
    const w = await world();
    const form = formOf((await getAs(w, FORM)).text);
    const boxes = (form?.controls ?? []).filter((c) => c.type === "checkbox");
    expect(boxes.map((b) => [b.value, b.label, b.checked])).toEqual(DOMAIN_PACKS.map((p) => [p.name, p.label, false]));
    const two = await submit(w, { type: { [SAID.caseName]: "Two packs" }, tick: [DOMAIN_PACKS[0]?.label ?? "", DOMAIN_PACKS[2]?.label ?? ""] });
    expect(two.res.status).toBe(303);
    expect(bodyProblems(posts(w.conduit), { name: "Two packs", new_dataset_name: "Two packs", domains: ["fibo", "stix"] })).toEqual([]);
    const one = await submit(w, { type: { [SAID.caseName]: "One pack" }, tick: [DOMAIN_PACKS[1]?.label ?? ""] });
    expect(one.res.status).toBe(303);
    expect(bodyProblems(posts(w.conduit), { name: "One pack", new_dataset_name: "One pack", domains: ["niem"] })).toEqual([]);
    const made = await getAs(w, one.res.headers["location"] as string);
    expect(mainText(made.text)).toContain(DOMAIN_PACKS[1]?.label ?? "none");
    // By hand, something that is no pack goes to the route as sent, and its refusal makes nothing: the page drops nothing of what was sent.
    const before = size(w.conduit);
    w.conduit.calls.splice(0);
    const labels = await postAs(w, FORM, [["name", "By hand"], ["data", "new"], ["domains", "fibo"], ["domains", DOMAIN_PACKS[1]?.label ?? ""]]);
    expect(posts(w.conduit)[0]?.["domains"]).toEqual(["fibo", DOMAIN_PACKS[1]?.label]);
    expect(notMadeProblems(labels)).toEqual([]);
    expect(madeNothingProblems(w.conduit, before)).toEqual([]);
  });

  it("CS21: none ticked sends `domains: []`, a choice, and the form drawn so says the core model beside the boxes", async () => {
    const w = await world();
    const domainsGroup = (html: string): string => {
      const first = formOf(html)?.controls.find((c) => c.type === "checkbox")?.id ?? "none";
      const group = [...mainOf(html).matchAll(/<fieldset\b[^>]*>(?:(?!<fieldset\b)[\s\S])*?<\/fieldset>/g)].find((m) => m[0].includes(`id="${first}"`));
      return said(group?.[0] ?? "");
    };
    const fresh = (await getAs(w, FORM)).text;
    expect(domainsGroup(fresh)).toContain(POLE_LABEL);
    expect(POLE_LABEL).toBe("Bespoke POLE (the core model)");
    const none = await submit(w, { type: { [SAID.caseName]: "No packs" } });
    expect(posts(w.conduit)[0]).toHaveProperty("domains", []);
    expect(mainText((await getAs(w, none.res.headers["location"] as string)).text)).toContain(POLE_LABEL);
    // Drawn again after a refusal: said with none ticked, and not with a box ticked.
    const refusedBare = await submit(w, { type: { [SAID.datasetName]: "Quay ledger" } });
    expect(refusedBare.res.status).toBe(422);
    expect(domainsGroup(refusedBare.res.text)).toContain(POLE_LABEL);
    const refusedTicked = await submit(w, { type: { [SAID.datasetName]: "Quay ledger" }, tick: [DOMAIN_PACKS[0]?.label ?? ""] });
    expect(domainsGroup(refusedTicked.res.text)).toContain(DOMAIN_PACKS[0]?.label ?? "none");
    expect(mainText(refusedTicked.res.text)).not.toContain(POLE_LABEL);
    // No route says to a person making a case which datasets have a live model, so the boxes are always sent, one with a model included
    // (the Conduit does not store them there), and the form says nothing of a dataset's model.
    const live = await submit(w, { type: { [SAID.caseName]: "On a model" }, choose: [SAID.useExisting, "Ledger with a model"], tick: [DOMAIN_PACKS[0]?.label ?? ""] });
    expect(bodyProblems(posts(w.conduit), { name: "On a model", dataset_ids: [LIVE], domains: ["fibo"] })).toEqual([]);
    expect(mainText(live.page)).not.toMatch(/model decides/i);
    const shown = mainText((await getAs(w, live.res.headers["location"] as string)).text);
    expect(shown).toContain(DOMAIN_PACKS[2]?.label ?? "none");
    expect(shown).not.toContain(DOMAIN_PACKS[0]?.label ?? "none");
  });

  it("CS22: a new dataset's name already taken is said against the name field, every word kept, and no case is made", async () => {
    const w = await world();
    const before = size(w.conduit);
    const { res, pairs } = await submit(w, {
      type: { [SAID.caseName]: ' Harbour "thefts" <2026> ', [SAID.datasetName]: "  quay   LEDGER " },
      choose: ["Gate camera log"],
      tick: [DOMAIN_PACKS[0]?.label ?? "", DOMAIN_PACKS[2]?.label ?? ""],
    });
    expect(res.status).toBe(422);
    expect(calls(w.conduit)).toEqual(["POST /v1/investigations", "GET /v1/datasets"]);
    expect(errorProblems(res.text, SAID.nameRefused, "name")).toEqual([]);
    expect(keptProblems(res.text, pairs)).toEqual([]);
    expect(res.text).not.toContain("<2026>");
    expect(res.text).not.toContain("dataset_refused");
    expect(h1sOf(res.text)).toEqual([SAID.newCase]);
    expect(madeNothingProblems(w.conduit, before)).toEqual([]);
    expect(noBannerProblems((await getAs(w, LIST)).text)).toEqual([]);
    // The name taken by the case's own, the dataset's field left empty: against the same field.
    const byCaseName = await submit(w, { type: { [SAID.caseName]: "Quay ledger" } });
    expect(byCaseName.res.status).toBe(422);
    expect(errorProblems(byCaseName.res.text, SAID.nameRefused, "name")).toEqual([]);
    expect(keptProblems(byCaseName.res.text, byCaseName.pairs)).toEqual([]);
  });

  it("CS23: a dataset that is not the unit's, or none chosen, is said against the choice and never as a name taken, and nothing is made", async () => {
    const w = await world();
    const before = size(w.conduit);
    for (const id of [ELSEWHERE, DRAWN, "no-such-dataset"]) {
      w.conduit.calls.splice(0);
      const res = await postAs(w, FORM, [["name", "By hand"], ["data", "existing"], ["new_dataset_name", ""], ["dataset_id", id]]);
      expect(res.status, id).toBe(422);
      expect(bodyProblems(posts(w.conduit), { name: "By hand", dataset_ids: [id], domains: [] }), id).toEqual([]);
      expect(errorProblems(res.text, SAID.datasetRefused, "choice"), id).toEqual([]);
      // The id posted is not offered, so it is not drawn at all; the branch and the words are kept.
      expect(res.text, id).not.toContain(id);
      // As a browser would send the form back: its checked radio comes where it is on the page, after the new dataset's name.
      expect(filled(res.text).filter(([name]) => name !== "_csrf"), id).toEqual([["name", "By hand"], ["new_dataset_name", ""], ["data", "existing"]]);
    }
    const none = await submit(w, { type: { [SAID.caseName]: "None chosen" }, choose: [SAID.useExisting] });
    expect(none.res.status).toBe(422);
    expect(bodyProblems(posts(w.conduit), { name: "None chosen", dataset_ids: [], domains: [] })).toEqual([]);
    expect(errorProblems(none.res.text, SAID.datasetRefused, "choice")).toEqual([]);
    expect(keptProblems(none.res.text, none.pairs)).toEqual([]);
    // A dataset the unit offers that the route refuses all the same (gone since the form was drawn): said so, and still chosen.
    const gone = await world({ create_answer: { status: 422, body: DATASET_REFUSED } });
    const kept = await submit(gone, { choose: [SAID.useExisting, "Gate camera log"], type: { [SAID.caseName]: "Gone" } });
    expect(kept.res.status).toBe(422);
    expect(errorProblems(kept.res.text, SAID.datasetRefused, "choice")).toEqual([]);
    expect(keptProblems(kept.res.text, kept.pairs)).toEqual([]);
    expect(madeNothingProblems(w.conduit, before)).toEqual([]);
    // With no dataset to offer, a post by hand for one is still said against the choice there is.
    const bare = await world({ datasets: [] });
    const byHand = await postAs(bare, FORM, [["name", "By hand"], ["data", "existing"], ["dataset_id", QUAY]]);
    expect(byHand.status).toBe(422);
    expect(errorProblems(byHand.text, SAID.datasetRefused, "choice")).toEqual([]);
  });

  it("CS24: New case is offered by `create_case` alone; without it there is no button, and the form and a post by hand say you cannot make cases", async () => {
    for (const levels of [LEVELS, {}]) {
      const creator = await world({ levels });
      const list = await getAs(creator, LIST);
      expect(list.status).toBe(200);
      expect(offeredProblems(list.text, true)).toEqual([]);
      expect(calls(creator.conduit)).toEqual(["GET /v1/investigations", "GET /v1/me/rights"]);
      // An Author of a case, without the right: no button.
      const other = await world({ levels, rights: ["investigate", "share_case"] });
      const without = await getAs(other, LIST);
      expect(without.status).toBe(200);
      expect(offeredProblems(without.text, false)).toEqual([]);
      expect(mainText(without.text)).not.toMatch(/could not be read/);
    }
    for (const rights of [["investigate"], []]) {
      const w = await world({ rights });
      const form = await getAs(w, FORM);
      expect(form.status).toBe(403);
      expect(h1sOf(form.text)).toEqual([SAID.cannot]);
      expect(formOf(form.text)).toBeUndefined();
      expect(calls(w.conduit)).toEqual(["GET /v1/me/rights"]);
      const before = size(w.conduit);
      for (const pairs of [[["name", "By hand"], ["data", "new"]], [["data", "existing"], ["dataset_id", QUAY]], [["data", "existing"]]] as [string, string][][]) {
        w.conduit.calls.splice(0);
        const res = await postAs(w, FORM, pairs);
        expect(res.status, JSON.stringify(pairs)).toBe(403);
        expect(h1sOf(res.text)).toEqual([SAID.cannot]);
        // The route judges the post: it is asked once, and nothing else.
        expect(calls(w.conduit)).toEqual(["POST /v1/investigations"]);
        expect(res.text).not.toContain("right_required");
        expect(res.text).not.toContain("create_case");
      }
      expect(madeNothingProblems(w.conduit, before)).toEqual([]);
    }
    // Rights that cannot be read offer nothing, the list says so, and the form is not drawn.
    const unread: WorldOptions[] = [
      { rights_answer: { status: 500, body: { detail: "boom" } } },
      { rights_answer: { status: 200, body: "not json" } },
      { rights_answer: { status: 200, body: { rights: "create_case" } } },
      { rights_answer: { status: 200, body: {} } },
      { rights_answer: { status: 200, body: { rights: [1, "create_case"] } } },
      { rights_no_answer: true },
    ];
    for (const options of unread) {
      const w = await world(options);
      const list = await getAs(w, LIST);
      expect(list.status, JSON.stringify(options)).toBe(200);
      expect(offeredProblems(list.text, false)).toEqual([]);
      expect(mainText(list.text)).toMatch(/could not be read.*New case/);
      expect(mainText(list.text)).toContain("Wharf watch");
      expect(formUnreadableProblems(await getAs(w, FORM)), JSON.stringify(options)).toEqual([]);
    }
    const ended = await world({ rights_answer: { status: 401, body: { detail: "Not authenticated" } } });
    for (const path of [LIST, FORM]) {
      const res = await getAs(ended, path);
      expect(res.status, path).toBe(401);
      expect(mainText(res.text)).toContain(said(refusalWords(401, undefined, "")));
    }
    // A list that cannot be read asks for no rights.
    const failed = await world({ list_answer: { status: 500, body: {} } });
    await getAs(failed, LIST);
    expect(calls(failed.conduit)).toEqual(["GET /v1/investigations"]);
  });

  it("CS25: with no dataset sent only a new one is offered, with no empty group; datasets that cannot be read draw no form", async () => {
    const w = await world({ datasets: [] });
    const page = await getAs(w, FORM);
    expect(page.status).toBe(200);
    expect(noDatasetProblems(page.text)).toEqual([]);
    expect(calls(w.conduit)).toEqual(["GET /v1/me/rights", "GET /v1/datasets"]);
    const { res } = await submit(w, { type: { [SAID.caseName]: "First of the unit" } });
    expect(res.status).toBe(303);
    const row = datasetOf(DATASETS[1] as UnitDataset);
    const failures: [string, WorldOptions][] = [
      ["a 500", { datasets_answer: { status: 500, body: { detail: "boom" } } }],
      ["a 403", { datasets_answer: { status: 403, body: rightRefusal("create_case") } }],
      ["text", { datasets_answer: { status: 200, body: "not json" } }],
      ["no list", { datasets_answer: { status: 200, body: { datasets: [] } } }],
      ["a row that is no object", { datasets_answer: { status: 200, body: [null] } }],
      ["no answer", { datasets_no_answer: true }],
      ["a kind the model has not", { datasets_answer: { status: 200, body: [{ ...row, kind: "folder" }] } }],
      ["a created_at that is no time", { datasets_answer: { status: 200, body: [{ ...row, created_at: "yesterday" }] } }],
    ];
    const fields = [...NEW_CASE_CENSUS.Dataset.drawn, ...NEW_CASE_CENSUS.Dataset.left];
    expect(fields.length).toBe(11);
    for (const field of fields) {
      const missing: Record<string, unknown> = { ...row };
      delete missing[field];
      failures.push([`${field} missing`, { datasets_answer: { status: 200, body: [missing] } }]);
      failures.push([`${field} of the wrong shape`, { datasets_answer: { status: 200, body: [{ ...row, [field]: { wrong: true } }] } }]);
    }
    for (const [label, options] of failures) {
      const broken = await world(options);
      expect(formUnreadableProblems(await getAs(broken, FORM)), label).toEqual([]);
    }
    const ended = await world({ datasets_answer: { status: 401, body: { detail: "Not authenticated" } } });
    const res401 = await getAs(ended, FORM);
    expect(res401.status).toBe(401);
    expect(mainText(res401.text)).toContain(said(refusalWords(401, undefined, "")));
    // A refusal whose form cannot be drawn again: the case was not made, and that is what is said.
    const refused = await world({ create_answer: { status: 422, body: DATASET_REFUSED }, datasets_answer: { status: 500, body: {} } });
    expect(notMadeProblems(await postAs(refused, FORM, [["name", "x"], ["data", "new"]]))).toEqual([]);
  });

  it("CS26: a post with no anti-forgery token, an empty one or another session's is refused and nothing is sent", async () => {
    const w = await world();
    const page = await getAs(w, FORM);
    expect(formOf(page.text)?.controls.filter((c) => c.name === "_csrf").map((c) => [c.type, c.value])).toEqual([["hidden", w.csrf]]);
    const theirs = await signedIn(w.app);
    expect(theirs.csrf).not.toBe(w.csrf);
    const before = size(w.conduit);
    const fields: [string, string][] = [["name", "Forged"], ["data", "new"]];
    for (const pairs of [fields, [["_csrf", ""], ...fields], [["_csrf", theirs.csrf], ...fields]] as [string, string][][]) {
      w.conduit.calls.splice(0);
      const res = await postAs(w, FORM, pairs, false);
      expect(res.status, JSON.stringify(pairs[0])).toBe(403);
      expect(res.text).toMatch(/could not be checked/i);
      expect(calls(w.conduit)).toEqual([]);
    }
    expect(madeNothingProblems(w.conduit, before)).toEqual([]);
    expect((await postAs(w, FORM, fields)).status).toBe(303);
  });

  it("CS27: no answer or a failing Conduit is a 502 saying nothing was made, with no banner; a 401 says to sign in again", async () => {
    const failures: [string, WorldOptions][] = [
      ["a 500", { create_answer: { status: 500, body: { detail: "boom" } } }],
      ["a 503", { create_answer: { status: 503, body: "down" } }],
      ["no answer", { create_no_answer: true }],
      ["a 200", { create_answer: { status: 200, body: "not json" } }],
      ["a body's 422", { create_answer: { status: 422, body: { detail: [{ type: "string_too_long", loc: ["body", "new_dataset_name"] }] } } }],
      ["another 422", { create_answer: { status: 422, body: { error: "something_else" } } }],
      ["a 409", { create_answer: { status: 409, body: { error: "conflict" } } }],
      ["a 404", { create_answer: { status: 404, body: { detail: "Not Found" } } }],
    ];
    for (const [label, options] of failures) {
      const w = await world(options);
      const res = await postAs(w, FORM, [["name", "Lost"], ["data", "new"]]);
      expect(notMadeProblems(res), label).toEqual([]);
      expect(res.text, label).not.toContain("boom");
      expect(noBannerProblems((await getAs(w, LIST)).text), label).toEqual([]);
      expect(noBannerProblems((await getAs(w, pageOf("c-harbour"))).text), label).toEqual([]);
    }
    const closed = await world({ conduitUrl: await closedAddress() });
    expect(notMadeProblems(await postAs(closed, FORM, [["name", "Lost"], ["data", "new"]]))).toEqual([]);
    const ended = await world({ create_answer: { status: 401, body: { detail: "Not authenticated" } } });
    const res = await postAs(ended, FORM, [["name", "Lost"], ["data", "new"]]);
    expect(res.status).toBe(401);
    expect(mainText(res.text)).toContain(said(refusalWords(401, undefined, "")));
    expect(noBannerProblems(res.text)).toEqual([]);
    // Made (a 201), with a body the page cannot read: never said as not made. The list shows what there is, with no banner.
    for (const body of ["not json", {}, { id: "../datasets" }, { id: "c-made-1" }]) {
      const w = await world({ create_answer: { status: 201, body } });
      const made = await postAs(w, FORM, [["name", "Made"], ["data", "new"]]);
      expect(made.status, JSON.stringify(body)).toBe(303);
      expect(made.headers["location"]).toBe(LIST);
      expect(noBannerProblems((await getAs(w, LIST)).text)).toEqual([]);
    }
  });

  it("CS28: one case made is one POST and a 303; following and reloading send nothing again, and the banner is said once, by that case alone", async () => {
    const w = await world();
    const { res } = await submit(w, { type: { [SAID.caseName]: "Once" } });
    expect(res.status).toBe(303);
    const to = res.headers["location"] as string;
    // Another case's page, and the list, first: neither says it, and neither takes it from the made case.
    expect(noBannerProblems((await getAs(w, pageOf("c-harbour"))).text)).toEqual([]);
    expect(noBannerProblems((await getAs(w, LIST)).text)).toEqual([]);
    const first = await getAs(w, to);
    expect(bannerProblems(first.text, studioOf("c-made-1"))).toEqual([]);
    const reload = await getAs(w, to);
    expect(reload.status).toBe(200);
    expect(noBannerProblems(reload.text)).toEqual([]);
    expect(onePostProblems(calls(w.conduit))).toEqual([]);
    // No address makes a page say a case was made.
    const fresh = await world();
    for (const path of [pageOf("c-harbour"), `${pageOf("c-harbour")}&made=1`, `${pageOf("c-harbour")}&made=c-harbour`, `${pageOf("c-harbour")}&banner=made`, `${LIST}?made=c-harbour`]) {
      expect(noBannerProblems((await getAs(fresh, path)).text), path).toEqual([]);
    }
    // Nor does another person's session say what this one made.
    const second = await submit(w, { type: { [SAID.caseName]: "Twice" } });
    const other = await signedIn(w.app);
    const theirs = await request(w.app).get(second.res.headers["location"] as string).set("Cookie", other.cookie);
    expect(noBannerProblems(theirs.text)).toEqual([]);
  });

  it("CS29: the form's controls are native and labelled, in the page's order, the two radio groups and the boxes each a group with a legend", async () => {
    const w = await world();
    const page = await getAs(w, FORM);
    expect(stopProblems(page.text)).toEqual([]);
    expect(h1sOf(page.text)).toEqual([SAID.newCase]);
    expect(page.text).toMatch(/<title>New case · OspreyFlow<\/title>/);
    const radios = (formOf(page.text)?.controls ?? []).filter((c) => c.type === "radio");
    expect(radios.filter((r) => r.checked).map((r) => r.label)).toEqual([SAID.makeNew]);
    for (const c of (formOf(page.text)?.controls ?? []).filter((x) => x.type === "text")) expect(attr(c.tag, "maxlength"), c.label).toBe("200");
    // *New case* on the list is a link, drawn as a button, and one stop.
    const list = await getAs(w, LIST);
    expect(mainOf(list.text)).toMatch(/<a class="btn btn--primary" href="\/cases\?new=1">New case<\/a>/);
  });

  it("CS30: with scripts off the form is whole, nothing waits to be shown, and it posts a case", async () => {
    const w = await world();
    const page = await getAs(w, FORM);
    expect(scriptsOffProblems(page.text)).toEqual([]);
    expect(page.text).toMatch(/<script type="application\/json" id="page-data"[^>]*>\{"page":"cases"\}<\/script>/);
    const refused = await submit(w, { type: { [SAID.datasetName]: "Quay ledger" } });
    expect(scriptsOffProblems(refused.res.text)).toEqual([]);
    const { res } = await submit(w, { type: { [SAID.caseName]: "No script" } });
    expect(res.status).toBe(303);
  });

  it("CS31: no dataset's id is on the page outside a form value, drawn first or again; each is named by its name alone, a composite saying how many it joins", async () => {
    const w = await world();
    const page = await getAs(w, FORM);
    const datasets = (formOf(page.text)?.controls ?? []).filter((c) => c.name === "dataset_id");
    expect(datasets.map((c) => c.label)).toEqual(OFFERED_LABELS);
    expect(datasets.map((c) => c.value)).toEqual([GATE, LIVE, BOTH, QUAY]);
    expect(idProblems(page.text)).toEqual([]);
    const refused = await submit(w, { choose: ["Gate camera log"], type: { [SAID.datasetName]: "Quay ledger" } });
    expect(refused.res.status).toBe(422);
    expect(idProblems(refused.res.text)).toEqual([]);
    expect(mainText(page.text)).not.toContain("A board's drawing");
    expect(mainText(page.text)).not.toContain("Another unit's extract");
  });

  it("CS32: every field of Dataset changes the form or is named as left out; the page sends the create's fields; no other address or method answers", async () => {
    const base = { ...datasetOf(DATASETS[1] as UnitDataset) };
    const other: Record<string, unknown> = {
      id: "ds-changed",
      name: "A changed name",
      owning_unit: "a-changed-unit",
      created_at: "2025-01-03T04:05:00Z",
      created_by: "acct-changed",
      egress: "any",
      kind: "source",
      members: [QUAY, GATE, LIVE],
      layer_of: "c-changed",
      highest_marking: "A changed marking",
      promotion_policy: "second_person",
    };
    const drawn = async (row: Record<string, unknown>): Promise<string> => {
      const w = await world({ datasets_answer: { status: 200, body: [row] } });
      const res = await getAs(w, FORM);
      expect(res.status).toBe(200);
      return withoutNonce(mainOf(res.text)).replace(/name="_csrf" value="[^"]*"/, "");
    };
    const was = await drawn(base);
    expect(Object.keys(other).sort()).toEqual([...NEW_CASE_CENSUS.Dataset.drawn, ...NEW_CASE_CENSUS.Dataset.left].sort());
    expect([...NEW_CASE_CENSUS.Dataset.drawn].sort()).toEqual(["id", "kind", "members", "name"]);
    for (const [field, value] of Object.entries(other)) {
      const moved = (await drawn({ ...base, [field]: value })) !== was;
      expect(moved, field).toBe((NEW_CASE_CENSUS.Dataset.drawn as readonly string[]).includes(field));
    }
    // The page sends the create's fields, each of them in one branch or the other, and no other.
    const w = await world();
    await submit(w, { type: { [SAID.caseName]: "a" } });
    const one = posts(w.conduit)[0] ?? {};
    await submit(w, { choose: [SAID.useExisting, "Gate camera log"] });
    expect([...new Set([...Object.keys(one), ...Object.keys(posts(w.conduit)[0] ?? {})])].sort()).toEqual([...CREATE_FIELDS].sort());
    // Any other address, and a post that names neither radio, is a page that is not there, and nothing is asked.
    const unknown = await getAs(w, NOWHERE);
    const same = (res: { status: number; text: string }, label: string): void => {
      expect(res.status, label).toBe(404);
      expect(withoutNonce(res.text), label).toBe(withoutNonce(unknown.text));
    };
    const before = size(w.conduit);
    for (const path of ["/cases?new=", "/cases?new=2", "/cases?new=true", "/cases?new=1&new=1", "/cases?new=1&case=c-harbour", "/cases?new=1&case=", "/cases?new=2&case=c-harbour"]) {
      w.conduit.calls.splice(0);
      same(await getAs(w, path), `GET ${path}`);
      same(await postAs(w, path, [["name", "x"], ["data", "new"]]), `POST ${path}`);
      expect(calls(w.conduit), path).toEqual([]);
    }
    for (const path of [LIST, pageOf("c-harbour")]) {
      w.conduit.calls.splice(0);
      same(await postAs(w, path, [["name", "x"], ["data", "new"]]), `POST ${path}`);
      expect(calls(w.conduit), path).toEqual([]);
    }
    for (const pairs of [[["name", "x"]], [["name", "x"], ["data", "both"]], [["data", "new"], ["data", "existing"]]] as [string, string][][]) {
      w.conduit.calls.splice(0);
      same(await postAs(w, FORM, pairs), JSON.stringify(pairs));
      expect(calls(w.conduit)).toEqual([]);
    }
    for (const method of ["put", "patch", "delete"] as const) {
      const res = await request(w.app)[method](FORM).set("Cookie", w.cookie).set("X-CSRF-Token", w.csrf);
      expect(res.status, method).toBe(404);
    }
    expect(calls(w.conduit)).toEqual([]);
    expect(madeNothingProblems(w.conduit, before)).toEqual([]);
    // A request with no sign-in is sent to sign-in.
    const unsigned = await request(w.app).get(FORM);
    expect([unsigned.status, unsigned.headers["location"]]).toEqual([302, "/session/sign-in"]);
    // The Default tree has no cases page: neither the form nor the post.
    const old = await world({ tree: "default" });
    const nothing = await getAs(old, NOWHERE);
    for (const res of [await getAs(old, FORM), await postAs(old, FORM, [["data", "new"]])]) {
      expect(res.status).toBe(404);
      expect(withoutNonce(res.text)).toBe(withoutNonce(nothing.text));
    }
    expect(calls(old.conduit)).toEqual([]);
    expect(PAGES.find((p) => p.path === LIST)?.methods).toEqual(["GET", "POST"]);
    // The words are British, the shared package's are not written again, and nothing in the page's code chooses what is drawn.
    for (const s of sources()) {
      expect(withoutComments(s.text).match(AMERICAN), s.name).toBeNull();
      for (const sentence of [POLE_LABEL, ...DOMAIN_PACKS.map((p) => p.label), "Untitled case", "a composite of"]) expect(s.text.includes(sentence), `${s.name} writes again ${sentence}`).toBe(false);
      expect(withoutComments(s.text).replace(".filter((field) => !NOT_SENT.includes(field))", ""), s.name).not.toMatch(/\.(?:filter|slice|splice|sort|toSorted|reverse|toReversed|shift|pop)\s*\(|\|\s*(?:sort|reverse|first|last|batch|slice|reject|select|selectattr|rejectattr)\b/);
    }
  });

  describe("CS33: each check is red against the real page or call with one thing changed", () => {
    it("CS33: the call's check, for each thing the fixture or the route would take differently", async () => {
      const w = await world();
      await submit(w, { type: { [SAID.caseName]: "Harbour thefts", [SAID.datasetName]: "Harbour 2026" } });
      const real = posts(w.conduit)[0] as Record<string, unknown>;
      const want = { name: "Harbour thefts", new_dataset_name: "Harbour 2026", domains: [] };
      expect(bodyProblems([real], want)).toEqual([]);
      const { domains: _dropped, ...neverChosen } = real;
      for (const planted of [{ ...real, dataset_ids: [QUAY] }, neverChosen, { ...real, new_dataset_name: "" }, { ...real, name: " Harbour thefts " }, { ...real, domains: [DOMAIN_PACKS[0]?.label] }]) {
        expect(bodyProblems([planted], want), JSON.stringify(planted)).not.toEqual([]);
      }
      expect(bodyProblems([real, real], want)).not.toEqual([]);
      expect(onePostProblems(["POST /v1/investigations"])).toEqual([]);
      expect(onePostProblems(["POST /v1/investigations", "GET /v1/investigations", "POST /v1/investigations"])).not.toEqual([]);
      expect(onePostProblems(["GET /v1/investigations"])).not.toEqual([]);
    });

    it("CS33: the refused form's checks, for a sentence against the other thing, words lost, no summary, a case made", async () => {
      const w = await world();
      const before = size(w.conduit);
      const taken = await submit(w, { type: { [SAID.caseName]: "Harbour thefts", [SAID.datasetName]: "Quay ledger" } });
      const real = taken.res.text;
      expect(errorProblems(real, SAID.nameRefused, "name")).toEqual([]);
      expect(errorProblems(real, SAID.nameRefused, "choice")).not.toEqual([]);
      expect(errorProblems(real.split(SAID.nameRefused).join(SAID.datasetRefused), SAID.nameRefused, "name")).not.toEqual([]);
      expect(errorProblems(real.replace('class="govuk-error-summary"', 'class="summary"'), SAID.nameRefused, "name")).not.toEqual([]);
      expect(errorProblems(real.replace(/aria-describedby="[^"]*"/g, ""), SAID.nameRefused, "name")).not.toEqual([]);
      expect(errorProblems(real.replace("<title>Error: ", "<title>"), SAID.nameRefused, "name")).not.toEqual([]);
      expect(keptProblems(real, taken.pairs)).toEqual([]);
      expect(keptProblems(real.replace('value="Harbour thefts"', 'value=""'), taken.pairs)).not.toEqual([]);
      const chosen = await submit(w, { choose: [SAID.useExisting] });
      expect(errorProblems(chosen.res.text, SAID.datasetRefused, "choice")).toEqual([]);
      // The branch ignored: an existing dataset's refusal said as a name taken.
      expect(errorProblems(chosen.res.text.split(SAID.datasetRefused).join(SAID.nameRefused), SAID.datasetRefused, "choice")).not.toEqual([]);
      expect(errorProblems(chosen.res.text, SAID.datasetRefused, "name")).not.toEqual([]);
      expect(madeNothingProblems(w.conduit, before)).toEqual([]);
      // A case made before its dataset was refused.
      w.conduit.cases.push({ ...(CASES[0] as Case), id: "c-made-first" });
      expect(madeNothingProblems(w.conduit, before)).not.toEqual([]);
    });

    it("CS33: the page's checks, for a banner, a button, an empty group, an id, a failure said as success, a stop, a script", async () => {
      const w = await world();
      const form = (await getAs(w, FORM)).text;
      const list = (await getAs(w, LIST)).text;
      const { res } = await submit(w, { type: { [SAID.caseName]: "Planted" } });
      const made = (await getAs(w, res.headers["location"] as string)).text;
      expect(bannerProblems(made, studioOf("c-made-1"))).toEqual([]);
      expect(bannerProblems(made, undefined)).not.toEqual([]);
      expect(bannerProblems(made.replace(SAID.made, "Case made"), studioOf("c-made-1"))).not.toEqual([]);
      expect(noBannerProblems(made)).not.toEqual([]);
      expect(offeredProblems(list, true)).toEqual([]);
      expect(offeredProblems(list, false)).not.toEqual([]);
      expect(offeredProblems(list.replace(`href="${FORM}"`, 'href="/cases/new"'), true)).not.toEqual([]);
      const bare = (await getAs(await world({ datasets: [] }), FORM)).text;
      expect(noDatasetProblems(bare)).toEqual([]);
      // Into the New case form, before its button: the page's first `</form>` is the sign-out's, in the header, which the check never reads.
      const emptyGroup = bare.replace('<button type="submit" class="btn btn--primary">', `<fieldset><legend>Datasets</legend></fieldset><button type="submit" class="btn btn--primary">`);
      expect(noDatasetProblems(emptyGroup)).toEqual(["a group has nothing in it"]);
      expect(noDatasetProblems(form)).not.toEqual([]);
      expect(idProblems(form)).toEqual([]);
      expect(idProblems(form.replace(">Quay ledger<", `>Quay ledger (${QUAY})<`))).not.toEqual([]);
      expect(idProblems(form.replace('id="dataset-1"', `id="dataset-${GATE}"`))).not.toEqual([]);
      const lost = await postAs(await world({ create_answer: { status: 500, body: {} } }), FORM, [["data", "new"]]);
      expect(notMadeProblems(lost)).toEqual([]);
      expect(notMadeProblems({ status: lost.status, text: lost.text.replace("</main>", `<div class="govuk-notification-banner"><div class="govuk-notification-banner__content">${SAID.made}</div></div></main>`) })).not.toEqual([]);
      expect(notMadeProblems({ status: 200, text: made })).not.toEqual([]);
      expect(formUnreadableProblems({ status: 200, text: bare })).not.toEqual([]);
      expect(stopProblems(form)).toEqual([]);
      expect(stopProblems(form.replace('type="radio"', 'tabindex="-1" type="radio"'))).not.toEqual([]);
      expect(stopProblems(form.replace('<label class="govuk-label" for="case-name">', "<label>"))).not.toEqual([]);
      expect(scriptsOffProblems(form)).toEqual([]);
      expect(scriptsOffProblems(form.replace("</main>", '<script src="/x.js"></script></main>'))).not.toEqual([]);
      expect(scriptsOffProblems(form.replace('class="govuk-radios__conditional"', 'class="govuk-radios__conditional govuk-radios__conditional--hidden"'))).not.toEqual([]);
      expect(scriptsOffProblems(form.replace("<fieldset", "<fieldset hidden"))).not.toEqual([]);
    });

    it("CS33: the fixture Conduit refuses a new case as the route does, in its order, and makes the dataset before the case", async () => {
      const w = await world();
      const poor = await world({ rights: ["investigate"] });
      const ask = async (at: World, body: unknown, bearerToken: string | null = at.reader.token): Promise<{ status: number; body: unknown }> => {
        const res = await fetch(`${at.conduit.url}/v1/investigations`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(bearerToken === null ? {} : { Authorization: `Bearer ${bearerToken}` }) },
          body: JSON.stringify(body),
        });
        return { status: res.status, body: await res.json() };
      };
      expect((await ask(w, {}, null)).status).toBe(401);
      // The right first, whatever is wrong with the body.
      expect(await ask(poor, { domains: ["pole"] })).toEqual({ status: 403, body: rightRefusal("create_case") });
      expect(await ask(poor, {})).toEqual({ status: 403, body: rightRefusal("create_case") });
      // Then the body, before any dataset rule.
      for (const body of [{ domains: ["pole"] }, { domains: [DOMAIN_PACKS[0]?.label], dataset_ids: [ELSEWHERE] }, { new_dataset_name: "x".repeat(201) }, { name: 7 }]) {
        const answered = await ask(w, body);
        expect(answered.status, JSON.stringify(body)).toBe(422);
        expect(Array.isArray((answered.body as { detail: unknown }).detail), JSON.stringify(body)).toBe(true);
      }
      // Then the three dataset rules, one answer.
      const before = size(w.conduit);
      for (const body of [{}, { name: "x" }, { new_dataset_name: "  " }, { dataset_ids: [] }, { dataset_ids: [QUAY], new_dataset_name: "Both" }, { dataset_ids: [QUAY, GATE] }, { dataset_ids: [ELSEWHERE] }, { dataset_ids: [DRAWN] }, { new_dataset_name: "QUAY  ledger" }, { new_dataset_name: "A board's drawing" }]) {
        expect(await ask(w, body), JSON.stringify(body)).toEqual({ status: 422, body: DATASET_REFUSED });
      }
      expect(madeNothingProblems(w.conduit, before)).toEqual([]);
      // A name another unit has is free.
      expect((await ask(w, { new_dataset_name: "Another unit's extract" })).status).toBe(201);
      const made = await ask(w, { dataset_ids: [LIVE], domains: ["fibo"] });
      expect(made.status).toBe(201);
      expect(made.body).toMatchObject({ name: "Untitled case", domains: ["stix"], owning_unit: UNIT });
      const listed = (await (await fetch(`${w.conduit.url}/v1/investigations`, { headers: { Authorization: `Bearer ${w.reader.token}` } })).json()) as { id: string; level: string }[];
      expect(listed[0]).toMatchObject({ level: "author" });
      // The rights and the datasets, as their routes send them.
      const get = async (path: string, at: World): Promise<unknown> => (await fetch(`${at.conduit.url}${path}`, { headers: { Authorization: `Bearer ${at.reader.token}` } })).json();
      expect(await get("/v1/me/rights", w)).toEqual({ rights: CREATOR });
      const offered = (await get("/v1/datasets", poor)) as { id: string }[];
      expect(offered.map((d) => d.id)).toEqual([GATE, LIVE, BOTH, QUAY]);
      expect(await get("/v1/datasets", await world({ rights: [] }))).toEqual([]);
    });
  });
});
