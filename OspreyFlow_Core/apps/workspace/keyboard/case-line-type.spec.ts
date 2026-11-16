// The case line on one type size (the owner's word, 15 November 2026): the row under the top bar, every part of it
// (the place, "Case", the case switcher, Saved views (n), the open saved view and its Details and way back, "reads …"
// and the cross-link; ADR-145 Amendment 19), on the
// top bar's own font size and line height, the place still its bold heading; one line high wherever the top bar is.
// Measured, never judged by eye: the computed size and line height of each part against the top bar's, in the GOV.UK
// look and the standard look's dark and light.
import { expect, test, type Page } from "@playwright/test";

const LOOKS = [["ospreyflow", "dark"], ["ospreyflow", "light"], ["govuk", "light"]] as const;

async function open(page: Page, brand: string, theme: string, width = 1440, long = false): Promise<void> {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`/keyboard/places-harness.html?openview=1${long ? "&long=1" : ""}${brand === "govuk" ? "&brand=govuk" : ""}`);
  await page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);
  await expect(page.getByRole("region", { name: "You are in the Glass" }).getByText(/^reads /)).toBeVisible();
}

/** Each part of the row with its computed type, and the top bar's. */
async function measure(page: Page) {
  return page.evaluate(() => {
    const type = (e: Element) => {
      const cs = getComputedStyle(e);
      return { size: cs.fontSize, line: cs.lineHeight, weight: cs.fontWeight };
    };
    const region = document.querySelector('[aria-labelledby="context-banner-title"]')!;
    const reads = [...region.querySelectorAll("span")].find((s) => s.textContent?.startsWith("reads "));
    const parts: Record<string, Element | null | undefined> = {
      place: region.querySelector("#context-banner-title"),
      case: region.querySelector(".context-banner__label"),
      switcher: region.querySelector(".menu-button--case"),
      "switcher's words": region.querySelector(".menu-button--case .menu-button__label"),
      "saved views": region.querySelector("[data-saved-views-button]"),
      "open saved view": region.querySelector(".context-banner__saved-view"),
      "its Details": [...region.querySelectorAll("button")].find((b) => b.getAttribute("aria-controls") === "saved-view-details"),
      "its way back": region.querySelector(".context-banner__whole"),
      reads,
      "cross-link": region.querySelector(".context-banner__cross"),
    };
    const missing = Object.entries(parts).filter(([, e]) => !e).map(([name]) => name);
    return {
      bar: type(document.querySelector("header.top-bar")!),
      missing,
      parts: Object.fromEntries(Object.entries(parts).filter(([, e]) => e).map(([name, e]) => [name, type(e!)])),
    };
  });
}

for (const [brand, theme] of LOOKS) {
  test(`${brand} ${theme}: every part of the case line is on the top bar's font size and line height, the place bold`, async ({ page }) => {
    await open(page, brand, theme);
    const { bar, missing, parts } = await measure(page);
    expect(missing, "parts of the row not found").toEqual([]);
    const off = Object.entries(parts)
      .filter(([, t]) => t.size !== bar.size || t.line !== bar.line)
      .map(([name, t]) => `${name}: ${t.size}/${t.line} (the bar ${bar.size}/${bar.line})`);
    expect(off, "parts of the row off the top bar's type").toEqual([]);
    expect(Number(parts.place!.weight), "the place's heading bold").toBeGreaterThanOrEqual(600);
  });

  for (const [width, long] of [[1440, false], [1280, false], [1024, false], [1440, true], [1280, true], [1024, true]] as const) {
    test(`${brand} ${theme}: at ${width} wide${long ? ", the long names," : ""} the case line is one line high where the top bar is`, async ({ page }) => {
      await open(page, brand, theme, width, long);
      const rows = await page.evaluate(() => {
        const lines = (container: Element) => {
          const boxes = [...container.children].map((c) => c.getBoundingClientRect()).filter((b) => b.width > 0 && b.height > 0);
          const bottom = Math.min(...boxes.map((b) => b.bottom));
          return boxes.some((b) => b.top >= bottom - 0.5) ? 2 : 1;
        };
        const region = document.querySelector('[aria-labelledby="context-banner-title"]')!;
        const row = region.querySelector(".govuk-notification-banner__content") ?? region;
        return { bar: lines(document.querySelector("header.top-bar")!), row: lines(row) };
      });
      test.skip(rows.bar !== 1, "the top bar itself is on two lines here");
      expect(rows.row, "the case line's lines").toBe(1);
    });
  }
}

