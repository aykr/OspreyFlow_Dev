/**
 * A case's drawing boards, one board's drawn items and links as tables, and making, sharing and deleting a board, a page of the GOV.UK
 * tree (slices GG4a and GG4c; ADR-143 decisions 3 to 5; ADR-152 decisions 1, 4, 5, 6, 7 and 12; FUNCTIONS row `drawing-boards`;
 * scenario BD):
 *
 *   GET  /cases/boards?case=<id>                              the case's boards the reader may see
 *                                                             (`GET /v1/investigations/{id}/boards`) as a table, then the person's
 *                                                             rights (`GET /v1/me/rights`): "New drawing board" when they hold
 *                                                             `draw_on_boards` and `investigate`
 *   GET  /cases/boards?case=<id>&board=<id>                   one board (`GET /v1/investigations/{id}/boards/{board_id}`) as three
 *                                                             tables; share and delete when it says `may_draw`
 *   GET  /cases/boards?case=<id>&board=<id>&delete=confirm    the page that asks before a delete (the same one read; `may_draw` alone)
 *   POST /cases/boards?case=<id>             action=make      a blank board (`POST .../boards` with its name and `start: "blank"`)
 *   POST /cases/boards?case=<id>&board=<id>  action=share     `POST .../boards/{board_id}/share`
 *   POST /cases/boards?case=<id>&board=<id>  action=delete    `DELETE .../boards/{board_id}`
 *
 * One page with the case and the board in its query, under the cases page and in the query form it uses, not
 * `/cases/{case_id}/boards/{board_id}`: a page's path is a plain path and one page is one row in a tree (`pages.ts`, decision 6).
 *
 * It reads and writes through the same door a script's call takes (`conduit.ts`), as the person, with their bearer and nothing of the
 * browser's. The Conduit authorises every call (rules 3 and 4): this page checks no level of its own, filters nothing after an answer
 * and counts nothing (decision 5). What it offers is words only: the route refuses all the same, and a refusal is said. One render of a
 * read reads each of its routes exactly once.
 *
 * **A write is post, then `303` to a `GET`** (the owner's question 6 (a); the first GOV.UK page to write this way), so a reload sends
 * nothing again. A write is a plain form with no script. The anti-forgery check (`csrf.ts`) runs before this handler, and the form is
 * never passed on: each write's call is built here, so the anti-forgery token never reaches the Conduit (`BoardInput` refuses a field
 * it does not have). One write is one call, which the route audits once: nothing is read back on the post. A delete's banner is held in
 * the session for the case's list to say once, never in the address, so no link can make the page say a board was deleted.
 *
 * What the page answers (the owner's rulings of 25 November 2026 on GG4a's draft and of 26 November on GG4c's):
 *  - a refusal of a read (any 4xx but a 401 and the cap's 409: someone else's private board, another case's, none at all, a case the
 *    reader holds no level on, another unit's, none, the right to investigate wanting): a 404 with the page of a path nothing serves,
 *    drawn from the same words and template, with none of the Conduit's words, never a sentence that a board is not shared;
 *  - a `case` or a `board` that is empty, repeated, a dot segment, holds a slash or is not a plain value, a `board` with no `case`, a
 *    `delete` other than `confirm` or with no board, the confirmation for a board the reader may not draw on, and a post that names no
 *    write of this page or the wrong address for one: the same 404, and nothing more is asked;
 *  - a board past the working-set cap (the route's 409 `limit_exceeded`, read strictly): a 409 page saying so, with the refusal's three
 *    options in words, and no part of the board (rule 2);
 *  - a 401: the Studio's words, to sign in again (a 401);
 *  - the Conduit failing, not answering, or answering what the page cannot draw from (the strict reader, `views/boardsWords.ts`): could
 *    not be read (a 502), with no table and no part of one (rule 2); of a write, the same page, which says nothing has changed;
 *  - a name empty or over 200 characters, or the route's 422 naming it: the GOV.UK error summary with the words kept (a 422);
 *  - a write's 403 for the right or the case level: "You cannot make boards in this case" (a 403); a write's 403
 *    `not_the_boards_creator` (the controls are the creator's alone, so a non-creator was never offered it) and its 404: the same 404.
 *
 * It is the GOV.UK tree's alone for now: a service started for the Default tree answers `/cases/boards` as a path nothing serves. GET
 * and POST are the only methods it answers, and it has no script. Its id is the `drawing-boards` row's, whose route stays empty until
 * the function is whole (drawing, the drawn watches and promotion are later slices').
 */
