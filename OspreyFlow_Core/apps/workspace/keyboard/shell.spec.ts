// The workspace shell by keyboard alone (ADR-097 step 1, rule 13). No `page.mouse`, no `.click()`.
import { expect, test } from "@playwright/test";

import { SHELL_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "SHELL_ACTIONS";

declare global {
  interface Window {
    __TOPBAR__?: { opened: string | null; browsed: boolean; signedOut: boolean; rail: string[] };
  }
}

test("/ outside a text field moves focus to search", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  await page.locator("body").focus();
  await page.keyboard.press("/");
  await expect(page.getByRole("combobox", { name: /Search entities/ })).toBeFocused();
  registerCovered(REGISTRY, "slash-moves-focus-to-search");
});

// ADR-128 decision 1 (B2): the search box's own "Add many from a list", opened, counted and cancelled.
test("add many from a list is opened from the search box, counted and cancelled, by keyboard", async ({ page }) => {
  // The harness's own `fetch` answers the count and records what was sent (a route would not see it).
  await page.goto("/keyboard/top-bar-harness.html");
  await page.getByRole("button", { name: "Add many from a list" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Add many from a list" })).toBeVisible();
  await page.getByRole("textbox", { name: /identifiers/i }).focus();
  await page.keyboard.type("Z1234ZZ, Z9999ZZ");
  await page.getByRole("button", { name: "Count" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "2 identifiers read." })).toHaveText(
    "2 identifiers read. 1 found. 1 matched nothing you can see. 0 repeated.",
  );
  await page.getByRole("button", { name: "Cancel" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Add many from a list" })).toBeHidden();
  const asked = await page.evaluate(() => (window as unknown as { __ADD_MANY__: string[] }).__ADD_MANY__);
  expect(asked).toHaveLength(1);
  expect(JSON.parse(asked[0]!)).toEqual({ identifiers: ["Z1234ZZ, Z9999ZZ"], confirm: false, with_links: false });
  registerCovered(REGISTRY, "add-many-from-the-search-box-by-keyboard");
});

// Rule 13 for the same dialog's other end: Add puts the nodes on the canvas through the shell's
// `applyStarterDelta` wiring (`GlobalSearch` -> `onApplyDelta` -> the working set), which the case
// above never reaches because it only counts and cancels.
test("add many from a list, added from the search box by keyboard, puts the nodes on the canvas", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html?canvas=1");
  const canvasNodes = () => page.evaluate(() => window.__TOPBAR_CANVAS__!.count());
  expect(await canvasNodes()).toBe(0);
  await page.getByRole("button", { name: "Add many from a list" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("textbox", { name: /identifiers/i }).focus();
  await page.keyboard.type("Z1234ZZ, Z9999ZZ");
  await page.getByRole("button", { name: "Count" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "2 identifiers read." })).toBeVisible();
  // Nothing is drawn until Add is pressed.
  expect(await canvasNodes()).toBe(0);
  await page.getByRole("button", { name: "Add", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "1 record is in the view." })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__TOPBAR_CANVAS__!.hasNode("n-listed-1"))).toBe(true);
  expect(await canvasNodes()).toBe(1);
  const asked = await page.evaluate(() => (window as unknown as { __ADD_MANY__: string[] }).__ADD_MANY__);
  expect(asked.map((body) => JSON.parse(body))).toEqual([
    { identifiers: ["Z1234ZZ, Z9999ZZ"], confirm: false, with_links: false },
    { identifiers: ["Z1234ZZ, Z9999ZZ"], confirm: true, with_links: false },
  ]);
  registerCovered(REGISTRY, "add-many-from-the-search-box-adds-to-the-canvas-by-keyboard");
});

// DESIGN.md v0.3 §5a (ADR-115 decision 9): the strip 20, the workspace's top bar 44, the rail 48 with
// 36px buttons.
test("the marking strip and the top bar take 20 and 44 pixels, and the rail 48 with 36px buttons", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/keyboard/top-bar-harness.html");
  const strip = (await page.getByRole("note", { name: "Protective marking" }).boundingBox())!;
  const bar = (await page.locator("header.top-bar").boundingBox())!;
  const railBox = (await page.getByRole("navigation", { name: "Workspace" }).boundingBox())!;
  expect(Math.round(strip.height)).toBe(20);
  expect(Math.round(bar.height)).toBe(44);
  expect(Math.round(railBox.width)).toBe(48);
  const item = (await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Cases" }).boundingBox())!;
  expect([Math.round(item.width), Math.round(item.height)]).toEqual([36, 36]);
  await expect(page.getByRole("note", { name: "Protective marking" })).toHaveText("OFFICIAL");
});

test("each rail entry is reached and pressed by keyboard", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  for (const name of ["Cases", "Monitoring", "Ownership", "History", "Explore", "Questions", "Dashboards"]) {
    await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name }).focus();
    await page.keyboard.press("Enter");
  }
  expect(await page.evaluate(() => window.__TOPBAR__?.rail)).toEqual(["cases", "alerts", "ownership", "history", "explore", "questions", "dashboards"]);
  // The owner's answer of 1 November 2026: watches are in Monitoring's Watches tab, not the rail.
  await expect(page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Watches" })).toHaveCount(0);
  registerCovered(REGISTRY, "rail-entries-by-keyboard");
});

