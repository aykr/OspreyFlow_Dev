/**
 * The pages server started for the GOV.UK tree against the cases page's fixture Conduit (`casesConduit.ts`), for the cases page's
 * keyboard and scripts-off specs (slice GR1a; scenario CS12 and CS13). Two synthetic cases of one unit, one of them with a brief; the
 * signed-in person holds a level on both and the right to investigate.
 */
import type { Page } from "@playwright/test";

import type { Assets } from "./helpServer.js";
import { casesConduit } from "./casesConduit.js";
import type { Case } from "./casesConduit.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { generateSecret } from "../support/secret.js";
import { bearer } from "../support/studioWorld.js";

const UNIT = "keyboard-unit";
export const KEYBOARD_CASES: Case[] = [
  {
    id: "k-harbour",
    name: "Harbour watch",
    created_at: "2026-10-02T09:05:00Z",
    created_by: "acct-k",
    owning_unit: UNIT,
    domains: ["fibo"],
    datasets: [{ id: "ds-k", name: "Quay ledger" }],
    brief: {
      priority: "Who moves the cargo at night?",
      requirements: [{ id: "r-k", text: "Which vessels berth after dark?", status: "open", answered_at: null, attachments: [{ kind: "trend", id: "t-k", title: "Berths" }] }],
    },
  },
  { id: "k-ferry", name: "Ferry routes", created_at: "2026-11-20T16:00:00Z", created_by: "acct-k", owning_unit: UNIT, domains: [], datasets: [], brief: { priority: "", requirements: [] } },
];

/** The stops of the list, in the page's own order: the skip link, the layout's sign-out, each case's link, the way back. */
export const LIST_TAB_ORDER = ["a: Skip to main content", "button: Sign out", "a: Harbour watch", "a: Ferry routes", "a: Back to Home"];
/** The stops of a case's page: the skip link, the sign-out, the way back to the cases, the way back to Home. */
export const CASE_TAB_ORDER = ["a: Skip to main content", "button: Sign out", "a: Back to your cases", "a: Back to Home"];

export async function withCases(assets: Assets, run: (base: string) => Promise<void>): Promise<void> {
  const token = bearer();
  const conduit = await casesConduit({
    readers: [{ token, unit: UNIT, rights: ["investigate"], levels: { "k-harbour": "author", "k-ferry": "viewer" }, hidden: ["k-ferry"] }],
    cases: KEYBOARD_CASES,
  });
  const io = { log: () => undefined, error: () => undefined, exit: () => undefined };
  const running: Running | undefined = await main(
    {
      OSPREY_PAGES_PORT: "0",
      OSPREY_PAGES_SESSION_SECRET: generateSecret(48),
      OSPREY_PAGES_TREE: "govuk",
      OSPREY_PAGES_CONDUIT_URL: conduit.url,
      OSPREY_PAGES_PUBLIC_ORIGIN: "https://osprey.test",
    },
    io,
    {
      store: new MemorySessionStore(),
      host: "127.0.0.1",
      assets,
      identityProvider: {
        async signIn() {
          return { subject: "sub-keyboard", displayName: "Alex Example", accessToken: token, refreshToken: "not-used", idpSessionExpiresAt: Date.now() + 3_600_000 };
        },
      },
    },
  );
  if (!running) throw new Error("the pages server did not start");
  try {
    await run(`http://127.0.0.1:${running.port}`);
  } finally {
    await running.stop();
    await conduit.stop();
  }
}

export async function openCases(page: Page, base: string, path = "/cases"): Promise<void> {
  await page.goto(`${base}/session/sign-in`);
  await page.goto(`${base}${path}`);
}
