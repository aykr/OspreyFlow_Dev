// What only a browser can show about the two websites (see playwright.config.ts). Each case was shown red first
// (`process/lanes/docs/gates/sites2-browser-red-first.txt`): against the 12 November pages, which had neither a theme
// switch nor a player, and against copies of the current pages with one defect planted in `site.js`.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

const PAGES = [
  "org/index.html", "org/features.html", "org/public-sector.html", "org/get-started.html", "org/team.html",
  "org/contribute.html", "org/governance.html",
  "net/index.html", "net/sectors.html", "net/public-sector.html", "net/services.html", "net/contact.html",
];
const STEP_MS = 7_000;
const KEY = "ospreyflow.site.theme";

/** The one scene a player shows, as "seat/step"; it fails when none or more than one is shown. */
async function shown(player: Locator): Promise<string> {
  const scenes = player.locator(".ov-scene:not([hidden]), .gv-scene:not([hidden])");
  await expect(scenes).toHaveCount(1);
  return `${await scenes.getAttribute("data-seat")}/${await scenes.getAttribute("data-step")}`;
}

/** Scrolls the player into view and lets the browser tell it so: an IntersectionObserver reports on a real rendering
 *  frame, which the installed clock does not run, so the wait is real time, not the clock's. */
async function inView(page: Page, player: Locator): Promise<void> {
  await player.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
}

async function openWithClock(page: Page, path: string): Promise<void> {
  await page.clock.install();
  await page.goto(path);
}

// ---------------------------------------------------------------- the theme switch

test("the theme switch turns the dark theme on and off, is kept, and is applied before the page paints", async ({ page }) => {
  await page.goto("org/index.html");
  const html = page.locator("html");
  const button = page.getByRole("button", { name: "Dark theme" });
  await expect(html).not.toHaveClass(/theme-dark/);
  await button.click();
  await expect(html).toHaveClass(/theme-dark/);
  await expect(page.getByRole("button", { name: "Light theme" })).toBeVisible();
  expect(await page.evaluate((k) => localStorage.getItem(k), KEY)).toBe("dark");

  // Another page, and the other site: dark from the first paint, set by the head script before site.js runs.
  await page.route("**/assets/site.js", (route) => route.abort());
  await page.goto("org/features.html");
  await expect(html).toHaveClass(/theme-dark/);
  await page.unroute("**/assets/site.js");
  await page.goto("org/team.html");
  await expect(html).toHaveClass(/theme-dark/);
  await page.getByRole("button", { name: "Light theme" }).click();
  await expect(html).not.toHaveClass(/theme-dark/);
  expect(await page.evaluate((k) => localStorage.getItem(k), KEY)).toBe("light");
});

test("the dark theme changes the page's colours and the overview's, and leaves the GOV.UK drawing light", async ({ page }) => {
  await page.goto("org/public-sector.html");
  const ground = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const gv = () => page.locator(".gv").evaluate((el) => getComputedStyle(el).backgroundColor);
  const light = await ground();
  const gvLight = await gv();
  await page.getByRole("button", { name: "Dark theme" }).click();
  expect(await ground()).not.toBe(light);
  expect(await gv()).toBe(gvLight);
  await page.goto("org/index.html");
  const ov = await page.locator(".ov").evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(ov).toBe("rgb(16, 19, 20)"); // --k-app in .theme-dark .ov
});

// ---------------------------------------------------------------- the player

for (const [path, selector, next] of [
  ["org/index.html", ".ov", "0/1"],
  ["net/index.html", ".ov", "0/1"],
  ["org/public-sector.html", ".gv", "0/1"],
] as const) {
  test(`the player on ${path} advances every seven seconds, and pauses`, async ({ page }) => {
    await openWithClock(page, path);
    const player = page.locator(selector);
    await inView(page, player);
    expect(await shown(player)).toBe("0/0");
    await page.clock.runFor(STEP_MS + 500);
    expect(await shown(player)).toBe(next);

    await player.locator("[data-play]").click();
    await expect(player.locator("[data-play]")).toHaveText("Play");
    await expect(player).toHaveClass(/is-paused/);
    expect(await player.evaluate((el) => getComputedStyle(el.querySelector(".a-fade, .a-rise, .a-pop")!).animationPlayState)).toBe("paused");
    await page.clock.runFor(STEP_MS * 3);
    expect(await shown(player)).toBe(next);
  });
}

test("the overview moves from one seat to the next after its last chapter, and loops", async ({ page }) => {
  await openWithClock(page, "org/index.html");
  const player = page.locator(".ov");
  await inView(page, player);
  await page.clock.runFor(4 * STEP_MS + 500);
  expect(await shown(player)).toBe("1/0");
  await expect(player.locator('.ov-steps[data-seat="1"]')).toBeVisible();
  await expect(player.locator('.ov-tab[data-seat="1"]')).toHaveAttribute("aria-pressed", "true");
  await page.clock.runFor(7 * STEP_MS);
  expect(await shown(player)).toBe("0/0");
});

test("the player starts paused, and stays so, under reduced motion", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  await openWithClock(page, "org/index.html");
  const player = page.locator(".ov");
  await expect(player.locator("[data-play]")).toHaveText("Play");
  await page.clock.runFor(STEP_MS * 3);
  expect(await shown(player)).toBe("0/0");
  await context.close();
});

/** How much of the shown scene's drawing can be seen: the share of its drawn shapes and words at full opacity. */
async function drawn(player: Locator): Promise<number> {
  return player.evaluate((el) => {
    const scene = el.querySelector(".ov-scene:not([hidden]), .gv-scene:not([hidden])")!;
    const parts = [...scene.querySelectorAll("svg text, svg path, svg rect")];
    const seen = parts.filter((p) => {
      let node: Element | null = p;
      while (node && node !== scene) {
        if (Number(getComputedStyle(node).opacity) < 0.99) return false;
        node = node.parentElement;
      }
      return true;
    });
    return seen.length / parts.length;
  });
}

