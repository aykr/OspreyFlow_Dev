/**
 * The reader's cases and one case's page with its brief, read-only, a page of the GOV.UK tree (slice GR1a; ADR-152 decisions 1, 4, 5, 6,
 * 7 and 12; FUNCTIONS row `cases-and-views`, its first part; scenario CS):
 *
 *   GET  /cases              the cases the reader holds a level on (`GET /v1/investigations`), as a table
 *   GET  /cases?case=<id>    one case: `GET /v1/investigations/{id}`, then its brief, then the list (for the reader's level and its datasets)
 *
 * One page with the case in its query, not `/cases/{case_id}`: a page's path is a plain path and one page is one row in a tree
 * (`pages.ts`, decision 6), so the owner's ruled address is a question in the slice's report, as GR4a's was.
 *
 * It reads through the same door a script's call takes (`conduit.ts`), as the person, with their bearer and nothing of the browser's.
 * The Conduit authorises every read (rules 3 and 4): this page checks no level or right of its own, filters nothing after the answer and
 * counts nothing (decision 5). One render of a case's page reads the case exactly once, so the Conduit's audit of the read is one row.
 *
 * What the page answers (the owner's rulings of 25 November 2026 on GR1a's draft):
 *  - the case's read or the brief's refused (any 4xx but a 401: no level, another unit and no such case are the route's one 404; the
 *    brief's 403 for want of the right to investigate is the same to the reader): a 404 with the page of a path nothing serves, drawn
 *    from the same words and template, with none of the Conduit's words; nothing more is asked after a refusal;
 *  - a `case` that is empty, repeated, a dot segment or not a plain value: the same 404, and nothing is asked;
 *  - a 401 from any read: the Studio's words, to sign in again (a 401);
 *  - the Conduit failing, not answering, or answering what the page cannot draw from (the strict reader, `views/casesWords.ts`), or a list
 *    that does not hold the case: could not be read (a 502), with no table, no brief and no part of one (rule 2).
 *
 * It is the GOV.UK tree's alone for now: a service started for the Default tree answers `/cases` as a path nothing serves. GET is the only
 * method it answers, and it has no form, control or script. Its id is the `cases-and-views` row's, whose route stays empty until the
 * function is whole (new case, settings, access, saved views and history are later slices').
 */
import type { Request, Response } from "express";

import { SessionEnded } from "./accessToken.js";
import { ConduitUnreachable, conduitFor, v1 } from "./conduit.js";
import type { Conduit, Reply } from "./conduit.js";
import type { ForwardSettings } from "./config.js";
import type { PageModule } from "./pages.js";
import { CASES_WORDS, caseView, listView } from "./views/casesWords.js";
import { NOT_FOUND } from "./views/notFoundWords.js";
import { refusalWords } from "./views/studioWords.js";

interface Settings {
  forward: ForwardSettings | undefined;
  log: (message: string) => void;
}

function context(title: string, view: unknown, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { title, page: "cases", words: CASES_WORDS, view, ...extra };
}

async function ask(conduit: Conduit, path: string): Promise<Reply | undefined> {
  try {
    return await conduit({ path });
  } catch (error) {
    if (error instanceof ConduitUnreachable) return undefined;
    throw error;
  }
}

const refused = (reply: Reply): boolean => reply.status >= 400 && reply.status < 500 && reply.status !== 401;
const notFound = (res: Response): void => void res.status(404).render("error", { ...NOT_FOUND });

async function casesGet(req: Request, res: Response): Promise<void> {
  const wanted = req.query["case"];
  const oneCase = wanted !== undefined;
  // A case named once, as a plain value: anything else is a page that is not there, and nothing is asked.
  // `.` and `..` are refused too: `v1` encodes each segment, but a dot segment is one the address's own parser folds away, so it would
  // ask another route than the case's. A value holding a slash too: `v1` sends it as `%2F`, which the Conduit's server decodes before it
  // routes, so `c-harbour/brief` would ask another route (found by GG4a's review, 25 November 2026).
  if (oneCase && (typeof wanted !== "string" || wanted === "" || wanted === "." || wanted === ".." || wanted.includes("/"))) return notFound(res);
  const title = oneCase ? CASES_WORDS.about : CASES_WORDS.listTitle;
  const unreadable = (status = 502): void => void res.status(status).render("cases", context(title, { kind: oneCase ? "unreadable-case" : "unreadable-list" }));
  const ended = (): void => void res.status(401).render("cases", context(title, { kind: "ended" }, { ended: refusalWords(401, undefined, "") }));

  const settings = req.app.locals["studio"] as Settings;
  const auth = req.session.auth;
  if (!auth || !settings.forward) return unreadable(503);
  let conduit: Conduit;
  try {
    conduit = await conduitFor(settings.forward, auth, settings.log);
  } catch (error) {
    if (error instanceof SessionEnded) throw error;
    settings.log("pages: cases: the person's access could not be prepared (502)");
    return unreadable();
  }

  if (!oneCase) {
    const list = await ask(conduit, v1("investigations"));
    if (list === undefined) return unreadable();
    if (list.status === 401) return ended();
    const view = list.status === 200 ? listView(list.json) : undefined;
    if (view === undefined) return unreadable();
    res.render("cases", context(title, view));
    return;
  }

  // The case's own read first: the Conduit's gate decides before anything else is asked, and it is asked once.
  const investigation = await ask(conduit, v1("investigations", wanted));
  if (investigation === undefined) return unreadable();
  if (investigation.status === 401) return ended();
  if (refused(investigation)) return notFound(res);
  if (investigation.status !== 200) return unreadable();
  const brief = await ask(conduit, v1("investigations", wanted, "brief"));
  if (brief === undefined) return unreadable();
  if (brief.status === 401) return ended();
  if (refused(brief)) return notFound(res);
  if (brief.status !== 200) return unreadable();
  const list = await ask(conduit, v1("investigations"));
  if (list === undefined) return unreadable();
  if (list.status === 401) return ended();
  const view = list.status === 200 ? caseView(wanted, investigation.json, brief.json, list.json) : undefined;
  if (view === undefined) return unreadable();
  res.render("cases", context(view.name, view));
}

export const casesPage: PageModule = {
  id: "cases-and-views",
  path: "/cases",
  methods: ["GET"],
  trees: ["govuk"],
  handler: casesGet,
};