import type { Request, Response } from "express";

import { SessionEnded } from "./accessToken.js";
import { ConduitUnreachable, conduitFor, v1 } from "./conduit.js";
import type { Call, Conduit, Reply } from "./conduit.js";
import type { ForwardSettings } from "./config.js";
import type { PageModule } from "./pages.js";
import { BOARDS_WORDS, boardHref, boardView, boardsHref, limitView, listView, madeBoardId, mayMakeBoards, nameFits, refusesTheName } from "./views/boardsWords.js";
import { caseHref } from "./views/casesWords.js";
import { NOT_FOUND } from "./views/notFoundWords.js";
import { refusalWords } from "./views/studioWords.js";

declare module "express-session" {
  interface SessionData {
    /** The case a board was just deleted from: its list says so once, at its next view (slice GG4c). */
    boardDeleted?: string;
  }
}

interface Settings {
  forward: ForwardSettings | undefined;
  log: (message: string) => void;
}

function context(title: string, view: unknown, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { title, page: "boards", words: BOARDS_WORDS, view, ...extra };
}

async function ask(conduit: Conduit, call: Call): Promise<Reply | undefined> {
  try {
    return await conduit(call);
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

/** The answers a read and a write share, for one case's address. */
function answers(res: Response, title: string, caseId: string, oneBoard: boolean) {
  const back = { toCase: caseHref(caseId), toBoards: boardsHref(caseId) };
  return {
    back,
    unreadable: (status = 502): void => void res.status(status).render("boards", context(title, { kind: oneBoard ? "unreadable-board" : "unreadable-list", ...back })),
    ended: (): void => void res.status(401).render("boards", context(title, { kind: "ended" }, { ended: refusalWords(401, undefined, "") })),
  };
}

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
    settings.log("pages: boards: the person's access could not be prepared (502)");
    unreadable();
    return undefined;
  }
}

async function boardsGet(req: Request, res: Response): Promise<void> {
  const caseId = req.query["case"];
  const boardId = req.query["board"];
  const asked = req.query["delete"];
  const oneBoard = boardId !== undefined;
  if (!plain(caseId) || (oneBoard && !plain(boardId))) return notFound(res);
  if (asked !== undefined && (!oneBoard || asked !== "confirm")) return notFound(res);
  const { back, unreadable, ended } = answers(res, oneBoard ? BOARDS_WORDS.about : BOARDS_WORDS.listTitle, caseId, oneBoard);
  const conduit = await conduitAs(req, unreadable);
  if (conduit === undefined) return;

  if (!oneBoard) {
    const list = await ask(conduit, { path: v1("investigations", caseId, "boards") });
    if (list === undefined) return unreadable();
    if (list.status === 401) return ended();
    if (refused(list)) return notFound(res);
    const view = list.status === 200 ? listView(caseId, list.json) : undefined;
    if (view === undefined) return unreadable();
    // Asked once the list is the reader's to see. Rights that cannot be read offer nothing, and the page says so.
    const rights = await ask(conduit, { path: v1("me", "rights") });
    if (rights?.status === 401) return ended();
    const mayMake = rights?.status === 200 ? mayMakeBoards(rights.json) : undefined;
    // The delete's banner: said once, by the list of the case it was deleted from, and only when that list is drawn.
    const deleted = req.method === "GET" && req.session.boardDeleted === caseId;
    if (deleted) delete req.session.boardDeleted;
    const make = mayMake === true ? { action: boardsHref(caseId) } : undefined;
    res.render("boards", context(BOARDS_WORDS.listTitle, view, { make, rightsUnread: mayMake === undefined, deleted }));
    return;
  }

  const opened = await ask(conduit, { path: v1("investigations", caseId, "boards", boardId as string) });
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
  const view = opened.status === 200 ? boardView(caseId, boardId as string, opened.json) : undefined;
  if (view === undefined) return unreadable();
  if (asked === "confirm") {
    // A delete is offered to whoever may draw on the board, and its page to no one else.
    if (view.own === undefined) return notFound(res);
    res.render("boards", context(BOARDS_WORDS.confirmTitle, { kind: "confirm-delete", name: view.name, here: view.own.here }));
    return;
  }
  res.render("boards", context(view.name, { ...view, ...back }));
}

