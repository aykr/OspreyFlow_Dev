// The GOV.UK tree's alert queue by keyboard alone, with scripts on (slice RM1a; `CLAUDE.md` rule 13; ADR-152 decision 6 and I4; scenario AQ9).
// The page has no action of its own beyond links (it is read-only: nothing closes, assigns or edits), so the cases that prove it are the tab
// order through the queue and through the list of cases, in the page's own order with the skip link first, and that Enter on a link does what
// it says. The service is the real one for the `govuk` tree, the Conduit is the fixture that refuses what the real route refuses. No
// `page.mouse`, no `.click()`.
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { aCase, aReader, aRow, queueConduit } from "../alertQueueConduit.js";
import type { QueueConduit } from "../alertQueueConduit.js";
import { startQueueService } from "../alertQueueServer.js";
import { buildScratchAssets, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets, Govuk } from "../helpServer.js";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

const mine = aCase({ id: "case-wing", name: "Wing review" });
const other = aCase({ id: "case-harbour", name: "Harbour case" });
const reader = aReader({ cases: [mine, other] });

async function withService(run: (service: Govuk, conduit: QueueConduit) => Promise<void>): Promise<void> {
  const conduit = await queueConduit({
    readers: [reader],
    alerts: [
      { caseId: mine.id, row: aRow({ summary: "Payments just under the limit" }) },
      { caseId: mine.id, row: aRow({ summary: "A hotlisted number appeared", row: { kind: "hotlist" } }) },
    ],
  });
  const service = await startQueueService(assets, conduit.url, reader);
  try {
    await run(service, conduit);
  } finally {
    await service.stop();
    await conduit.stop();
  }
}

async function openQueue(page: Page, base: string, path: string): Promise<void> {
  await page.goto(`${base}/session/sign-in`);
  await page.goto(`${base}${path}`);
}

test.describe("the alert queue page with scripts", () => {
  test("QK1: Tab reaches the skip link first, then the sign-out, the way to all cases and the way back, in the page's order", async ({ page }) => {
    await withService(async (s) => {
      await openQueue(page, s.base, `/alert-queue?case=${mine.id}`);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Alert queue");
      await expect(page.getByRole("row")).toHaveCount(3); // the header row and the two alerts the Conduit sent
      expect(await tabOrder(page)).toEqual(["a: Skip to main content", "button: Sign out", "a: All cases", "a: Back to Home"]);
    });
  });

  test("QK2: with no case, Tab reaches a link to each case, and Enter on one opens its queue", async ({ page }) => {
    await withService(async (s) => {
      await openQueue(page, s.base, "/alert-queue");
      expect(await tabOrder(page)).toEqual(["a: Skip to main content", "button: Sign out", "a: Wing review", "a: Harbour case", "a: Back to Home"]);
      await page.getByRole("link", { name: "Wing review" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`/alert-queue\\?case=${mine.id}$`));
      await expect(page.getByRole("table")).toBeVisible();
      await page.getByRole("link", { name: "All cases" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp("/alert-queue$"));
    });
  });

  test("QK3: the skip link takes focus to the main landmark, and the next Tab is the first link inside it", async ({ page }) => {
    await withService(async (s) => {
      await openQueue(page, s.base, `/alert-queue?case=${mine.id}`);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("main")).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "All cases" })).toBeFocused();
    });
  });
});
