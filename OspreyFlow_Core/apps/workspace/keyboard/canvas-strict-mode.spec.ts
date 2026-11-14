// The canvas under React's StrictMode, as the App is mounted (`src/main.tsx`): in a dev build each effect
// is run, cleaned up and run again on mount. The cleanup kills Sigma, and `sigma.kill()` empties its
// container (`while (container.firstChild) container.removeChild(...)`). Where that container is the
// one React draws the canvas's toolbar, menus and selection bar into, they are gone from the page while
// React still holds them, and the next node React inserts among them throws `insertBefore`, taking the
// whole tree with it. Found by the live tier (14 November 2026, A12: `\` on the canvas, `#root` left
// empty). The keyboard harness mounts without StrictMode, so no case here saw it.
import { expect, test } from "@playwright/test";

test("under StrictMode the canvas keeps its own toolbar, and \\ opens its menu with no page error", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/keyboard/harness.html?strict=1");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await expect(canvas).toBeVisible();
  // The toolbar is React's, drawn inside the canvas: gone when Sigma's cleanup emptied its container.
  await expect(canvas.getByRole("toolbar", { name: "Canvas tools" })).toBeVisible();
  await canvas.focus();
  await page.keyboard.press("\\");
  await expect(page.locator(".radial-menu__list[role='menu']")).toBeVisible();
  expect(errors).toEqual([]);
});

test("without StrictMode, the same: the harness's usual mount is unchanged", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await expect(canvas.getByRole("toolbar", { name: "Canvas tools" })).toBeVisible();
  await canvas.focus();
  await page.keyboard.press("\\");
  await expect(page.locator(".radial-menu__list[role='menu']")).toBeVisible();
});
