// v0.6.1 glass-rows A and C (ADR-145 Amendment 19 decisions 5 and 6; the owner's rulings 1, 3, 4, 6 and 7 of
// 16 November 2026), on the real canvas toolbar and the real case line (`glass-toolbar-harness.tsx`, wired by App's
// own `useViewToolbar`). The keyboard routes themselves are `keyboard.spec.ts`'s (CANVAS_ACTIONS, rule 13).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { checkUndecidedContrast } from "../a11y/undecidedContrast";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
type Look = "dark" | "light" | "govuk";

async function open(page: Page, query = "", look: Look = "dark"): Promise<void> {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const parts = [query, look === "govuk" ? "brand=govuk" : "", look === "light" ? "theme=light" : ""].filter(Boolean).join("&");
  await page.goto(`/keyboard/glass-toolbar-harness.html${parts ? `?${parts}` : ""}`);
  await expect(page.getByRole("region", { name: "You are in the Glass" })).toBeVisible();
}

const tools = (page: Page) => page.getByRole("toolbar", { name: "Canvas tools" });
const caseLine = (page: Page) => page.getByRole("region", { name: "You are in the Glass" });

test("hidden means out of the tab order and the accessibility tree: Tab from Show toolbar never reaches a toolbar control", async ({ page }) => {
  await open(page);
  await tools(page).getByRole("button", { name: "Hide toolbar" }).click();
  await expect(tools(page)).toHaveCount(0);
  await expect(page.locator("#glass-view-toolbar")).toBeHidden();
  const show = caseLine(page).getByRole("button", { name: "Show toolbar" });
  await expect(show).toBeFocused();
  // Every stop after Show toolbar, round to the canvas: none is inside the hidden toolbar.
  const inside: string[] = [];
  for (let i = 0; i < 6; i += 1) {
    await page.keyboard.press("Tab");
    const where = await page.evaluate(() => {
      const el = document.activeElement;
      return el?.closest("#glass-view-toolbar") ? (el.getAttribute("aria-label") ?? el.textContent ?? "") : null;
    });
    if (where !== null) inside.push(where);
  }
  expect(inside).toEqual([]);
  const snapshot = await page.locator("body").ariaSnapshot();
  expect(snapshot).not.toContain("Canvas tools");
  expect(snapshot).not.toContain("Match strictness");
});

test("the setting is the analyst's and survives a reload: the Glass opens hidden, and another analyst's opens shown", async ({ page }) => {
  await open(page);
  await tools(page).getByRole("button", { name: "Hide toolbar" }).click();
  expect(await page.evaluate(() => localStorage.getItem("ospreyflow.glass.toolbar.osprey-demo-analyst"))).toBe("hidden");
  // The first draw is held hidden in jsdom (`App.chrome.test.tsx`, plant C18); a watch of the page's mutations here could
  // not be shown red by a late hide (the plants' C18b), so it is not claimed here.
  await page.reload();
  await expect(caseLine(page).getByRole("button", { name: "Show toolbar" })).toBeVisible();
  await expect(tools(page)).toHaveCount(0);
  await open(page, "user=someone-else");
  await expect(tools(page)).toBeVisible();
  await expect(caseLine(page).getByRole("button", { name: "Show toolbar" })).toHaveCount(0);
});

test("the Map's row hides the same way, under the same setting", async ({ page }) => {
  await open(page, "view=map");
  const row = page.getByRole("toolbar", { name: "Map view" });
  await row.getByRole("button", { name: "Hide toolbar" }).click();
  await expect(page.locator("#glass-view-toolbar")).toBeHidden();
  await expect(caseLine(page).getByRole("button", { name: "Show toolbar" })).toBeFocused();
  await open(page);
  await expect(tools(page)).toHaveCount(0);
});

