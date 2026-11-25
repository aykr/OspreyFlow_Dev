/**
 * Trends shown together, a read-only page of the GOV.UK tree (slice GR4a; ADR-152 decisions 5, 6, 7, 10 and 12, invariant I21;
 * FUNCTIONS row `reports-figures`; scenario TS; the owner's rulings of 25 November 2026):
 *
 *   GET  /packs/trends?case={case id}&pack={pack id}   one pack's trend items, in the pack's stored order, each as its figures drawn
 *
 * The address is for now: the owner ruled `/packs/{pack_id}/trends`, but a page's path is a plain path (`pages.ts`) and the pack routes
 * need the case as well as the pack, so the two go in the query, as the dataset map's do, until he rules (GR4a's away report).
 *
 * Decision 10 says this page is "a pack of trend items shown together on one page" with no new Conduit route, so it reads the pack
 * through the same door a script's call takes (`conduit.ts`), as the person, with their bearer and nothing of the browser's, and shows
 * **the pack's own snapshots**, frozen when each was added: it never asks a trend route for live figures (the owner's ruling 2(a)).
 *
 * Who may see it (the owner's ruling 3(a): "whoever may read the pack now"): the Conduit decides, on every read (rules 3 and 4). The
 * working pack first, `GET /v1/investigations/{id}/packs/{pack_id}` (the right to record assessments); when that route refuses for the
 * right (its 403), the newest published version, `GET /v1/investigations/{id}/packs/{pack_id}/published` (the right to read reports).
 * This page adds no access rule of its own, checks no right, filters nothing after the answer and counts nothing (decision 5). What the
 * page answers:
 *  - any other refusal (a case the reader cannot see, a pack not in the case, a pack never published, a 403 from the second read): a 404
 *    with the page of a path nothing serves, drawn from the same words and template, with none of the Conduit's words and no right named
 *    (the owner's ruling of 24 November 2026, "a non-viewer gets 404, the same as a missing thing"); an address with no case or no pack
 *    is the same 404 and asks nothing;
 *  - the Conduit's 401 (the session has outlived the person's token): the Studio's words, to sign in again (a 401);
 *  - the Conduit failing, not answering, or answering what the strict reader cannot read (`views/packTrendsWords.ts`): the trends could
 *    not be read (a 502), with no chart, no table and no part of either (rule 2).
 *
 * It is the GOV.UK tree's alone: a GOV.UK page may exist before its Default twin (the owner, 24 November 2026). GET is the only method
 * it answers, and it has no form, control or script. Its id is the `reports-figures` row's, whose route stays empty until the function
 * is complete.
 */
import type { Request, Response } from "express";

import { SessionEnded } from "./accessToken.js";
import { ConduitUnreachable, conduitFor, v1 } from "./conduit.js";
import type { Conduit, Reply } from "./conduit.js";
import type { ForwardSettings } from "./config.js";
import type { PageModule } from "./pages.js";
import { NOT_FOUND } from "./views/notFoundWords.js";
import { PACK_TRENDS_WORDS, readDraft, readPublished } from "./views/packTrendsWords.js";
import type { PackTrendsView } from "./views/packTrendsWords.js";
import { refusalWords } from "./views/studioWords.js";

interface Settings {
  forward: ForwardSettings | undefined;
  log: (message: string) => void;
}

/** The longest identifier the page will ask about; a longer one is a path nothing serves. */
const MAX_ID_CHARS = 200;

/** One query value, given once: anything else (missing, repeated, empty, too long) is not an identifier. */
function identifier(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" && value.length <= MAX_ID_CHARS ? value : undefined;
}

function context(view: unknown, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { title: PACK_TRENDS_WORDS.title, page: "pack-trends", words: PACK_TRENDS_WORDS, view, ...extra };
}

const unreadable = (res: Response, status = 502): void => void res.status(status).render("pack-trends", context({ kind: "unreadable" }));
const notFound = (res: Response): void => void res.status(404).render("error", { ...NOT_FOUND });
const ended = (res: Response): void => void res.status(401).render("pack-trends", context({ kind: "ended" }, { ended: refusalWords(401, undefined, "") }));

/** One read, as the person: the reply, or `undefined` when the Conduit could not be reached. */
async function ask(conduit: Conduit, path: string): Promise<Reply | undefined> {
  try {
    return await conduit({ path });
  } catch (error) {
    if (error instanceof ConduitUnreachable) return undefined;
    throw error;
  }
}

/** What a read's answer is: a view, or how the page says it has none. */
type Outcome = { view: PackTrendsView } | { said: "unreadable" | "ended" | "not-found" } | { refusedForTheRight: true };

function outcomeOf(reply: Reply | undefined, read: (body: unknown) => PackTrendsView | undefined, mayFallThrough: boolean): Outcome {
  if (reply === undefined || reply.status >= 500) return { said: "unreadable" };
  if (reply.status === 401) return { said: "ended" };
  if (mayFallThrough && reply.status === 403) return { refusedForTheRight: true };
  if (reply.status >= 400) return { said: "not-found" };
  if (reply.status !== 200) return { said: "unreadable" };
  const view = read(reply.json);
  return view === undefined ? { said: "unreadable" } : { view };
}

async function packTrendsGet(req: Request, res: Response): Promise<void> {
  const settings = req.app.locals["studio"] as Settings;
  const caseId = identifier(req.query["case"]);
  const packId = identifier(req.query["pack"]);
  if (caseId === undefined || packId === undefined) return notFound(res);
  const auth = req.session.auth;
  if (!auth || !settings.forward) return unreadable(res, 503);
  let conduit: Conduit;
  try {
    conduit = await conduitFor(settings.forward, auth, settings.log);
  } catch (error) {
    // The provider would not renew the token and the session is ended: the app answers with the sign-in redirect (`app.ts`).
    if (error instanceof SessionEnded) throw error;
    settings.log("pages: trends: the person's access could not be prepared (502)");
    return unreadable(res);
  }
  // The working pack first; its refusal for the right, and only that, sends the page to the newest published version.
  let outcome = outcomeOf(await ask(conduit, v1("investigations", caseId, "packs", packId)), readDraft, true);
  if ("refusedForTheRight" in outcome) {
    outcome = outcomeOf(await ask(conduit, v1("investigations", caseId, "packs", packId, "published")), readPublished, false);
  }
  if ("view" in outcome) return void res.render("pack-trends", context(outcome.view));
  if ("said" in outcome && outcome.said === "ended") return ended(res);
  if ("said" in outcome && outcome.said === "not-found") return notFound(res);
  return unreadable(res);
}

export const packTrends: PageModule = {
  id: "reports-figures",
  path: "/packs/trends",
  methods: ["GET"],
  trees: ["govuk"],
  handler: packTrendsGet,
};
