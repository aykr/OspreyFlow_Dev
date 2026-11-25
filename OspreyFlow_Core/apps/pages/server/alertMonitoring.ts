/**
 * The alert monitoring figures, a page of the GOV.UK tree (slice GR3a; ADR-152 decisions 7, 8, 10 and 12; FUNCTIONS row
 * `reports-figures`; scenario AM):
 *
 *   GET  /reports?case=<case>[&weeks=<4, 12, 26 or 52>]   the case's alert monitoring figures, a table and a plain SVG chart of each
 *
 * The page makes one call to the Conduit, `GET /v1/investigations/{id}/reports`, as the person (`conduit.ts`: their bearer, the case
 * encoded as one piece), and draws only what that call sends. **It has no access rule of its own** (rules 3 and 4): the Conduit
 * counts every figure for the reader, leaves out an alert concerning anything the reader cannot see, sends held rows to Editors and
 * above, and refuses a report past its bound; this page adds up the rows it is sent and says them. It makes no new Conduit route
 * (decision 10) and never asks for the Superset list.
 *
 * **One page for every case the person cannot open.** A request that names no case, a case that is not there, a case the person
 * holds no level on (the Conduit answers it as one that is not there) and a person without `read_reports` (the Conduit refuses
 * the right first, 403) are all answered 404 with the same page and the same words, so the page says nothing of which it was (the
 * owner's ruling of 24 November 2026). A report past its bound is a page of words with the route's own 409; a Conduit that cannot
 * be reached, fails, or answers a body that is not the figures is a page of words with 502, and never a figure made from part of
 * what was sent (rule 2).
 *
 * GET is the only method it answers, and it adds no action beyond links, so its keyboard case is the tab order through it.
 */
import type { Request, Response } from "express";

import { SessionEnded } from "./accessToken.js";
import { ConduitUnreachable, conduitFor, v1 } from "./conduit.js";
import type { Reply } from "./conduit.js";
import type { ForwardSettings } from "./config.js";
import type { PageModule } from "./pages.js";
import { ALERT_MONITORING_WORDS, limitView, monitoringView, periodOf, readLimit, readReport } from "./views/alertMonitoringWords.js";
import type { MonitoringView } from "./views/alertMonitoringWords.js";

const MAX_ID_CHARS = 200;

interface Settings {
  forward: ForwardSettings | undefined;
  log: (message: string) => void;
}

const one = (value: unknown): string | undefined => (typeof value === "string" ? value : undefined);

/** The one page for a case the person cannot open, whatever the reason. */
function notFound(res: Response): void {
  const words = ALERT_MONITORING_WORDS.notFound;
  res.status(404).render("error", { title: words.title, message: words.message });
}

function unreadable(res: Response): void {
  const words = ALERT_MONITORING_WORDS.unreadable;
  res.status(502).render("error", { title: words.title, message: words.message });
}

function draw(res: Response, status: number, caseId: string, view: MonitoringView): void {
  res.status(status).render("alert-monitoring", { title: ALERT_MONITORING_WORDS.title, page: "alert-monitoring", words: ALERT_MONITORING_WORDS, caseId, view });
}

async function alertMonitoringGet(req: Request, res: Response): Promise<void> {
  const settings = req.app.locals["studio"] as Settings | undefined;
  const auth = req.session.auth;
  const asked = one(req.query["case"]);
  // No case named, or a name that cannot be one: the page for a case that cannot be opened, with no call made.
  if (asked === undefined || asked === "" || asked.length > MAX_ID_CHARS) {
    notFound(res);
    return;
  }
  if (!auth || !settings?.forward) {
    unreadable(res);
    return;
  }
  const weeks = periodOf(one(req.query["weeks"]));
  let reply: Reply;
  try {
    const conduit = await conduitFor(settings.forward, auth, settings.log);
    reply = await conduit({ path: v1("investigations", asked, "reports"), query: { weeks } });
  } catch (error) {
    // The provider would not renew the token and the session is ended: the app answers with the sign-in redirect (`app.ts`).
    if (error instanceof SessionEnded) throw error;
    if (!(error instanceof ConduitUnreachable)) settings.log("pages: reports: the person's access could not be prepared (502)");
    unreadable(res);
    return;
  }
  if (reply.status === 200) {
    const report = readReport(reply.json);
    if (report === undefined) {
      settings.log("pages: reports: the Conduit's answer was not the figures (502)");
      unreadable(res);
      return;
    }
    draw(res, 200, asked, monitoringView(report, asked));
    return;
  }
  if (reply.status === 409) {
    const limit = readLimit(reply.json);
    if (limit === undefined) {
      unreadable(res);
      return;
    }
    draw(res, 409, asked, limitView(limit, asked, weeks));
    return;
  }
  // 404 (a case the person holds no level on is answered as one that is not there) and 403 (no `read_reports`, refused first): one page.
  if (reply.status === 404 || reply.status === 403) {
    notFound(res);
    return;
  }
  unreadable(res);
}

export const alertMonitoring: PageModule = {
  id: "reports-figures",
  path: "/reports",
  methods: ["GET"],
  trees: ["govuk"],
  handler: alertMonitoringGet,
};