test("each view is chosen by keyboard, Reports among them", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  for (const name of ["Map", "Reports", "Graph"]) {
    await page.getByRole("button", { name, exact: true }).focus();
    await page.keyboard.press("Enter");
  }
  expect(await page.evaluate(() => window.__TOPBAR__?.views)).toEqual(["map", "reports", "graph"]);
  registerCovered(REGISTRY, "views-chosen-by-keyboard");
});

test("the rail shows its names, and hides them again, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  const rail = page.getByRole("navigation", { name: "Workspace" });
  await rail.getByRole("button", { name: "Show names" }).focus();
  await page.keyboard.press("Enter");
  await expect(rail.getByText("History")).toBeVisible();
  await expect(rail.getByRole("button", { name: "Hide names" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(rail.getByText("History")).toHaveCount(0);
  registerCovered(REGISTRY, "rail-shows-and-hides-names-by-keyboard");
});

// ADR-115 E6: Help at the rail's foot, by keyboard (it reopens the workspace's welcome panel).
test("the rail's Help is reached and pressed by keyboard", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Help" }).focus();
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => window.__TOPBAR__?.help)).toBe(1);
  registerCovered(REGISTRY, "help-from-the-rail-by-keyboard");
});

// ADR-145 decisions 1 and 3 (rule 13): the place switcher, by keyboard, under both brands — in the
// bar, and inside the GOV.UK header — listing only the places the rights open.
for (const brand of ["ospreyflow", "govuk"] as const) {
  test(`${brand}: the place switcher lists only the places the rights open, and moves between them by keyboard`, async ({ page }) => {
    await page.goto(`/keyboard/places-harness.html?brand=${brand}`);
    const places = page.getByRole("navigation", { name: "Places" });
    await expect(places.getByRole("button")).toHaveText(["The Glass", "Ingest Studio", "Admin"]);
    if (brand === "govuk") await expect(page.locator(".govuk-header").getByRole("navigation", { name: "Places" })).toHaveCount(1);
    await expect(places.getByRole("button", { name: "The Glass" })).toHaveAttribute("aria-current", "page");
    await places.getByRole("button", { name: "Ingest Studio" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "You are in the Ingest Studio" })).toBeVisible();
    await expect(places.getByRole("button", { name: "Ingest Studio" })).toHaveAttribute("aria-current", "page");
    await places.getByRole("button", { name: "Admin" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "You are in Admin" })).toBeVisible();
    expect(await page.evaluate(() => window.__PLACES__?.chosen)).toEqual(["ingest", "admin"]);
    registerCovered(REGISTRY, "switch-place-by-keyboard");
  });
}

test("an analyst's switcher offers the Glass alone", async ({ page }) => {
  await page.goto("/keyboard/places-harness.html?rights=investigate,read_reports");
  await expect(page.getByRole("navigation", { name: "Places" }).getByRole("button")).toHaveText(["The Glass"]);
  await expect(page.getByRole("button", { name: /in the Ingest Studio/ })).toHaveCount(0);
});

