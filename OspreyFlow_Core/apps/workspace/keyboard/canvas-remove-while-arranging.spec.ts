// A node taken out while the canvas is moving nodes into place. Sigma's `animateNodes` (the canvas's arrange,
// 420 ms) writes each target node's x and y on every frame, reading its targets afresh each frame. A remove delta
// (another reader's change, a withdrawal, a revert) that drops one of them mid-animation left the next frame
// writing to a node no longer in the graph: `NotFoundGraphError: Graph.setNodeAttribute: could not find the
// "n0" node`, thrown in an animation frame, uncaught (found 14 November 2026, building the expand refusal's
// stale-node case). A snapshot that clears the graph mid-animation is the same, for every node at once.
import { expect, type Page, test } from "@playwright/test";

type W = {
  __CANVAS__?: { removeNode?: (id: string) => void; resnapshotWithout?: (id: string) => void; hasNode: (id: string) => boolean };
  __KEYBOARD__?: { focused: string | null };
};

async function arrangeAndThen(page: Page, act: (focused: string) => Promise<void>): Promise<string[]> {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  const focused = await page.evaluate(() => (window as unknown as W).__KEYBOARD__?.focused ?? null);
  expect(focused).toBeTruthy();
  // Let the first fill's own move end, so the one under test is the Arrange pressed now.
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: "Arrange", exact: true }).click();
  await act(focused!);
  // Past the animation's 420 ms, so every frame it would have drawn has run.
  await page.waitForTimeout(900);
  return errors;
}

test("a node taken out while the canvas arranges is left out of the move, with no error", async ({ page }) => {
  let removed = "";
  const errors = await arrangeAndThen(page, async (focused) => {
    removed = focused;
    await page.evaluate((id) => (window as unknown as W).__CANVAS__!.removeNode!(id), focused);
  });
  expect(await page.evaluate((id) => (window as unknown as W).__CANVAS__!.hasNode(id), removed)).toBe(false);
  expect(errors).toEqual([]);
  // The canvas still answers: its menu opens on what is left.
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await page.keyboard.press("\\");
  await expect(page.locator(".radial-menu__list[role='menu']")).toBeVisible();
});

test("a snapshot that clears the graph while the canvas arranges is drawn, with no error", async ({ page }) => {
  let left = "";
  const errors = await arrangeAndThen(page, async (focused) => {
    left = focused;
    await page.evaluate((id) => (window as unknown as W).__CANVAS__!.resnapshotWithout!(id), focused);
  });
  expect(await page.evaluate((id) => (window as unknown as W).__CANVAS__!.hasNode(id), left)).toBe(false);
  expect(errors).toEqual([]);
});
