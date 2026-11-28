/**
 * The reader's cases, one case's page with its brief and its history, and New case, a page of the GOV.UK tree (slices GR1a, GR1e and
 * GR1b; ADR-152 decisions 1, 4, 5, 6, 7 and 12; ADR-099 Amendment 12 item 6; ADR-126; FUNCTIONS row `cases-and-views`, its first three
 * parts; scenario CS):
 *
 *   GET  /cases              the cases the reader holds a level on (`GET /v1/investigations`), as a table, then the person's rights
 *                            (`GET /v1/me/rights`): *New case* when they hold `create_case`
 *   GET  /cases?case=<id>    one case: `GET /v1/investigations/{id}`, then its brief, then its history, then the list (for the reader's
 *                            level and its datasets)
 *   GET  /cases?new=1        the New case form: the rights, then the unit's datasets (`GET /v1/datasets`)
 *   POST /cases?new=1        one `POST /v1/investigations`, then a `303` to the new case's page
 *
 * One page with the case in its query, not `/cases/{case_id}` (the owner's ruling of 26 November 2026: the query form, as GR4a's page
 * has), and New case a form on it, not a page of its own (his ruling on GR1b, until GR1c): a page's path is a plain path and one page is
 * one row in a tree (`pages.ts`, decision 6).
 *
 * It reads and writes through the same door a script's call takes (`conduit.ts`), as the person, with their bearer and nothing of the
 * browser's. The Conduit authorises every call (rules 3 and 4): this page checks no level of its own, filters nothing after an answer
 * and counts nothing (decision 5). What it offers is words only: the route refuses all the same, and a refusal is said. One render of a
 * case's page reads the case and its history exactly once each, so the Conduit's audit of each read is one row. The history is a part of
 * the case's page (the owner's ruling of 26 November 2026 on GR1e's draft) until GR1c gives it a page of its own, and it restores
 * nothing: a restore changes the working set, which no GOV.UK page shows until GG2e.
 *
 * **A write is post, then `303` to a `GET`**, so a reload sends nothing again; it is a plain form with no script. The anti-forgery check
 * (`csrf.ts`) runs before this handler, and the form is never passed on: the create's call is built here, field by field
 * (`createCaseBody`), so the anti-forgery token never reaches the Conduit. One case made is one call, which the route audits once:
 * nothing is read back on the post. The made case's banner is held in the session for that case's page to say once, never in the
 * address, so no link can make a page say a case was made.
 *
 * What the page answers (the owner's rulings of 25 November 2026 on GR1a's draft and of 26 November on GR1b's):
 *  - the case's read, the brief's or the history's refused (any 4xx but a 401: no level, another unit and no such case are the route's
 *    one 404; the brief's 403 for want of the right to investigate is the same to the reader): a 404 with the page of a path nothing
 *    serves, drawn from the same words and template, with none of the Conduit's words; nothing more is asked after a refusal;
 *  - a `case` that is empty, repeated, a dot segment, holding a slash or not a plain value, a `new` other than `1` or with a `case`, a
 *    post to any address but the form's, and a post choosing neither new nor existing data: the same 404, and nothing is asked;
 *  - a 401 from any call: the Studio's words, to sign in again (a 401);
 *  - rights that cannot be read: the list offers nothing and says so; the form could not be read (a 502);
 *  - the form asked for by a person without `create_case`, and the create's 403: "You cannot make cases" (a 403);
 *  - the create's `422 dataset_refused`, which carries no detail: the form again (a 422), said by the branch the page sent, the person's
 *    words kept, with the GOV.UK error summary; the page never says which of the route's rules refused;
 *  - a create answered by anything else, or not at all: a 502 saying the case could not be made and nothing was made (the owner's
 *    ruling), with the way to the list. A `201` whose body cannot be read is a case made: the list shows what there is, with no banner;
 *  - the Conduit failing, not answering, or answering what the page cannot draw from (the strict reader, `views/casesWords.ts`), or a list
 *    that does not hold the case: could not be read (a 502), with no table, no brief, no history, no form and no part of one (rule 2).
 *
 * It is the GOV.UK tree's alone for now: a service started for the Default tree answers `/cases` as a path nothing serves. GET and
 * POST are the only methods it answers, and it has no script. Its id is the `cases-and-views` row's, whose route stays empty until the
 * function is whole (settings, access, saved views and the history's own page are later slices').
 */
import type { Request, Response } from "express";

