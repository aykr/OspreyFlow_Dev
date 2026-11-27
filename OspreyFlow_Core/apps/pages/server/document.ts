/**
 * One document of a case in the reader, read-only, a page of the GOV.UK tree (slice GG3b; ADR-152 decisions 1, 4, 5, 6, 7 and 12;
 * FUNCTIONS row `documents`, its first part; scenario DR):
 *
 *   GET  /cases/document?case=<case id>&document=<document id>    `GET /v1/investigations/{case}/documents/{document}/reader`, once
 *
 * One page with the case and the document in its query, GR1a's form (the owner's ruling 3 (a) of 26 November 2026, until GR1a's
 * question 1 on the address is ruled): a page's path is a plain path and one page is one row in a tree (`pages.ts`, decision 6).
 *
 * It reads through the same door a script's call takes (`conduit.ts`), as the person, with their bearer and nothing of the browser's.
 * The Conduit authorises the read (rules 3 and 4): this page checks no level or right of its own, filters nothing after the answer and
 * counts nothing (decision 5). One render reads the document exactly once, so the Conduit's audit of the read is one row; a picture's or
 * a film's address is the forwarder's path for the file, which the browser loads as its own read (audited `read_document_file`).
 *
 * What the page answers (the owner's rulings of 26 November 2026 on GG3b's draft, D268):
 *  - the read refused (a 404: a document the reader may not see, one in another case, one that does not exist, the case's gate; a
 *    403: the right to investigate): a 404 with the page of a path nothing serves, drawn from the same words and template, with none
 *    of the Conduit's words;
 *  - a `case` or a `document` missing, empty, repeated, a dot segment or not a plain value: the same 404, and nothing is asked;
 *  - a 401: the Studio's words, to sign in again (a 401);
 *  - any other 4xx (a 429, say), the Conduit failing, not answering, or answering what the page cannot draw from (the strict reader, `views/documentWords.ts`):
 *    could not be read (a 502), with no text, no mark, no table and no file (rule 2).
 *
 * It is the GOV.UK tree's alone for now: a service started for the Default tree answers `/cases/document` as a path nothing serves. GET
 * is the only method it answers, and it has no form, control or script. Its id is the `documents` row's, whose route stays empty until
 * the function is whole (a node's Messages and adding files are later slices').
 */
import type { Request, Response } from "express";

import { SessionEnded } from "./accessToken.js";
import { ConduitUnreachable, conduitFor, v1 } from "./conduit.js";
import type { Conduit, Reply } from "./conduit.js";
import type { ForwardSettings } from "./config.js";
import type { PageModule } from "./pages.js";
import { DOCUMENT_WORDS, caseHref, documentView } from "./views/documentWords.js";
import { NOT_FOUND } from "./views/notFoundWords.js";
import { refusalWords } from "./views/studioWords.js";

interface Settings {
  forward: ForwardSettings | undefined;
  log: (message: string) => void;
}

function context(title: string, view: unknown, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { title, page: "document", words: DOCUMENT_WORDS, view, ...extra };
}

async function ask(conduit: Conduit, path: string): Promise<Reply | undefined> {
  try {
    return await conduit({ path });
  } catch (error) {
    if (error instanceof ConduitUnreachable) return undefined;
    throw error;
  }
}

/** A value named once, as a plain value. `.` and `..` are refused too: `v1` encodes each segment, but a dot segment is one the
 * address's own parser folds away, so it would ask another route than the reader's. */
const plain = (value: unknown): value is string => typeof value === "string" && value !== "" && value !== "." && value !== "..";
/** The route's refusals: 404 for a document or a case the reader may not see or that is not there, 403 for want of the right. Any other
 * 4xx (a 429, a 413) is not a refusal of this reader and says nothing of the document: it is "could not be read", never "not found". */
const refused = (reply: Reply): boolean => reply.status === 403 || reply.status === 404;
const notFound = (res: Response): void => void res.status(404).render("error", { ...NOT_FOUND });

async function documentGet(req: Request, res: Response): Promise<void> {
  const caseId = req.query["case"];
  const documentId = req.query["document"];
  if (!plain(caseId) || !plain(documentId)) return notFound(res);
  const title = DOCUMENT_WORDS.about;
  const unreadable = (status = 502): void => void res.status(status).render("document", context(title, { kind: "unreadable", caseHref: caseHref(caseId) }));
  const ended = (): void => void res.status(401).render("document", context(title, { kind: "ended" }, { ended: refusalWords(401, undefined, "") }));

  const settings = req.app.locals["studio"] as Settings;
  const auth = req.session.auth;
  if (!auth || !settings.forward) return unreadable(503);
  let conduit: Conduit;
  try {
    conduit = await conduitFor(settings.forward, auth, settings.log);
  } catch (error) {
    if (error instanceof SessionEnded) throw error;
    settings.log("pages: document: the person's access could not be prepared (502)");
    return unreadable();
  }

  const reply = await ask(conduit, v1("investigations", caseId, "documents", documentId, "reader"));
  if (reply === undefined) return unreadable();
  if (reply.status === 401) return ended();
  if (refused(reply)) return notFound(res);
  const view = reply.status === 200 ? documentView(caseId, documentId, reply.json) : undefined;
  if (view === undefined) return unreadable();
  res.render("document", context(view.title, view));
}

export const documentPage: PageModule = {
  id: "documents",
  path: "/cases/document",
  methods: ["GET"],
  trees: ["govuk"],
  handler: documentGet,
};
