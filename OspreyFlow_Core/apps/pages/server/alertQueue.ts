/**
 * The alert queue as a read-only page of the GOV.UK tree (slice RM1a; ADR-152 decisions 1, 4, 5, 6, 7 and 12; FUNCTIONS row
 * `alerts-rules-watches`; scenario AQ of `spec/08_ACCEPTANCE_SCENARIOS.md`):
 *
 *   GET  /alert-queue?case=<case>   the case's alert queue, one row for each alert the Conduit sends
 *   GET  /alert-queue               the cases the person holds, each a link to its queue
 *
 * One case at a time, because the Conduit's queue is the case's (`GET /v1/investigations/{id}/alert-queue`): there is no queue across
 * cases to read. The path is not `/alerts`, which is an alert's own address (`/alerts/<id>`, ADR-146 decision 6) and, under the front
 * proxy's rule of a path and everything under it, would carry that address here.
 *
 * **Access control is the Conduit's, and this page adds none and takes none away** (rules 3, 4 and 7). Every read is made as the person
 * (`conduit.ts`: their bearer and nothing the browser sent), and the Conduit leaves out an alert any of whose evidence the reader may not
 * see and does not count it. So this page:
 *  - draws every row it was sent, in the order sent, and filters, counts, sorts and cuts none (`views/alertQueueWords.ts` reads a row;
 *    a bare slice near a limit is a defect, rule 2);
 *  - states no count of its own, and names no alert it was not sent: there is nothing here that could tell a reader one was left out;
 *  - draws five things of an alert and never what it rests on (its entities, citations, evidence or ids);
 *  - answers every refusal (a right not held, the rows not offered, a case not held or not there, a level not enough, a token not
 *    known) as a path nothing serves, in the same words and with the same status, and never shows the Conduit's own words;
 *  - says a queue it could not read, in words, with no table: a failed read is never an empty queue.
 * It writes nothing, takes GET alone, and has no control but links.
 *
 * It is the GOV.UK tree's alone for now: a GOV.UK page may exist before its Default twin (the owner, 24 November 2026).
 */
import type { Request, Response } from "express";

import { SessionEnded } from "./accessToken.js";
import { ConduitUnreachable, conduitFor, v1 } from "./conduit.js";
import type { Conduit } from "./conduit.js";
import type { ForwardSettings } from "./config.js";
import type { PageModule } from "./pages.js";
import { ALERT_QUEUE_WORDS, QUEUE_PATH, caseLinks, caseList, nameOfCase, queueRows } from "./views/alertQueueWords.js";
import type { CaseLink, QueueRow } from "./views/alertQueueWords.js";

/** What the app keeps for the pages that call the Conduit (`app.ts`: the Conduit's address and the log), settings and never a request's own. */
interface Settings {
  forward: ForwardSettings | undefined;
  log: (message: string) => void;
}

/** What the template draws, and the status it is sent with. */
type View =
  | { kind: "table"; caption: string; caseName: string; rows: QueueRow[] }
  | { kind: "cases"; cases: CaseLink[] }
  | { kind: "empty" | "unreadable" | "message"; message: string };

const MAX_CASE_ID_CHARS = 200;

/** The status of a read, and its body when it was 200 and JSON: 0 for a Conduit that could not be reached. */
async function readAs(conduit: Conduit, path: string): Promise<{ status: number; json: unknown }> {
  try {
    const reply = await conduit({ path });
    return { status: reply.status, json: reply.status === 200 ? reply.json : undefined };
  } catch (error) {
    if (error instanceof ConduitUnreachable) return { status: 0, json: undefined };
    throw error;
  }
}

/** A refusal of any kind: the words and the status of a path nothing serves (`app.ts`), the page the same for every reason. */
function notFound(res: Response): void {
  res.status(404).render("error", ALERT_QUEUE_WORDS.notFound);
}

function draw(res: Response, status: number, view: View): void {
  res.status(status).render("alert-queue", { title: ALERT_QUEUE_WORDS.title, page: "alert-queue", words: ALERT_QUEUE_WORDS, q: view });
}

async function alertQueueGet(req: Request, res: Response): Promise<void> {
  const settings = req.app.locals["studio"] as Settings;
  const auth = req.session.auth;
  if (!auth || !settings.forward) {
    res.status(503).render("error", ALERT_QUEUE_WORDS.unavailable);
    return;
  }
  const asked: unknown = req.query["case"];
  const caseId = asked === undefined || asked === "" ? null : asked;
  if (caseId !== null && (typeof caseId !== "string" || caseId.length > MAX_CASE_ID_CHARS)) {
    notFound(res);
    return;
  }
  let conduit: Conduit;
  try {
    conduit = await conduitFor(settings.forward, auth, settings.log);
  } catch (error) {
    // The provider would not renew the token and the session is ended: the app answers with the sign-in redirect (`app.ts`).
    if (error instanceof SessionEnded) throw error;
    settings.log("pages: alert queue: the person's access could not be prepared (502)");
    res.status(502).render("error", ALERT_QUEUE_WORDS.unavailable);
    return;
  }
  if (caseId === null) {
    // No queue is read: only the cases the Conduit says the person holds, as links.
    const reply = await readAs(conduit, v1("investigations"));
    const cases = reply.status === 200 ? caseList(reply.json) : undefined;
    if (cases === undefined) draw(res, 502, { kind: "message", message: ALERT_QUEUE_WORDS.casesUnreadable });
    else if (cases.length === 0) draw(res, 200, { kind: "message", message: ALERT_QUEUE_WORDS.noCases });
    else draw(res, 200, { kind: "cases", cases: caseLinks(cases) });
    return;
  }
  // The queue and the case's name, as the person, at once: the name is for the caption and the Case column and decides nothing.
  const [queue, cases] = await Promise.all([readAs(conduit, v1("investigations", caseId, "alert-queue")), readAs(conduit, v1("investigations"))]);
  if (queue.status >= 400 && queue.status < 500) {
    notFound(res);
    return;
  }
  const rows = queue.status === 200 ? queueRows(queue.json) : undefined;
  if (rows === undefined) {
    draw(res, 502, { kind: "unreadable", message: ALERT_QUEUE_WORDS.unreadable });
    return;
  }
  if (rows.length === 0) {
    draw(res, 200, { kind: "empty", message: ALERT_QUEUE_WORDS.empty });
    return;
  }
  const name = nameOfCase(cases.status === 200 ? caseList(cases.json) : undefined, caseId);
  draw(res, 200, {
    kind: "table",
    caption: `${ALERT_QUEUE_WORDS.captionFor} ${name ?? ALERT_QUEUE_WORDS.thisCaseLower}`,
    caseName: name ?? ALERT_QUEUE_WORDS.thisCase,
    rows,
  });
}

export const alertQueue: PageModule = {
  id: "alerts-rules-watches",
  path: QUEUE_PATH,
  methods: ["GET"],
  trees: ["govuk"],
  handler: alertQueueGet,
};
