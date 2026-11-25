/**
 * The Admin People list, a read-only page of the GOV.UK tree (slice AD3a; ADR-152 decisions 1, 4, 5, 6, 7 and 12; FUNCTIONS row
 * `admin`, its first section; scenario AP):
 *
 *   GET  /admin/people   the people the Conduit lists, their roles in words and the state of each account
 *
 * It reads through the same door a script's call takes (`conduit.ts`): `GET /v1/admin/people`, then `GET /v1/admin/roles` for the
 * names of the roles, as the person, with their bearer and nothing of the browser's. The Conduit authorises each read behind the right
 * to manage people (rules 3 and 4); this page adds no access rule of its own, checks no right, filters nothing after the answer and
 * counts nothing (decision 5). It draws what the Conduit sent, whole and in the order sent (`views/adminPeopleWords.ts`).
 *
 * Who may see it, and what the page answers (the owner's ruling of 24 November 2026: "a non-viewer gets 404, the same as a missing
 * thing"):
 *  - the Conduit refuses (any 4xx but a 401: a person without the right is 403, and the others are the same): a 404 with the page of
 *    a path nothing serves, drawn from the same words and template, so that the page's existence is not told to a person who may not
 *    read it, and none of the Conduit's words, the right's name or a number is shown. The roles are not asked of a person refused;
 *  - the Conduit's 401 (the session has outlived the person's token): the Studio's words, to sign in again (a 401);
 *  - the Conduit failing, not answering, or answering what the page cannot draw from: the people could not be read (a 502), with no
 *    table and no part of one (rule 2).
 *
 * It is the GOV.UK tree's alone for now: a GOV.UK page may exist before its Default twin (the owner, 24 November 2026), so a service
 * started for the Default tree answers `/admin/people` as a path nothing serves. The page is read-only: GET is the only method it
 * answers, and it has no form, control or script. Its id is the `admin` row's, whose route stays empty until every section has its page.
 */
import type { Request, Response } from "express";

import { SessionEnded } from "./accessToken.js";
import { ConduitUnreachable, conduitFor, v1 } from "./conduit.js";
import type { Conduit, Reply } from "./conduit.js";
import type { ForwardSettings } from "./config.js";
import type { PageModule } from "./pages.js";
import { ADMIN_PEOPLE_WORDS, peopleView } from "./views/adminPeopleWords.js";
import { NOT_FOUND } from "./views/notFoundWords.js";
import { refusalWords } from "./views/studioWords.js";

interface Settings {
  forward: ForwardSettings | undefined;
  log: (message: string) => void;
}

/** What the page's own words are made of: the title and the words, and the view the template draws. */
function context(view: unknown, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { title: ADMIN_PEOPLE_WORDS.title, page: "admin-people", words: ADMIN_PEOPLE_WORDS, view, ...extra };
}

const unreadable = (res: Response, status = 502): void => void res.status(status).render("admin-people", context({ kind: "unreadable" }));

/** One read, as the person: the reply, or `undefined` when the Conduit could not be reached. */
async function ask(conduit: Conduit, path: string): Promise<Reply | undefined> {
  try {
    return await conduit({ path });
  } catch (error) {
    if (error instanceof ConduitUnreachable) return undefined;
    throw error;
  }
}

/** A refusal the Conduit made: a 4xx, whatever its words. A 401 is the session's, said apart. */
const refused = (reply: Reply): boolean => reply.status >= 400 && reply.status < 500 && reply.status !== 401;

async function adminPeopleGet(req: Request, res: Response): Promise<void> {
  const settings = req.app.locals["studio"] as Settings;
  const auth = req.session.auth;
  if (!auth || !settings.forward) {
    unreadable(res, 503);
    return;
  }
  let conduit: Conduit;
  try {
    conduit = await conduitFor(settings.forward, auth, settings.log);
  } catch (error) {
    // The provider would not renew the token and the session is ended: the app answers with the sign-in redirect (`app.ts`).
    if (error instanceof SessionEnded) throw error;
    settings.log("pages: admin: the person's access could not be prepared (502)");
    unreadable(res);
    return;
  }
  // The people first: the Conduit's refusal decides before anything else is asked.
  const people = await ask(conduit, v1("admin", "people"));
  if (people === undefined) return unreadable(res);
  if (people.status === 401) {
    res.status(401).render("admin-people", context({ kind: "ended" }, { ended: refusalWords(401, undefined, "") }));
    return;
  }
  if (refused(people)) {
    res.status(404).render("error", { ...NOT_FOUND });
    return;
  }
  if (people.status !== 200) return unreadable(res);
  const roles = await ask(conduit, v1("admin", "roles"));
  if (roles === undefined) return unreadable(res);
  if (roles.status === 401) {
    res.status(401).render("admin-people", context({ kind: "ended" }, { ended: refusalWords(401, undefined, "") }));
    return;
  }
  if (refused(roles)) {
    res.status(404).render("error", { ...NOT_FOUND });
    return;
  }
  const view = roles.status === 200 ? peopleView(people.json, roles.json) : undefined;
  if (view === undefined) return unreadable(res);
  res.render("admin-people", context(view));
}

export const adminPeople: PageModule = {
  id: "admin",
  path: "/admin/people",
  methods: ["GET"],
  trees: ["govuk"],
  handler: adminPeopleGet,
};