// The owner's brief: showing or hiding the toolbar moves the canvas once, by the toolbar's height, and the graph keeps
// its centre and zoom. On the Graph the canvas toolbar lies over the canvas (case's proposal 2.2), so what moves is the
// top of the drawing area, from the toolbar's bottom edge to the canvas's own top; the canvas element moves only by
// what the slim line gives back (nothing where both forms are one line). Each is watched every frame, so a move in
// two steps (a jump and a settle) is seen.
// At 400 px the full line is taller than the slim one (measured on B's line), so the canvas element itself moves too, once;
// at 540 px the slim line was once taller than the full one (case's ruling 14 fixed it): the canvas must not move down.
for (const viewport of [1280, 540, 400]) test(`hiding and showing moves the drawing area's top once each way, by the toolbar's height, keeping the graph's centre and zoom (${viewport} px)`, async ({ page }) => {
  await page.setViewportSize({ width: viewport, height: 800 });
  await open(page);
  await expect.poll(() => page.evaluate(() => window.__GLASS_TOOLBAR__!.cameraState())).not.toBeNull();
  await page.waitForTimeout(800);
  await page.evaluate(() => {
    const seen = { drawing: [] as number[], canvas: [] as number[] };
    (window as unknown as { __SEEN__: typeof seen }).__SEEN__ = seen;
    const watch = () => {
      const canvas = window.__GLASS_TOOLBAR__!.canvasBox()!.top;
      const bar = document.getElementById("glass-view-toolbar");
      const drawing = bar && !bar.hidden ? bar.getBoundingClientRect().bottom : canvas;
      if (seen.drawing.at(-1) !== drawing) seen.drawing.push(drawing);
      if (seen.canvas.at(-1) !== canvas) seen.canvas.push(canvas);
      requestAnimationFrame(watch);
    };
    watch();
  });
  const read = () =>
    page.evaluate(() => ({
      seen: structuredClone((window as unknown as { __SEEN__: { drawing: number[]; canvas: number[] } }).__SEEN__),
      camera: window.__GLASS_TOOLBAR__!.cameraState()!,
      bar: document.getElementById("glass-view-toolbar")!.getBoundingClientRect().height,
      line: document.querySelector('[role="region"][aria-labelledby="context-banner-title"]')!.getBoundingClientRect().height,
    }));
  const before = await read();
  const toolbarHeight = before.bar;
  expect(toolbarHeight).toBeGreaterThan(30);
  await tools(page).getByRole("button", { name: "Hide toolbar" }).click();
  await page.waitForTimeout(500);
  const hidden = await read();
  const [drawingBefore] = before.seen.drawing;
  expect(hidden.seen.drawing).toHaveLength(2);
  expect(drawingBefore! - hidden.seen.drawing[1]!).toBeCloseTo(toolbarHeight + (before.line - hidden.line), 0);
  // The canvas element: moved by the line's change alone, at most once.
  expect(hidden.seen.canvas.length).toBe(before.line === hidden.line ? 1 : 2);
  expect(hidden.camera).toEqual(before.camera);
  await caseLine(page).getByRole("button", { name: "Show toolbar" }).click();
  await page.waitForTimeout(500);
  const shown = await read();
  expect(shown.seen.drawing).toEqual([drawingBefore, hidden.seen.drawing[1], drawingBefore]);
  expect(shown.camera).toEqual(before.camera);
  if (viewport === 400) expect(before.line - hidden.line).toBeGreaterThan(20);
  // Never taller: hiding the toolbar never pushes the canvas down.
  expect(hidden.line).toBeLessThanOrEqual(before.line);
});

// The owner's rulings 1, 6 and 7: the toolbar stays one row; when its own width is narrow its words shorten
// (Strictness: …, Hide) and the Layout and Show captions go, the whole names kept; below about 900 it may wrap. The
// line is 1220 px, measured here (`toolbarCompact.ts`), not the rulings' estimate of 1132; Last change takes what is
// left and never wraps the row.
for (const look of ["dark", "govuk"] as const) {
  for (const [width, compact] of [[1440, false], [1240, false], [1220, false], [1219, true], [1131, true], [1024, true], [940, true], [912, true]] as const) {
    test(`at ${width} px of toolbar (${look}) the words are ${compact ? "short" : "whole"} and it is one row`, async ({ page }) => {
      await page.setViewportSize({ width: Math.max(width + 40, 1280), height: 800 });
      await open(page, `width=${width}`, look);
      const bar = tools(page);
      const strictness = bar.getByRole("button", { name: "Match strictness: Balanced" });
      const hide = bar.getByRole("button", { name: "Hide toolbar" });
      await expect(strictness).toBeVisible();
      // A width is the product's only in the product's face: where it could not load (a server that refuses
      // node_modules), say so rather than measure the fallback.
      expect(
        await page.evaluate(() => document.fonts.check(`12px ${getComputedStyle(document.documentElement).getPropertyValue("--ui")}`)),
        "the look's face did not load; is the server allowed to serve node_modules?",
      ).toBe(true);
      expect(Math.round((await bar.boundingBox())!.width)).toBe(width);
      await expect(strictness).toHaveText(compact ? "Strictness: Balanced ▾" : "Match strictness: Balanced ▾");
      await expect(hide).toHaveText(compact ? "Hide" : "Hide toolbar");
      await expect(bar.locator(".canvas-toolbar__label")).toHaveCount(compact ? 0 : 2);
      await expect(bar.getByRole("group", { name: "Layout" })).toHaveCount(1);
      await expect(bar.getByRole("group", { name: "Show" })).toHaveCount(1);
      // One row: no taller than the toolbar's height token (36 px) and its border; Hide toolbar its last control.
      expect((await bar.boundingBox())!.height).toBeLessThanOrEqual(37);
      const last = await bar.evaluate((el) => [...el.querySelectorAll("button, select")].at(-1)?.getAttribute("aria-label"));
      expect(last).toBe("Hide toolbar");
      // Ruling 14: hidden, Show toolbar on the case line says Show on the same narrow width, its name kept.
      await hide.click();
      const show = caseLine(page).getByRole("button", { name: "Show toolbar" });
      await expect(show).toHaveText(compact ? "Show" : "Show toolbar");
    });
  }
}

