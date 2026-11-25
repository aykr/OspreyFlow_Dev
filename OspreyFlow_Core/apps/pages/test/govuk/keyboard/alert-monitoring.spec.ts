// The GOV.UK tree's alert monitoring page by keyboard alone, with scripts on (slice GR3a; `CLAUDE.md` rule 13; ADR-152 decision 6 and I4;
// scenario AM8). The page adds no action beyond links, so the case that proves it is the tab order through the whole page: every stop a
// native one, in the page's own order, the skip link first, and that Enter on a period's link opens that period. No `page.mouse`, no
// `.click()`. The Conduit is the fixture of `test/support/fakeReportConduit.ts`, which refuses what the real report route refuses.
import { expect, test } from "@playwright/test";

import { buildScratchAssets, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets } from "../helpServer.js";
import { MemorySessionStore } from "../../../server/sessionStore.js";
import { main } from "../../../server/start.js";
import type { Running } from "../../../server/start.js";
import { fakeReportConduit } from "../../support/fakeReportConduit.js";
import { generateSecret } from "../../support/secret.js";

const CASE = "case-wing";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

/** The page's own stops, in its own order: the skip link, the layout's sign-out, the periods but the one shown (12), the way back. */
const TAB_ORDER = [
  "a: Skip to main content",
  "button: Sign out",
  "a: Last 4 weeks",
  "a: Last 26 weeks",
  "a: Last 52 weeks",
  "a: Back to Home",
];

async function withPage(run: (base: string) => Promise<void>): Promise<void> {
  const token = `kbd-${generateSecret(24)}`;
  const conduit = await fakeReportConduit([{ token, id: "reader", clearance: "OFFICIAL", rights: ["read_reports"], cases: { [CASE]: "editor" } }]);
  conduit.world.set(CASE, [
    { week: "2026-11-09", label: "typology", typology: "structuring", needs: "OFFICIAL" },
    { week: "2026-11-16", label: "typology", typology: "rapid_movement", needs: "OFFICIAL", closedAs: "false_positive", tookBand: "under a day" },
  ]);
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
          return { subject: "sub-keyboard", displayName: "Alex Example", accessToken: token, refreshToken: `r-${token}`, idpSessionExpiresAt: Date.now() + 3_600_000 };
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

test.describe("the alert monitoring page with scripts", () => {
  test("AK1: Tab reaches the skip link first, then the sign-out, each period but the one shown and the way back, in the page's order", async ({ page }) => {
    await withPage(async (base) => {
      await page.goto(`${base}/session/sign-in`);
      await page.goto(`${base}/reports?case=${CASE}`);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Alert monitoring");
      expect(await tabOrder(page)).toEqual(TAB_ORDER);
    });
  });

  test("AK2: Enter on a period's link opens that period, and the chart and its table are on the page for a reader who moves by them", async ({ page }) => {
    await withPage(async (base) => {
      await page.goto(`${base}/session/sign-in`);
      await page.goto(`${base}/reports?case=${CASE}`);
      await page.getByRole("link", { name: "Last 4 weeks" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`/reports\\?case=${CASE}&weeks=4$`));
      await expect(page.getByText("2 alerts raised in the last 4 weeks")).toBeVisible();
      await expect(page.getByRole("img", { name: "Bar chart: alerts raised each week" })).toHaveCount(1);
      const table = page.getByRole("table", { name: "Alerts raised each week" });
      await expect(table.getByRole("columnheader")).toHaveText(["Week starting", "Alerts raised"]);
      await expect(table.getByRole("rowheader")).toHaveCount(2);
    });
  });
});