import { SessionEnded } from "./accessToken.js";
import { ConduitUnreachable, conduitFor, v1 } from "./conduit.js";
import type { Call, Conduit, Reply } from "./conduit.js";
import type { ForwardSettings } from "./config.js";
import type { PageModule } from "./pages.js";
import {
  BLANK_FIELDS,
  CASES_WORDS,
  NEW_CASE_HREF,
  caseHref,
  caseView,
  createCaseBody,
  datasetsOf,
  isDatasetRefusal,
  listView,
  madeCaseId,
  mayMakeCases,
  newCaseFields,
  newCaseView,
} from "./views/casesWords.js";
import type { NewCaseFields } from "./views/casesWords.js";
import { NOT_FOUND } from "./views/notFoundWords.js";
import { refusalWords, workspaceStudioHref } from "./views/studioWords.js";

declare module "express-session" {
  interface SessionData {
    /** The case just made: its page says so once, at its next view (slice GR1b). */
    caseMade?: { id: string; newDataset: boolean };
  }
}

interface Settings {
  forward: ForwardSettings | undefined;
  log: (message: string) => void;
}

function context(title: string, view: unknown, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { title, page: "cases", words: CASES_WORDS, view, newCaseHref: NEW_CASE_HREF, ...extra };
}

async function ask(conduit: Conduit, call: Call): Promise<Reply | undefined> {
  try {
    return await conduit(call);
  } catch (error) {
    if (error instanceof ConduitUnreachable) return undefined;
    throw error;
  }
}

const refused = (reply: Reply): boolean => reply.status >= 400 && reply.status < 500 && reply.status !== 401;
const notFound = (res: Response): void => void res.status(404).render("error", { ...NOT_FOUND });
/** A case's id as a plain value, named once: not empty, no dot segment, no slash. */
const plain = (value: unknown): value is string => typeof value === "string" && value !== "" && value !== "." && value !== ".." && !value.includes("/");

const ended = (res: Response, title: string): void => void res.status(401).render("cases", context(title, { kind: "ended" }, { ended: refusalWords(401, undefined, "") }));
const cannot = (res: Response): void => void res.status(403).render("cases", context(CASES_WORDS.cannot, { kind: "cannot" }));

/** The Conduit, asked as the person; `undefined` when the page has already answered that it cannot ask it. */
async function conduitAs(req: Request, unreadable: (status?: number) => void): Promise<Conduit | undefined> {
  const settings = req.app.locals["studio"] as Settings;
  const auth = req.session.auth;
  if (!auth || !settings.forward) {
    unreadable(503);
    return undefined;
  }
  try {
    return await conduitFor(settings.forward, auth, settings.log);
  } catch (error) {
    if (error instanceof SessionEnded) throw error;
    settings.log("pages: cases: the person's access could not be prepared (502)");
    unreadable();
    return undefined;
  }
}

/**
 * The New case form drawn with these fields, after reading the unit's datasets: blank, or again after the route refused the dataset
 * (`refused`, a 422). Datasets that cannot be read draw no form (`unreadable`): never a form that offers none.
 */
async function drawForm(res: Response, conduit: Conduit, fields: NewCaseFields, refused: boolean, unreadable: () => void): Promise<void> {
  const title = refused ? `${CASES_WORDS.errorPrefix} ${CASES_WORDS.newCase}` : CASES_WORDS.newCase;
  const datasets = await ask(conduit, { path: v1("datasets") });
  if (datasets === undefined) return unreadable();
  if (datasets.status === 401) return ended(res, CASES_WORDS.newCase);
  const offered = datasets.status === 200 ? datasetsOf(datasets.json) : undefined;
  if (offered === undefined) return unreadable();
  res.status(refused ? 422 : 200).render("cases", context(title, newCaseView(offered, fields, refused)));
}

async function newCaseGet(req: Request, res: Response): Promise<void> {
  const unreadable = (status = 502): void => void res.status(status).render("cases", context(CASES_WORDS.newCase, { kind: "unreadable-form" }));
  const conduit = await conduitAs(req, unreadable);
  if (conduit === undefined) return;
  // The rights first: the form is offered to whoever may make a case, and the unit's datasets are asked only then.
  const rights = await ask(conduit, { path: v1("me", "rights") });
  if (rights === undefined) return unreadable();
  if (rights.status === 401) return ended(res, CASES_WORDS.newCase);
  const may = rights.status === 200 ? mayMakeCases(rights.json) : undefined;
  if (may === undefined) return unreadable();
  if (!may) return cannot(res);
  await drawForm(res, conduit, BLANK_FIELDS, false, () => unreadable());
}