/** A field of the posted form, when it was sent once. */
function field(body: unknown, name: string): string | undefined {
  if (typeof body !== "object" || body === null) return undefined;
  const value = (body as Record<string, unknown>)[name];
  return typeof value === "string" ? value : undefined;
}

async function boardsPost(req: Request, res: Response): Promise<void> {
  const caseId = req.query["case"];
  const boardId = req.query["board"];
  const action = field(req.body, "action");
  if (!plain(caseId)) return notFound(res);
  // A new board is posted to the list's address; a share or a delete to the board's own. Anything else is no write of this page.
  const making = action === "make" && boardId === undefined;
  const onBoard = (action === "share" || action === "delete") && plain(boardId);
  if (!making && !onBoard) return notFound(res);
  const { back, unreadable, ended } = answers(res, making ? BOARDS_WORDS.listTitle : BOARDS_WORDS.about, caseId, !making);

  const name = field(req.body, "name") ?? "";
  const nameWrong = (): void => {
    const view = { kind: "name-error", kept: name, action: boardsHref(caseId), ...back };
    res.status(422).render("boards", context(`${BOARDS_WORDS.errorPrefix} ${BOARDS_WORDS.newTitle}`, view));
  };
  if (making && !nameFits(name)) return nameWrong();

  const conduit = await conduitAs(req, unreadable);
  if (conduit === undefined) return;
  // Each write's call is built here: of the form, only the name goes on.
  const call: Call = making
    ? { method: "POST", path: v1("investigations", caseId, "boards"), json: { name, start: "blank" } }
    : action === "share"
      ? { method: "POST", path: v1("investigations", caseId, "boards", boardId as string, "share") }
      : { method: "DELETE", path: v1("investigations", caseId, "boards", boardId as string) };
  const reply = await ask(conduit, call);
  if (reply === undefined) return unreadable();
  if (reply.status === 401) return ended();
  if (reply.status === 403) {
    // A non-creator was never offered the write: told what they are told of a board that is not there.
    if ((reply.json as Record<string, unknown> | null | undefined)?.["error"] === "not_the_boards_creator") return notFound(res);
    res.status(403).render("boards", context(BOARDS_WORDS.cannot, { kind: "cannot", ...back }));
    return;
  }
  if (reply.status === 404) return notFound(res);
  if (making) {
    if (reply.status === 422 && refusesTheName(reply.json)) return nameWrong();
    if (reply.status !== 201) return unreadable();
    // The board is made. One whose answer the page cannot read is found in the case's list, which shows what there is.
    const made = madeBoardId(caseId, reply.json);
    res.redirect(303, plain(made) ? boardHref(caseId, made) : boardsHref(caseId));
    return;
  }
  if (action === "share") {
    if (reply.status !== 200) return unreadable();
    res.redirect(303, boardHref(caseId, boardId as string));
    return;
  }
  if (reply.status !== 204) return unreadable();
  req.session.boardDeleted = caseId;
  res.redirect(303, boardsHref(caseId));
}

export const boardsPage: PageModule = {
  id: "drawing-boards",
  path: "/cases/boards",
  methods: ["GET", "POST"],
  trees: ["govuk"],
  handler: async (req, res) => {
    if (req.method === "POST") await boardsPost(req, res);
    else await boardsGet(req, res);
  },
};
