/**
 * Help, the first page of the GOV.UK tree (slice GR2a; ADR-152 decisions 6, 7 and 12; FUNCTIONS row `help`; scenario HP):
 *
 *   GET  /help   the roles, the places, the levels in a case, teams and Authors, and what each right lets a person do
 *
 * A page of static words (`views/helpWords.ts`, from the shared package's `roles.ts`), drawn on the server and complete with
 * scripts off. It sits behind the session as every page does (`pages.ts`: an unsigned request is sent to sign-in) and asks
 * nothing more of the person: it names no right, makes no call to the Conduit, shows no count and writes nothing, so what a
 * person may do is never what decides whether they may read what it says. GET is the only method it answers.
 *
 * It is the GOV.UK tree's alone for now: a GOV.UK page may exist before its Default twin (the owner, 24 November 2026), so
 * a service started for the Default tree answers `/help` as a path nothing serves.
 */
import type { Request, Response } from "express";

import type { PageModule } from "./pages.js";
import { HELP_WORDS, helpView } from "./views/helpWords.js";

function helpGet(_req: Request, res: Response): void {
  res.render("help", { title: HELP_WORDS.title, page: "help", words: HELP_WORDS, help: helpView() });
}

export const help: PageModule = {
  id: "help",
  path: "/help",
  methods: ["GET"],
  trees: ["govuk"],
  handler: helpGet,
};