// ADR-145 decision 2 (rule 13): the banner's cross-link, there and back, keeping the case.
test("the banner's cross-link goes to the Studio and back to the same case by keyboard", async ({ page }) => {
  await page.goto("/keyboard/places-harness.html?rights=investigate,edit_pipelines");
  await page.getByRole("button", { name: "Open Prison intel in the Ingest Studio ↗" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "You are in the Ingest Studio" })).toContainText("Dataset Prison intel");
  await page.getByRole("button", { name: "← Back to case Kestrel in the Glass" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "You are in the Glass" })).toBeVisible();
  await expect(page.getByText("glass on case kestrel")).toBeVisible();
  expect(await page.evaluate(() => window.__PLACES__?.crossed)).toEqual(["to-studio", "to-glass"]);
  registerCovered(REGISTRY, "banner-cross-link-by-keyboard");
});

// ADR-145 decision 1 (rule 13): Home's cards are the switcher's list, reached by Tab and opened by
// Enter; a place the rights do not open has no card at all.
test("Home's cards are the places the rights open, each reached by Tab and opened by keyboard", async ({ page }) => {
  await page.route("**/*/v1/**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.goto("/keyboard/start-harness.html?rights=investigate,edit_pipelines");
  await expect(page.getByRole("region", { name: "Admin" })).toHaveCount(0);
  const reached: string[] = [];
  for (let i = 0; i < 40 && reached.length < 2; i++) {
    await page.keyboard.press("Tab");
    const name = await page.evaluate(() => document.activeElement?.textContent ?? "");
    if (/^Open /.test(name) && !reached.includes(name)) reached.push(name);
  }
  expect(reached.map((n) => n.replace(/[GIA]$/, "").trim())).toEqual(["Open The Glass", "Open Ingest Studio"]);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Choose the case to load into" })).toBeVisible();
  registerCovered(REGISTRY, "home-place-cards-by-keyboard");
});

// ADR-132: the skip link, the one keyboard action the deployment brand adds, under both brands
// (`keyboard/shell-harness.tsx`, the real `BrandFrame`). It is the first Tab stop, shows itself on
// focus at a usable size, and Enter moves focus to the main content; under GOV.UK the header, the
// service name, the Glass and the footer follow in that order.
for (const brand of ["ospreyflow", "govuk"] as const) {
  test(`${brand}: the skip link is the first Tab stop, visible on focus, and Enter moves focus to the main content`, async ({ page }) => {
    await page.goto("/keyboard/shell-harness.html?brand=" + brand);
    await page.getByRole("link", { name: "Skip to main content" }).waitFor({ state: "attached" });
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      const r = el?.getBoundingClientRect();
      return { text: el?.textContent?.trim() ?? "", w: r?.width ?? 0, h: r?.height ?? 0 };
    });
    expect(focused.text).toBe("Skip to main content");
    expect(focused.w).toBeGreaterThanOrEqual(24);
    expect(focused.h).toBeGreaterThanOrEqual(24);
    await page.keyboard.press("Enter");
    expect(await page.evaluate(() => document.activeElement?.id)).toBe("main-content");
    registerCovered(REGISTRY, "skip-to-main-content-by-keyboard");
  });
}

// ADR-132 Amendment 5 (4 November 2026): no service-name band, so the Glass follows the header.
test("govuk: the header, the Glass and the footer are reached by Tab in that order", async ({ page }) => {
  await page.goto("/keyboard/shell-harness.html?brand=govuk");
  await page.getByRole("link", { name: "Skip to main content" }).waitFor({ state: "attached" });
  const names: string[] = [];
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    const name = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      return el?.getAttribute("aria-label") ?? el?.textContent?.trim() ?? "";
    });
    names.push(name);
    if (name === "Cookies") break;
  }
  expect(names[0]).toBe("Skip to main content");
  const at = (match: (n: string) => boolean, from: number) => names.findIndex((n, i) => i >= from && match(n));
  const header = at((n) => n.includes("GOV.UK"), 1);
  expect(header).toBeGreaterThan(0);
  expect(names).not.toContain("Prison Intelligence");
  const glass = at((n) => n === "Workspace control", header + 1);
  expect(glass).toBeGreaterThan(header);
  const accessibility = at((n) => n === "Accessibility statement", glass + 1);
  expect(accessibility).toBeGreaterThan(glass);
  const cookies = at((n) => n === "Cookies", accessibility + 1);
  expect(cookies).toBeGreaterThan(accessibility);
});

