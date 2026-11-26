/**
 * What the GOV.UK tree's Playwright cases for trends shown together share (slice GR4a; scenario TS11 and TS12): the pages service
 * started in the case for the `govuk` tree, against the fixture Conduit that answers and refuses as the real pack routes do
 * (`packsConduit.ts`), with a pack of two trends and a note, of which the person may read one trend and the note. Synthetic throughout.
 */
import type { Page } from "@playwright/test";

import type { Assets } from "./helpServer.js";
import { RECORD_ASSESSMENT, figures, packItem, packsConduit } from "./packsConduit.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { generateSecret } from "../support/secret.js";
import { bearer } from "../support/studioWorld.js";

export const CASE = "case-estuary";
export const PACK = "pack-estuary";
export const ADDRESS = `/packs/trends?case=${CASE}&pack=${PACK}`;

/** The stops of the page, in its own order: the skip link, the layout's sign-out and the way back. A chart and a table add none. */
export const TRENDS_TAB_ORDER = ["a: Skip to main content", "button: Sign out", "a: Back to Home"];

export async function withTrends(assets: Assets, run: (base: string) => Promise<void>): Promise<void> {
  const token = bearer();
  const conduit = await packsConduit({
    readers: [{ token, rights: [RECORD_ASSESSMENT], cases: { [CASE]: "viewer" } }],
    cases: [CASE],
    packs: [
      {
        id: PACK,
        case_id: CASE,
        title: "Estuary movements",
        created_by: "someone-synthetic",
        created_at: "2026-11-01T09:00:00Z",
        updated_at: "2026-11-02T12:00:00Z",
        items: [
          { item: packItem({ id: "k-harbour", kind: "trend", trend: figures({ title: "Harbour meetings", points: [{ period_start: "2026-10-05T00:00:00Z", value: 3 }] }) }) },
          { item: packItem({ id: "k-ferry", kind: "trend", trend: figures({ title: "Ferry crossings", points: [] }) }), hiddenFrom: [token] },
          { item: packItem({ id: "k-note", kind: "note", note: "A note that is not a trend." }) },
        ],
      },
    ],
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
          return { subject: "sub-trends", displayName: "Alex Example", accessToken: token, refreshToken: "not-used", idpSessionExpiresAt: Date.now() + 3_600_000 };
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

export async function openTrends(page: Page, base: string): Promise<void> {
  await page.goto(`${base}/session/sign-in`);
  await page.goto(`${base}${ADDRESS}`);
}
