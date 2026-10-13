// The top bar (ADR-065), in a real browser. Two things a unit test cannot see: that the menus can
// be clicked (nothing sits over them) and that the bar stays on one line with Filters inside the
// search box. The keyboard routes are the rule 13 proof for the case menu and the account menu.
import { expect, test } from "@playwright/test";

declare global {
  interface Window {
    __TOPBAR__?: { opened: string | null; browsed: boolean; signedOut: boolean; rail: string[] };
  }
}

// Wide enough for the whole bar, with the resolution slider, on one line. Narrower windows wrap
// whole items onto a second line (`.app-header`), which is the intended fallback.
test.use({ viewport: { width: 1440, height: 400 } });

test("the case choice and the account are one button each, and the bar is one line", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  await expect(page.getByRole("button", { name: /^Case: Enron corpus/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /osprey-demo-analyst · OFFICIAL/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /osprey-demo-analyst/ })).toContainText("OFFICIAL");
  await expect(page.getByRole("button", { name: "All cases" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
  const height = (await page.locator("header.app-header").boundingBox())!.height;
  expect(height).toBeLessThan(60);
});

test("the Filters icon sits inside the search box", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  const box = (await page.getByRole("combobox").boundingBox())!;
  const filters = (await page.getByRole("button", { name: "Filters" }).boundingBox())!;
  expect(filters.x).toBeGreaterThanOrEqual(box.x);
  expect(filters.x + filters.width).toBeLessThanOrEqual(box.x + box.width);
  expect(filters.y).toBeGreaterThanOrEqual(box.y);
  expect(filters.y + filters.height).toBeLessThanOrEqual(box.y + box.height);
});

test("with the mouse: choose another case, browse all cases, sign out", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  await page.getByRole("button", { name: /^Case:/ }).click({ timeout: 3000 });
  await page.getByRole("button", { name: /PaySim mobile money/ }).click({ timeout: 3000 });
  expect(await page.evaluate(() => window.__TOPBAR__?.opened)).toBe("c2");

  await page.getByRole("button", { name: /^Case:/ }).click({ timeout: 3000 });
  await page.getByRole("button", { name: "All cases" }).click({ timeout: 3000 });
  expect(await page.evaluate(() => window.__TOPBAR__?.browsed)).toBe(true);

  await page.getByRole("button", { name: /osprey-demo-analyst/ }).click({ timeout: 3000 });
  await page.getByRole("button", { name: "Sign out" }).click({ timeout: 3000 });
  expect(await page.evaluate(() => window.__TOPBAR__?.signedOut)).toBe(true);
});

test("with the keyboard: open the case menu, move through it, choose, and Escape closes", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  const trigger = page.getByRole("button", { name: /^Case:/ });
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Case menu" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.getByRole("group", { name: "Case menu" })).toHaveCount(0);
  await expect(trigger).toBeFocused();

  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab"); // the open case
  await page.keyboard.press("Tab"); // the next case
  await expect(page.getByRole("button", { name: /PaySim mobile money/ })).toBeFocused();
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => window.__TOPBAR__?.opened)).toBe("c2");
  await expect(page.getByRole("group", { name: "Case menu" })).toHaveCount(0);
});

test("with the keyboard: tabbing out of an open menu closes it, and the account menu signs out", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  await page.getByRole("button", { name: /^Case:/ }).focus();
  await page.keyboard.press("Enter");
  // Two cases, All cases and New case are inside the menu; the next Tab leaves it for the search box.
  for (let i = 0; i < 5; i++) await page.keyboard.press("Tab");
  await expect(page.getByRole("combobox")).toBeFocused();
  await expect(page.getByRole("group", { name: "Case menu" })).toHaveCount(0);

  await page.getByRole("button", { name: /osprey-demo-analyst/ }).focus();
  await page.keyboard.press("Enter");
  // ADR-115 Amendment 1: the theme is an icon in the bar now, so the menu goes straight to Sign out.
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeFocused();
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => window.__TOPBAR__?.signedOut)).toBe(true);
});

test("with the keyboard: the theme is switched from its icon in the bar, and the page changes (ADR-115 Amendment 1)", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  const before = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const theme = page.getByRole("button", { name: "Switch to the light theme" });
  // In the bar, just before the account, and not in the account menu.
  const account = page.getByRole("button", { name: /osprey-demo-analyst/ });
  await theme.focus();
  await page.keyboard.press("Tab");
  await expect(account).toBeFocused();
  await account.press("Enter");
  await expect(page.getByRole("menu").or(page.getByRole("group")).getByRole("button", { name: /Switch to the/ })).toHaveCount(0);
  await account.press("Escape");
  await theme.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  const after = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(after).not.toBe(before);
  // The same icon, now offering dark, keeps focus and switches back.
  const back = page.getByRole("button", { name: "Switch to the dark theme" });
  await expect(back).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  // The bar is still one line.
  const height = (await page.locator("header.app-header").boundingBox())!.height;
  expect(height).toBeLessThan(60);
});

test("the search hint floats over the page, keeps the bar one line, and fades by itself", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  const hint = page.getByRole("status");
  await page.getByRole("combobox").fill("per");
  await expect(hint).toContainText("more match");
  // It is laid over the page, not part of the bar: the bar does not grow to hold it.
  const height = (await page.locator("header.app-header").boundingBox())!.height;
  expect(height).toBeLessThan(60);
  const bar = (await page.locator("header.app-header").boundingBox())!;
  const text = (await hint.boundingBox())!;
  expect(text.y).toBeGreaterThanOrEqual(bar.y + bar.height - 8);
  await expect(hint).not.toHaveAttribute("data-faded", "true");
  // Then it dissolves; the words stay readable for anyone using a screen reader.
  await expect(hint).toHaveAttribute("data-faded", "true", { timeout: 7000 });
  await expect.poll(() => hint.evaluate((el) => getComputedStyle(el).opacity)).toBe("0");
  await expect(hint).toContainText("more match");
  expect((await page.locator("header.app-header").boundingBox())!.height).toBeLessThan(60);
});

test("the Filters panel floats over the page too, so opening it does not grow the bar", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  await page.getByRole("button", { name: "Filters" }).click();
  await expect(page.getByText("Ignore case")).toBeVisible();
  expect((await page.locator("header.app-header").boundingBox())!.height).toBeLessThan(60);
});