test("every registered shell action has its own proving test case above", () => {
  assertAllCovered("SHELL_ACTIONS", SHELL_ACTIONS);
});

// ADR-132 Amendment 4: GOV.UK's own chrome keeps GOV.UK's link styling. The Glass gives every link a
// bottom border (`tokens.css`), which drew a rule under the logo at rest, where GOV.UK draws none
// (found 1 November 2026 against www.gov.uk). The service name it also checked is gone (Amendment 5).
test("govuk: the GOV.UK logo is not underlined at rest", async ({ page }) => {
  await page.goto("/keyboard/shell-harness.html?brand=govuk");
  const rules = await page.evaluate(() =>
    [".govuk-header__homepage-link"].map((selector) => {
      const style = getComputedStyle(document.querySelector(selector)!);
      return { selector, border: style.borderBottomStyle === "none" ? "0px" : style.borderBottomWidth, line: style.textDecorationLine };
    }),
  );
  for (const rule of rules) expect(rule, rule.selector).toEqual({ selector: rule.selector, border: "0px", line: "none" });
});

// ADR-132 Amendment 5: no service-name band in the real page under GOV.UK, and the title names the service.
test("govuk: no service-name band is drawn, and the page title names the service", async ({ page }) => {
  await page.goto("/keyboard/shell-harness.html?brand=govuk");
  await page.locator(".govuk-header").waitFor();
  await expect(page.locator(".govuk-service-navigation")).toHaveCount(0);
  await expect(page).toHaveTitle("Prison Intelligence – GOV.UK");
});

// ADR-132 Amendment 4: under GOV.UK the sign-in and start pages sit in GOV.UK's width container (960px,
// gutters of 30px, 15px on a phone), so their content starts on the logo's left edge and ends inside the
// header's right edge, as every GOV.UK page does. They had their own wider rows (found 1 November 2026).
const GOVUK_PAGES = [
  { name: "sign-in", url: "/keyboard/sign-in-harness.html?brand=govuk", first: ".welcome-hero__title", rows: [".welcome-header", ".welcome-hero", ".welcome-footer"] },
  { name: "start", url: "/keyboard/start-harness.html?brand=govuk", first: ".home-greeting h1", rows: [".home-header", ".home-main"] },
] as const;
for (const shown of GOVUK_PAGES) {
  for (const width of [1440, 800, 375]) {
    test(`govuk: the ${shown.name} page's content lines up with the GOV.UK header at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(shown.url);
      await page.locator(shown.first).waitFor();
      const edges = await page.evaluate(
        ({ first, rows }) => {
          const box = (selector: string) => document.querySelector(selector)?.getBoundingClientRect() ?? null;
          const container = box(".govuk-header__container")!;
          const style = getComputedStyle(document.querySelector(".govuk-header__container")!);
          return {
            left: container.left + parseFloat(style.paddingLeft),
            right: container.right - parseFloat(style.paddingRight),
            first: box(first)!.left,
            rows: rows.map((row) => {
              const element = document.querySelector(row);
              if (!element) return null;
              const r = element.getBoundingClientRect();
              const s = getComputedStyle(element);
              return { row, left: r.left + parseFloat(s.paddingLeft), right: r.right - parseFloat(s.paddingRight) };
            }).filter((r) => r !== null),
          };
        },
        { first: shown.first, rows: [...shown.rows] },
      );
      expect(Math.abs(edges.first - edges.left), `${shown.first} starts on the logo's edge`).toBeLessThanOrEqual(1);
      for (const row of edges.rows) {
        expect(Math.abs(row.left - edges.left), `${row.row}'s left`).toBeLessThanOrEqual(1);
        expect(Math.abs(row.right - edges.right), `${row.row}'s right`).toBeLessThanOrEqual(1);
      }
    });
  }
}