// case's merge tree (16 November 2026): the standard look's widths were measured before its web font arrived, in the
// fallback face, which is wider, so a toolbar that fits in Atkinson Hyperlegible Next wrapped. Five cases failed there on a
// cold server and passed here on a warm one. The harness now loads the product's faces before it draws; held here with
// the font files held back, as a cold or busy server serves them.
test("the widths are measured in the product's own face even when its font files are slow to arrive", async ({ page }) => {
  await page.route(/\.woff2?(\?.*)?$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await open(page, "width=1240");
  const bar = tools(page);
  await expect(bar.getByRole("button", { name: "Match strictness: Balanced" })).toHaveText("Match strictness: Balanced ▾");
  expect(await page.evaluate(() => document.fonts.check('12px "Atkinson Hyperlegible Next"'))).toBe(true);
  expect((await bar.boundingBox())!.height).toBeLessThanOrEqual(37);
});

test("under GOV.UK too: its face, a web face as well, is loaded before the narrowest one-row width is measured", async ({ page }) => {
  await page.route(/\.woff2?(\?.*)?$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await open(page, "width=912", "govuk");
  const bar = tools(page);
  await expect(bar.getByRole("button", { name: "Match strictness: Balanced" })).toHaveText("Strictness: Balanced ▾");
  expect(await page.evaluate(() => document.fonts.check(`12px ${getComputedStyle(document.documentElement).getPropertyValue("--ui")}`))).toBe(true);
  expect((await bar.boundingBox())!.height).toBeLessThanOrEqual(37);
});

// case's merge tree again: its node_modules is a link outside the worktree, which Vite refuses to serve, so the font files
// never arrived, `document.fonts.load` rejected, and the harnesses' top-level await left both pages blank (38 cases red).
// A face that cannot load must leave the page drawn, in its fallback face; a case that measures widths says so plainly.
for (const harness of ["glass-toolbar-harness.html", "harness.html?width=900"]) {
  test(`${harness.split("?")[0]} is drawn when the font files are refused`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route(/\.woff2?(\?.*)?$/, (route) => route.fulfill({ status: 403, body: "refused" }));
    await page.goto(`/keyboard/${harness}`);
    await expect(page.getByRole("application", { name: "Network canvas" })).toBeVisible();
    expect(errors).toEqual([]);
  });
}

// The owner's brief: Hide toolbar, Show toolbar and the strictness control meet the contrast floor in all three themes
// (the adviser's sketch had Show toolbar unreadable in the light theme).
for (const look of ["dark", "light", "govuk"] as const) {
  for (const [state, query] of [["shown, strictness open", "open=strictness"], ["hidden", ""]] as const) {
    test(`the toolbar's new controls, ${state}, pass axe and the contrast probe (${look})`, async ({ page }) => {
      await open(page, query, look);
      if (look === "light") await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
      if (look === "govuk") await expect(page.locator("html")).toHaveAttribute("data-brand", "govuk");
      if (state === "hidden") {
        await tools(page).getByRole("button", { name: "Hide toolbar" }).click();
        await expect(caseLine(page).getByRole("button", { name: "Show toolbar" })).toBeVisible();
      } else {
        await expect(page.getByRole("slider", { name: "Match strictness" })).toBeVisible();
      }
      const targets = state === "hidden" ? [".toolbar-toggle--show"] : [".toolbar-toggle", ".resolution-threshold-control"];
      let builder = new AxeBuilder({ page }).withTags(WCAG_TAGS);
      for (const target of targets) builder = builder.include(target);
      const results = await builder.analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      // Colour contrast was decided for every new control, not left undecided.
      expect(results.passes.some((rule) => rule.id === "color-contrast")).toBe(true);
      const contrast = await checkUndecidedContrast(page, results);
      expect(contrast.unlisted, "colour contrast axe left undecided").toEqual([]);
    });
  }
}