async function casesPost(req: Request, res: Response): Promise<void> {
  // The page's one write, posted to the form's own address. Anything else is no write of this page.
  if (req.query["new"] !== "1" || req.query["case"] !== undefined) return notFound(res);
  const fields = newCaseFields(req.body);
  if (fields === undefined) return notFound(res);
  const notMade = (status = 502): void => void res.status(status).render("cases", context(CASES_WORDS.notMadeTitle, { kind: "not-made" }));
  const conduit = await conduitAs(req, notMade);
  if (conduit === undefined) return;
  // The route judges the post, the right first: of the form, only the create's own fields go on.
  const reply = await ask(conduit, { method: "POST", path: v1("investigations"), json: createCaseBody(fields) });
  if (reply === undefined) return notMade();
  if (reply.status === 401) return ended(res, CASES_WORDS.newCase);
  if (reply.status === 403) return cannot(res);
  if (reply.status === 422 && isDatasetRefusal(reply.json)) return drawForm(res, conduit, fields, true, () => notMade());
  if (reply.status !== 201) return notMade();
  // The case is made. One whose answer the page cannot read is found in the list, which shows what there is.
  const made = madeCaseId(reply.json);
  if (!plain(made)) {
    res.redirect(303, "/cases");
    return;
  }
  req.session.caseMade = { id: made, newDataset: fields.data === "new" };
  res.redirect(303, caseHref(made));
}

async function casesGet(req: Request, res: Response): Promise<void> {
  const asked = req.query["new"];
  const wanted = req.query["case"];
  // `new=1`, named once and alone, is the New case form; any other `new` is a page that is not there, and nothing is asked.
  if (asked !== undefined) return asked === "1" && wanted === undefined ? newCaseGet(req, res) : notFound(res);
  const oneCase = wanted !== undefined;
  // A case named once, as a plain value: anything else is a page that is not there, and nothing is asked.
  // `.`, `..` and a value holding a slash are refused too: `v1` encodes each segment, but a dot segment is one the address's own parser
  // folds away, and the Conduit's server decodes `%2F` before its router sees the path (`<id>%2Fbrief` is the brief's route there),
  // so either would ask another route than the case's.
  if (oneCase && !plain(wanted)) return notFound(res);
  const title = oneCase ? CASES_WORDS.about : CASES_WORDS.listTitle;
  const unreadable = (status = 502): void => void res.status(status).render("cases", context(title, { kind: oneCase ? "unreadable-case" : "unreadable-list" }));
  const conduit = await conduitAs(req, unreadable);
  if (conduit === undefined) return;

  if (!plain(wanted)) {
    const list = await ask(conduit, { path: v1("investigations") });
    if (list === undefined) return unreadable();
    if (list.status === 401) return ended(res, title);
    const view = list.status === 200 ? listView(list.json) : undefined;
    if (view === undefined) return unreadable();
    // Asked once the list is read. Rights that cannot be read offer nothing, and the page says so.
    const rights = await ask(conduit, { path: v1("me", "rights") });
    if (rights?.status === 401) return ended(res, title);
    const may = rights?.status === 200 ? mayMakeCases(rights.json) : undefined;
    res.render("cases", context(title, view, { offerNewCase: may === true, rightsUnread: may === undefined }));
    return;
  }

  // The case's own read first: the Conduit's gate decides before anything else is asked, and it is asked once.
  const investigation = await ask(conduit, { path: v1("investigations", wanted) });
  if (investigation === undefined) return unreadable();
  if (investigation.status === 401) return ended(res, title);
  if (refused(investigation)) return notFound(res);
  if (investigation.status !== 200) return unreadable();
  const brief = await ask(conduit, { path: v1("investigations", wanted, "brief") });
  if (brief === undefined) return unreadable();
  if (brief.status === 401) return ended(res, title);
  if (refused(brief)) return notFound(res);
  if (brief.status !== 200) return unreadable();
  const history = await ask(conduit, { path: v1("investigations", wanted, "history") });
  if (history === undefined) return unreadable();
  if (history.status === 401) return ended(res, title);
  if (refused(history)) return notFound(res);
  if (history.status !== 200) return unreadable();
  const list = await ask(conduit, { path: v1("investigations") });
  if (list === undefined) return unreadable();
  if (list.status === 401) return ended(res, title);
  const view = list.status === 200 ? caseView(wanted, investigation.json, brief.json, history.json, list.json) : undefined;
  if (view === undefined) return unreadable();
  // The made case's banner: said once, by that case's page, and only when the page is drawn.
  const held = req.method === "GET" && req.session.caseMade?.id === wanted ? req.session.caseMade : undefined;
  if (held !== undefined) delete req.session.caseMade;
  const made = held === undefined ? undefined : { studio: held.newDataset ? workspaceStudioHref(wanted) : undefined };
  res.render("cases", context(view.name, view, { made }));
}

export const casesPage: PageModule = {
  id: "cases-and-views",
  path: "/cases",
  methods: ["GET", "POST"],
  trees: ["govuk"],
  handler: async (req, res) => {
    if (req.method === "POST") await casesPost(req, res);
    else await casesGet(req, res);
  },
};