test("under reduced motion every chapter is drawn in full, still", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  for (const [path, selector] of [["org/index.html", ".ov"], ["org/public-sector.html", ".gv"]] as const) {
    await page.goto(path);
    const player = page.locator(selector);
    await expect.poll(() => drawn(player)).toBeGreaterThan(0.95);
    await player.locator("button[data-step]").nth(2).click();
    await expect.poll(() => drawn(player)).toBeGreaterThan(0.95);
  }
  await context.close();
});

test("a chapter chosen while paused is drawn in full", async ({ page }) => {
  await page.goto("org/index.html");
  const player = page.locator(".ov");
  await player.locator("[data-play]").click();
  await player.locator('.ov-tab[data-seat="1"]').click();
  await player.locator('.ov-steps[data-seat="1"] button[data-step="1"]').click();
  await page.waitForTimeout(400);
  expect(await drawn(player)).toBeGreaterThan(0.95);
});

test("the player does not advance off screen, and does once it is back", async ({ page }) => {
  await openWithClock(page, "org/index.html");
  const player = page.locator(".ov");
  await inView(page, page.locator("footer"));
  expect(await player.evaluate((el) => el.getBoundingClientRect().bottom < 0)).toBe(true);
  await page.clock.runFor(STEP_MS * 3);
  expect(await shown(player)).toBe("0/0");
  await inView(page, player);
  await page.clock.runFor(STEP_MS + 500);
  expect(await shown(player)).toBe("0/1");
});

test("the player does not advance in a hidden tab", async ({ page }) => {
  await openWithClock(page, "net/index.html");
  const player = page.locator(".ov");
  await inView(page, player);
  await page.evaluate(() => Object.defineProperty(document, "hidden", { configurable: true, get: () => true }));
  await page.clock.runFor(STEP_MS * 3);
  expect(await shown(player)).toBe("0/0");
});

// ---------------------------------------------------------------- the keyboard

test("every control in the overview works from the keyboard alone", async ({ page }) => {
  await openWithClock(page, "org/index.html");
  const player = page.locator(".ov");
  // Pause first, so the clock cannot move the scene under the keys.
  await player.locator("[data-play]").focus();
  await page.keyboard.press("Enter");
  await expect(player.locator("[data-play]")).toHaveText("Play");

  await player.locator('.ov-tab[data-seat="2"]').focus();
  await page.keyboard.press("Space");
  expect(await shown(player)).toBe("2/0");
  await page.keyboard.press("Tab"); // past Pause, to the seat's first chapter button
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toHaveText("Access");
  await page.keyboard.press("Enter");
  expect(await shown(player)).toBe("2/1");
  const outline = await page.locator(":focus").evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe("none");
});

test("every control in the GOV.UK drawing works from the keyboard alone", async ({ page }) => {
  await openWithClock(page, "org/public-sector.html");
  const player = page.locator(".gv");
  await player.locator("[data-play]").focus();
  await page.keyboard.press("Enter");
  await player.getByRole("button", { name: "Accessible" }).focus();
  await page.keyboard.press("Enter");
  expect(await shown(player)).toBe("0/3");
});

test("the skip link, the site switcher and the theme switch come first, by keyboard", async ({ page }) => {
  await page.goto("net/services.html");
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toHaveText("Skip to main content");
  for (const name of ["Project ospreyflow.org", "Services ospreyflow.net", /Release v\d+\.\d+\.\d+/, "Solirius Reply", "Dark theme"]) {
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toHaveAccessibleName(name);
  }
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveClass(/theme-dark/);
});

// ---------------------------------------------------------------- accessibility scans, in both themes

for (const theme of ["light", "dark"] as const) {
  for (const path of PAGES) {
    test(`axe finds nothing on ${path} in the ${theme} theme`, async ({ browser }) => {
      // Reduced motion, so a scan never meets a drawing halfway through fading in.
      const context = await browser.newContext({ reducedMotion: "reduce" });
      await context.addInitScript(([k, v]) => localStorage.setItem(k, v), [KEY, theme] as const);
      const page = await context.newPage();
      await page.goto(path);
      await expect(page.locator("html")).toHaveClass(theme === "dark" ? /theme-dark/ : /^(?!.*theme-dark)/);
      await page.evaluate(() => document.fonts.ready);
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
      expect(result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
      await context.close();
    });
  }
}

// ---------------------------------------------------------------- a phone's width

test("no page scrolls sideways at a phone's width", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 360, height: 740 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  const wide: string[] = [];
  for (const path of PAGES) {
    await page.goto(path);
    const [scroll, width] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    if (scroll > width) wide.push(`${path}: ${scroll} > ${width}`);
  }
  expect(wide).toEqual([]);
  await context.close();
});

// ---------------------------------------------------------------- nothing fetched from elsewhere

test("no page asks for anything from another host, fonts included", async ({ page }) => {
  const elsewhere: string[] = [];
  page.on("request", (r) => {
    if (!r.url().startsWith("http://127.0.0.1:")) elsewhere.push(r.url());
  });
  const fonts: string[] = [];
  page.on("response", (r) => {
    if (r.url().endsWith(".woff2") && r.ok()) fonts.push(r.url().split("/").pop()!);
  });
  for (const path of PAGES) {
    await page.goto(path);
    await page.evaluate(() => document.fonts.ready);
  }
  expect(elsewhere).toEqual([]);
  expect(new Set(fonts.map((f) => f.split("-latin")[0]))).toEqual(new Set(["atkinson-hyperlegible-next", "ibm-plex-mono"]));
});
