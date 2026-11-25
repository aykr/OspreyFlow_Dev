/**
 * A case's drawing boards and one board's drawn items and links as tables, read-only, a page of the GOV.UK tree (slice GG4a; ADR-143
 * decisions 3 to 5; ADR-152 decisions 1, 4, 5, 6, 7 and 12; FUNCTIONS row `drawing-boards`, its first part; scenario BD):
 *
 *   GET  /cases/boards?case=<id>               the case's boards the reader may see (`GET /v1/investigations/{id}/boards`), as a table
 *   GET  /cases/boards?case=<id>&board=<id>    one board (`GET /v1/investigations/{id}/boards/{board_id}`), as three tables
 *
 * One page with the case and the board in its query, under the cases page and in the query form it uses, not
 * `/cases/{case_id}/boards/{board_id}`: a page's path is a plain path and one page is one row in a tree (`pages.ts`, decision 6).
 *
 * It reads through the same door a script's call takes (`conduit.ts`), as the person, with their bearer and nothing of the browser's.
 * The Conduit authorises every read (rules 3 and 4): this page checks no level or right of its own, filters nothing after the answer and
 * counts nothing (decision 5). One render reads its one route exactly once.
 *
 * What the page answers (the owner's rulings of 25 November 2026 on GG4a's draft):
 *  - a refusal of the read (any 4xx but a 401 and the cap's 409: someone else's private board, another case's, none at all, a case the
 *    reader holds no level on, another unit's, none, the right to investigate wanting): a 404 with the page of a path nothing serves, drawn
 *    from the same words and template, with none of the Conduit's words, never a sentence that a board is not shared;
 *  - a `case` or a `board` that is empty, repeated, a dot segment, holds a slash or is not a plain value, and a `board` with no `case`:
 *    the same 404, and nothing is asked;
 *  - a board past the working-set cap (the route's 409 `limit_exceeded`, read strictly): a 409 page saying so, with the refusal's three
 *    options in words, and no part of the board (rule 2);
 *  - a 401: the Studio's words, to sign in again (a 401);
 *  - the Conduit failing, not answering, or answering what the page cannot draw from (the strict reader, `views/boardsWords.ts`): could
 *    not be read (a 502), with no table and no part of one (rule 2).
 *
 * It is the GOV.UK tree's alone for now: a service started for the Default tree answers `/cases/boards` as a path nothing serves. GET is
 * the only method it answers, and it has no form, control or script. Its id is the `drawing-boards` row's, whose route stays empty until
 * the function is whole (drawing, the drawn watches and promotion are later slices').
 */
import type { Request, Response } from "express";

import { SessionEnded } from "./accessToken.js";
import { ConduitUnreachable, conduitFor, v1 } from "./conduit.js";
import type { Conduit, Reply } from "./conduit.js";
import type { ForwardSettings } from "./config.js";
import type { PageModule } from "./pages.js";
import { BOARDS_WORDS, boardView, boardsHref, limitView, listView } from "./views/boardsWords.js";
import { caseHref } from "./views/casesWords.js";
import { NOT_FOUND } from "./views/notFoundWords.js";
import { refusalWords } from "./views/studioWords.js";

interface Settings {
  forward: ForwardSettings | undefined;
  log: (message: string) => void;
}

function context(title: string, view: unknown, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { title, page: "boards", words: BOARDS_WORDS, view, ...extra };
}

async function ask(conduit: Conduit, path: string): Promise<Reply | undefined> {
  try {
    return await conduit({ path });
  } catch (error) {
    if (error instanceof ConduitUnreachable) return undefined;
    throw error;
  }
}

/** A value named once, as a plain value: anything else names nothing. `.` and `..` too: `v1` encodes each segment, but a dot segment is
 * one the address's own parser folds away, so it would ask another route than the board's. And a value holding a slash: `v1` sends it as
 * `%2F`, which the Conduit's server decodes before it routes, so `b-quay/matches` would ask the board's matches, a route the reader never
 * chose (the review of 25 November found it). */
const plain = (value: unknown): value is string => typeof value === "string" && value !== "" && value !== "." && value !== ".." && !value.includes("/");
const refused = (reply: Reply): boolean => reply.status >= 400 && reply.status < 500 && reply.status !== 401;
const notFound = (res: Response): void => void res.status(404).render("error", { ...NOT_FOUND });

async function boardsGet(req: Request, res: Response): Promise<void> {
  const caseId = req.query["case"];
  const boardId = req.query["board"];
  const oneBoard = boardId !== undefined;
  if (!plain(caseId) || (oneBoard && !plain(boardId))) return notFound(res);
  const title = oneBoard ? BOARDS_WORDS.about : BOARDS_WORDS.listTitle;
  const back = { toCase: caseHref(caseId), toBoards: boardsHref(caseId) };
  const unreadable = (status = 502): void => void res.status(status).render("boards", context(title, { kind: oneBoard ? "unreadable-board" : "unreadable-list", ...back }));
  const ended = (): void => void res.status(401).render("boards", context(title, { kind: "ended" }, { ended: refusalWords(401, undefined, "") }));

  const settings = req.app.locals["studio"] as Settings;
  const auth = req.session.auth;
  if (!auth || !settings.forward) return unreadable(503);
  let conduit: Conduit;
  try {
    conduit = await conduitFor(settings.forward, auth, settings.log);
  } catch (error) {
    if (error instanceof SessionEnded) throw error;
    settings.log("pages: boards: the person's access could not be prepared (502)");
    return unreadable();
  }

  if (!oneBoard) {
    const list = await ask(conduit, v1("investigations", caseId, "boards"));
    if (list === undefined) return unreadable();
    if (list.status === 401) return ended();
    if (refused(list)) return notFound(res);
    const view = list.status === 200 ? listView(caseId, list.json) : undefined;
    if (view === undefined) return unreadable();
    res.render("boards", context(title, view));
    return;
  }

  const opened = await ask(conduit, v1("investigations", caseId, "boards", boardId));
  if (opened === undefined) return unreadable();
  if (opened.status === 401) return ended();
  // The cap's typed refusal is a 409 with its own body: said with its three options, never a 404 and never a part of the board.
  if (opened.status === 409 && typeof opened.json === "object" && opened.json !== null && (opened.json as Record<string, unknown>)["error"] === "limit_exceeded") {
    const limit = limitView(opened.json);
    if (limit === undefined) return unreadable();
    res.status(409).render("boards", context(BOARDS_WORDS.tooLargeTitle, { ...limit, ...back }));
    return;
  }
  if (refused(opened)) return notFound(res);
  const view = opened.status === 200 ? boardView(caseId, boardId, opened.json) : undefined;
  if (view === undefined) return unreadable();
  res.render("boards", context(view.name, { ...view, ...back }));
}

export const boardsPage: PageModule = {
  id: "drawing-boards",
  path: "/cases/boards",
  methods: ["GET"],
  trees: ["govuk"],
  handler: boardsGet,
};