// (a) When the line runs out of room, the cross-link takes its short words first, measured; with room, its full words.
for (const [brand, theme] of LOOKS) {
  test(`${brand} ${theme}: the cross-link keeps its full words with room and takes its short ones without, again on widening`, async ({ page }) => {
    await open(page, brand, theme, 1440);
    const region = page.getByRole("region", { name: "You are in the Glass" });
    const full = region.getByRole("button", { name: "Open this case's data in the Ingest Studio ↗" });
    const short = region.getByRole("button", { name: "Open in the Ingest Studio ↗", exact: true });
    await expect(full).toBeVisible();
    await page.setViewportSize({ width: 1024, height: 900 });
    if (brand !== "govuk") await expect(short).toBeVisible();
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(full).toBeVisible();
  });
}

// (b) With the long names at 1024 (ADR-145 Amendment 19 decision 4, the owner's ruling 10): after the cross-link's short
// words, "reads …" goes out of sight (kept in the page, what a screen reader reads, and in its title), then the open
// saved view's name, the case switcher and "You are in the Glass" give way in turn, as far as the line needs and no
// further; *Saved views (n)*, the tag, *Details* and *Back to the whole case* are never cut. Whole words stay in the page
// and in each title.
for (const [brand, theme] of LOOKS) {
  test(`${brand} ${theme}: the long names give way in the ruled order, their whole words kept in the page and the title`, async ({ page }) => {
    await open(page, brand, theme, 1024, true);
    const region = page.getByRole("region", { name: "You are in the Glass" });
    const view = "Saved view: Every payment between the three Ledger accounts in March and April";
    const reads = "reads Prison Intelligence Dataset (synthetic) and the Ledger visits log";
    const named = region.locator(".context-banner__saved-view");
    const read = region.locator(".context-banner__reads");
    await expect(named).toHaveText(view);
    await expect(named).toHaveAttribute("title", view);
    await expect(read).toHaveText(reads);
    await expect(read).toHaveAttribute("title", reads);
    // "reads …" first: out of sight, kept for a screen reader.
    await expect(read).toHaveClass(/visually-hidden/);
    // Never cut: Saved views (n), the tag, Details and the way back.
    const never = await region.evaluate((element) =>
      [element.querySelector("[data-saved-views-button]"), element.querySelector(".context-banner__tag"),
        [...element.querySelectorAll("button")].find((b) => b.getAttribute("aria-controls") === "saved-view-details"),
        element.querySelector(".context-banner__whole")]
        .filter((e): e is Element => e !== null && e !== undefined)
        .filter((e) => (e as HTMLElement).scrollWidth > (e as HTMLElement).clientWidth + 1 || e.closest(".visually-hidden"))
        .map((e) => e.textContent ?? ""),
    );  // prettier-ignore
    expect(never, "parts the fold must never cut").toEqual([]);
    // And no item of the row itself is drawn narrower than what it holds, but those the fold may cut.
    const clipped = await region.evaluate((element) => {
      const row = element.querySelector(".govuk-notification-banner__content") ?? element;
      return [...row.children]
        .filter((c) => !c.classList.contains("context-banner__fit") && !c.classList.contains("menu") && !c.classList.contains("visually-hidden") && c.scrollWidth > c.clientWidth + 1)
        .map((c) => (c.textContent ?? "").slice(0, 40));
    });
    expect(clipped, "items of the row clipped").toEqual([]);
  });
}
