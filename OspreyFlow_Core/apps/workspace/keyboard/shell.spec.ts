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
  // ADR-145 Amendment 12: the rail keeps Cases, Explore, Ask & Chat (Questions renamed) and Dashboards.
  // Monitoring is no longer the Glass's at all: Rules and Monitoring is a place of its own (ADR-146
  // decision 2).
  for (const name of ["Cases", "Explore", "Ask & Chat", "Dashboards"]) {
    // Exact: "Explore" is also the start of "Explore Details" (ADR-145 Amendment 12).
    await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name, exact: true }).focus();
    await page.keyboard.press("Enter");
  }
  expect(await page.evaluate(() => window.__TOPBAR__?.rail)).toEqual(["cases", "explore", "questions", "dashboards"]);
  // Watches are with the rules in Rules and Monitoring (ADR-146 decision 4), not the rail.
  await expect(page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Watches" })).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: /Monitoring/ })).toHaveCount(0);
  registerCovered(REGISTRY, "rail-entries-by-keyboard");
});

// ADR-145 Amendment 12 (rule 13): each destination under the rail's ⋯ Explore Details, in its order,
// opened and chosen by keyboard, and Escape closes the menu back onto it.
test("each destination under the rail's Explore Details is reached and chosen by keyboard", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  const rail = page.getByRole("navigation", { name: "Workspace" });
  for (const name of ["History", "Ownership", "Connection strength"]) {
    await rail.getByRole("button", { name: "Explore Details" }).focus();
    await page.keyboard.press("Enter");
    const menu = rail.getByRole("group", { name: "Explore Details" });
    await expect(menu.getByRole("button")).toHaveText(["History", "Ownership", "Connection strength"]);
    await menu.getByRole("button", { name }).focus();
    await page.keyboard.press("Enter");
    await expect(rail.getByRole("group", { name: "Explore Details" })).toHaveCount(0);
  }
  expect(await page.evaluate(() => window.__TOPBAR__?.rail)).toEqual(["history", "ownership", "strength"]);
  await rail.getByRole("button", { name: "Explore Details" }).focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Escape");
  await expect(rail.getByRole("group", { name: "Explore Details" })).toHaveCount(0);
  await expect(rail.getByRole("button", { name: "Explore Details" })).toBeFocused();
  registerCovered(REGISTRY, "rail-more-by-keyboard");
});

test("each view is chosen by keyboard, Matrix and Figures under More views", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  await page.getByRole("button", { name: "Map", exact: true }).focus();
  await page.keyboard.press("Enter");
  for (const name of ["Figures", "Matrix"]) {
    await page.getByRole("button", { name: "More views" }).focus();
    await page.keyboard.press("Enter");
    await page.getByRole("group", { name: "More views" }).getByRole("button", { name }).focus();
    await page.keyboard.press("Enter");
  }
  await page.getByRole("button", { name: "Graph", exact: true }).focus();
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => window.__TOPBAR__?.views)).toEqual(["map", "reports", "matrix", "graph"]);
  registerCovered(REGISTRY, "views-chosen-by-keyboard");
  registerCovered(REGISTRY, "more-views-by-keyboard");
});

// ADR-145 decision 4 (Amendment 2): the column opens with the Inspector only, the other panels folded
// beneath it in their order, each opened by one keypress on its name.
test("the column opens with the Inspector only, and each folded panel opens with one keypress", async ({ page }) => {
  await page.goto("/keyboard/panel-frames-harness.html?defaults=1");
  const header = (name: string) => page.getByRole("button", { name, exact: true });
  await expect(header("Inspector")).toHaveAttribute("aria-expanded", "true");
  for (const name of ["Metrics", "Query builder"]) await expect(header(name)).toHaveAttribute("aria-expanded", "false");
  for (const name of ["Metrics", "Query builder"]) {
    await header(name).focus();
    await page.keyboard.press("Enter");
    await expect(header(name)).toHaveAttribute("aria-expanded", "true");
  }
  registerCovered(REGISTRY, "open-a-folded-panel-by-keyboard");
});

test("the rail shows its names, and hides them again, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  const rail = page.getByRole("navigation", { name: "Workspace" });
  await rail.getByRole("button", { name: "Show names" }).focus();
  await page.keyboard.press("Enter");
  await expect(rail.getByText("Explore", { exact: true })).toBeVisible();
  await expect(rail.getByRole("button", { name: "Hide names" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(rail.getByText("Explore", { exact: true })).toHaveCount(0);
  registerCovered(REGISTRY, "rail-shows-and-hides-names-by-keyboard");
});

// ADR-115 E6 and ADR-145 Amendment 12 (rule 13): Help at the rail's foot, by keyboard, opens the keys
// panel and a second press closes it; `?` does the same, and Esc closes it from inside; its user guide
// link is reached by Tab and activated. (That it shows over every view of the real App is
// `App.help.test.tsx`'s.)
test("the rail's Help opens and closes the keys panel by keyboard, as ? and Esc do", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  const help = page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Help" });
  const panel = page.getByRole("dialog", { name: "Welcome back" });
  await help.focus();
  await page.keyboard.press("Enter");
  await expect(panel).toBeVisible();
  await help.focus();
  await page.keyboard.press("Enter");
  await expect(panel).toHaveCount(0);
  expect(await page.evaluate(() => window.__TOPBAR__?.help)).toBe(2);
  // Opened by Help it takes focus, so Esc closes it straight away.
  await help.focus();
  await page.keyboard.press("Enter");
  await expect(panel).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await page.locator("body").focus();
  await page.keyboard.press("?");
  await expect(panel).toBeVisible();
  await page.keyboard.press("?");
  await expect(panel).toHaveCount(0);
  await page.keyboard.press("?");
  await panel.getByRole("link", { name: "Read the user guide (PDF)" }).focus();
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => window.__TOPBAR__?.guide)).toBe(1);
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  registerCovered(REGISTRY, "help-from-the-rail-by-keyboard");
});

// ADR-145 decisions 1 and 3 and Amendment 4 (rule 13): the place switcher, by keyboard, under both
// brands — in the bar, and inside the GOV.UK header — listing only the places the rights open, Rules
// and Monitoring the fourth (ADR-146 decision 2).
for (const brand of ["ospreyflow", "govuk"] as const) {
  test(`${brand}: the place switcher lists only the places the rights open, and moves between them by keyboard`, async ({ page }) => {
    await page.goto(`/keyboard/places-harness.html?brand=${brand}&rights=investigate,edit_pipelines,triage_alerts,read_alert_queue,manage_people`);
    const places = page.getByRole("navigation", { name: "Places" });
    await expect(places.getByRole("button")).toHaveText(["The Glass", "Ingest Studio", "Rules and Monitoring", "Admin"]);
    if (brand === "govuk") await expect(page.locator(".govuk-header").getByRole("navigation", { name: "Places" })).toHaveCount(1);
    await expect(places.getByRole("button", { name: "The Glass" })).toHaveAttribute("aria-current", "page");
    await places.getByRole("button", { name: "Ingest Studio" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "You are in the Ingest Studio" })).toBeVisible();
    await expect(places.getByRole("button", { name: "Ingest Studio" })).toHaveAttribute("aria-current", "page");
    await places.getByRole("button", { name: "Rules and Monitoring" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "You are in Rules and Monitoring" })).toBeVisible();
    await expect(places.getByRole("button", { name: "Rules and Monitoring" })).toHaveAttribute("aria-current", "page");
    await places.getByRole("button", { name: "Admin" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "You are in Admin" })).toBeVisible();
    expect(await page.evaluate(() => window.__PLACES__?.chosen)).toEqual(["ingest", "rules", "admin"]);
    registerCovered(REGISTRY, "switch-place-by-keyboard");
    registerCovered(REGISTRY, "switch-to-rules-and-monitoring-by-keyboard");
  });
}

test("a reader's switcher offers the Glass alone", async ({ page }) => {
  await page.goto("/keyboard/places-harness.html?rights=investigate,read_reports,read_alert_queue");
  await expect(page.getByRole("navigation", { name: "Places" }).getByRole("button")).toHaveText(["The Glass"]);
  await expect(page.getByRole("button", { name: /in the Ingest Studio/ })).toHaveCount(0);
});

// ADR-146 decision 2: the open-alert count rides on the switcher's Rules and Monitoring, its count in
// its name, and is gone from the Glass's banner; from Rules and Monitoring the switcher returns to the
// Glass's view that was open.
test("Rules and Monitoring carries the count, and the Glass is returned to its last view by keyboard", async ({ page }) => {
  await page.goto("/keyboard/places-harness.html?badge=1&rights=investigate,triage_alerts,read_alert_queue");
  const places = page.getByRole("navigation", { name: "Places" });
  await expect(places.getByRole("button", { name: "Rules and Monitoring 3 open" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "In the Glass" }).getByRole("button", { name: /Monitoring/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Map", exact: true }).focus();
  await page.keyboard.press("Enter");
  await places.getByRole("button", { name: "Rules and Monitoring 3 open" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("rules, alerts, on case kestrel")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Workspace" })).toHaveCount(0);
  await places.getByRole("button", { name: "The Glass" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("glass, map, on case kestrel")).toBeVisible();
  registerCovered(REGISTRY, "back-to-the-glass-from-rules-and-monitoring-by-keyboard");
});

// ADR-145 decision 2 (rule 13): the banner's cross-link, there and back, keeping the case and the view.
test("the banner's cross-link goes to the Studio and back to the same case and view by keyboard", async ({ page }) => {
  await page.goto("/keyboard/places-harness.html?rights=investigate,edit_pipelines");
  await page.getByRole("button", { name: "Map", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("glass, map, on case kestrel")).toBeVisible();
  await page.getByRole("button", { name: "Open this case's data in the Ingest Studio ↗" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("ingest, ingest, on case kestrel")).toBeVisible();
  // Another case, chosen in the Studio: the real `openCase`, which reloads the page.
  await page.getByRole("button", { name: "Case: Kestrel" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("ingest, ingest, on case harrier")).toBeVisible();
  await page.getByRole("button", { name: "← Back to case Harrier in the Glass" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "You are in the Glass" })).toBeVisible();
  await expect(page.getByText("glass, map, on case harrier")).toBeVisible();
  expect(await page.evaluate(() => window.__PLACES__?.crossed)).toEqual(["to-glass"]);
  registerCovered(REGISTRY, "banner-cross-link-by-keyboard");
});

// Messages is drawn for one node, which a reload does not keep: crossing from it, changing case in the
// Studio and coming Back returns to the view open before Messages, not to an empty Messages.
test("from Messages, the cross-link and a case change in the Studio come Back to the view before it", async ({ page }) => {
  await page.goto("/keyboard/places-harness.html?rights=investigate,edit_pipelines");
  for (const name of ["Map", "Messages"]) {
    await page.getByRole("button", { name, exact: true }).focus();
    await page.keyboard.press("Enter");
  }
  await expect(page.getByText("glass, dossier, on case kestrel")).toBeVisible();
  await page.getByRole("button", { name: "Open this case's data in the Ingest Studio ↗" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Case: Kestrel" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("ingest, ingest, on case harrier")).toBeVisible();
  await page.getByRole("button", { name: "← Back to case Harrier in the Glass" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("glass, map, on case harrier")).toBeVisible();
});

// ADR-145 decision 1 and Amendment 13 (rule 13): the Glass's mode toggle in the banner, Graph · Drawing board,
// each chosen by keyboard, and the open mode's one-line note the region's own, read with it (its
// description). Monitoring left for Rules and Monitoring (ADR-146 decision 2).
test("the banner's toggle is Graph and Drawing board, each chosen by keyboard, its note read with the region", async ({ page }) => {
  await page.goto("/keyboard/places-harness.html?rights=investigate,read_alert_queue,triage_alerts");
  const region = page.getByRole("region", { name: "You are in the Glass" });
  const sections = region.getByRole("navigation", { name: "In the Glass" });
  await expect(sections.getByRole("button")).toHaveText(["Graph", "Drawing board"]);
  const GRAPH = "Graph: the case's data. Saved views are under Views or Cases.";
  const BOARD = "Drawing board: your sketch; it does not change the case's data.";
  await expect(region).toHaveAccessibleDescription(GRAPH);
  await expect(region).toContainText(GRAPH);
  await page.getByRole("button", { name: "Map", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("glass, map, on case kestrel")).toBeVisible();
  await sections.getByRole("button", { name: "Drawing board" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("glass, boards, on case kestrel")).toBeVisible();
  await expect(sections.getByRole("button", { name: "Drawing board" })).toHaveAttribute("aria-current", "page");
  await expect(region).toHaveAccessibleDescription(BOARD);
  await expect(region).not.toContainText(GRAPH);
  await sections.getByRole("button", { name: "Graph" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("glass, graph, on case kestrel")).toBeVisible();
  await expect(sections.getByRole("button", { name: "Graph" })).toHaveAttribute("aria-current", "page");
  await expect(region).toHaveAccessibleDescription(GRAPH);
  registerCovered(REGISTRY, "banner-sections-by-keyboard");
});

// ADR-145 Amendment 14 decision 3 (the owner's screen fixes, 13 November 2026: one place, one marker), in the
// dark, light and GOV.UK looks. A place of the rail's own chosen by keyboard from Explore Details is the one thing
// marked, on the trigger; the banner's Graph is not current there and its note is not said. The owner's own case:
// the Cases panel opened over Dashboards leaves Dashboards the one marker, Cases expanded, and a second Enter
// closes it.
for (const [brand, theme] of [["ospreyflow", "dark"], ["ospreyflow", "light"], ["govuk", "light"]] as const) {
  const marked = '[aria-pressed="true"], [data-current="true"]';

  test(`${brand} ${theme}: a rail place chosen by keyboard is the only marker: no Glass mode current, no mode's note`, async ({ page }) => {
    await page.goto(`/keyboard/places-harness.html?rights=investigate,read_alert_queue,triage_alerts&brand=${brand}`);
    await page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);
    const region = page.getByRole("region", { name: "You are in the Glass" });
    const sections = region.getByRole("navigation", { name: "In the Glass" });
    const rail = page.getByRole("navigation", { name: "Workspace" });
    await rail.getByRole("button", { name: "Explore Details" }).focus();
    await page.keyboard.press("Enter");
    await page.getByRole("group", { name: "Explore Details" }).getByRole("button", { name: "Connection strength" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("glass, strength, on case kestrel")).toBeVisible();
    for (const name of ["Graph", "Drawing board"]) await expect(sections.getByRole("button", { name })).not.toHaveAttribute("aria-current", "page");
    await expect(region).not.toContainText("Graph: the case's data");
    await expect(region).not.toHaveAttribute("aria-describedby");
    await expect(rail.locator(marked)).toHaveCount(1);
    await expect(rail.locator(marked)).toHaveAccessibleName("Explore Details, Connection strength open");
    await sections.getByRole("button", { name: "Graph" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("glass, graph, on case kestrel")).toBeVisible();
    await expect(sections.getByRole("button", { name: "Graph" })).toHaveAttribute("aria-current", "page");
    await expect(region).toHaveAccessibleDescription("Graph: the case's data. Saved views are under Views or Cases.");
    await expect(rail.locator(marked)).toHaveCount(0);
  });

  test(`${brand} ${theme}: the Cases panel opened over Dashboards leaves Dashboards the one marker, Cases expanded`, async ({ page }) => {
    await page.goto(`/keyboard/places-harness.html?rights=investigate,read_alert_queue,triage_alerts&brand=${brand}`);
    await page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);
    const rail = page.getByRole("navigation", { name: "Workspace" });
    await rail.getByRole("button", { name: "Dashboards" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("glass, dashboards, on case kestrel")).toBeVisible();
    const cases = rail.getByRole("button", { name: "Cases" });
    await cases.focus();
    await page.keyboard.press("Enter");
    await expect(cases).toHaveAttribute("aria-expanded", "true");
    await expect(rail.locator(marked)).toHaveCount(1);
    await expect(rail.locator(marked)).toHaveAccessibleName("Dashboards");
    await expect(page.getByRole("region", { name: "You are in the Glass" })).not.toContainText("Graph: the case's data");
    await page.keyboard.press("Enter");
    await expect(cases).toHaveAttribute("aria-expanded", "false");
  });
}

// ADR-146 decision 6 (rule 13): Home's Needs your attention opens the alert, not its case.
test("an alert on Home, focused, is opened at its address by Enter", async ({ page }) => {
  await page.route("**/*/v1/**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.goto("/keyboard/start-harness.html?figures=1&rights=investigate,triage_alerts,read_alert_queue");
  const row = page.getByRole("region", { name: "Needs your attention" }).getByRole("button", { name: /KYC screening alert/ });
  await row.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__START__)).toEqual({ opened: null, alert: "al-14" });
  registerCovered(REGISTRY, "open-an-alert-from-home-by-keyboard");
});

// ADR-146 decision 2 (rule 13): Rules and Monitoring's card on Home, by its key R, and with no case
// open, a case chosen for it opens on the place (`openCaseOnRules`, `/rules?investigation=…`).
test("Rules and Monitoring's card opens by its key, and a case is chosen for it by keyboard", async ({ page }) => {
  const CASES = [{ id: "c1", name: "Operation Ledger (synthetic demo)", level: "author", created_at: "2026-10-01T09:00:00Z", created_by: "a" }];
  await page.route("**/*/v1/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(new URL(route.request().url()).pathname === "/v1/investigations" ? CASES : []) }),
  );
  await page.goto("/keyboard/start-harness.html?rights=investigate,triage_alerts,read_alert_queue");
  await expect(page.getByRole("region", { name: "Rules and Monitoring" })).toBeVisible();
  await page.locator("body").focus();
  await page.keyboard.press("r");
  await expect(page.getByRole("heading", { name: "Choose the case whose alerts to work" })).toBeVisible();
  await page.getByRole("button", { name: "Operation Ledger (synthetic demo)", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__START__?.opened)).toEqual({ id: "c1", view: "rules" });
  await expect(page.getByText("Workspace on c1, rules")).toBeVisible();
  registerCovered(REGISTRY, "open-rules-and-monitoring-from-home-by-keyboard");
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
// ADR-132 Amendment 8 (the owner's ruling, 13 November 2026): under GOV.UK a workspace screen's top is
// compact: a slim header (its places kept), the banner on one slim line (its words and landmark kept), and
// the context bar's "You are in …" folded into the start of its own row (its region and name kept). The
// OFFICIAL strip and the toolbar are untouched, and so are the dark and light looks and Home. Measured in
// Chromium at 1440×1000 with the demonstration's banner words, as osprey-small shows them; at main 054f24b
// the place's content started at 257 px under GOV.UK and at 130 in dark and light.
const DEMO_WORDS = "Demonstration only: this is not a government service, and all data is synthetic.";
// Whole pixels: a line box's height depends on the fonts' metrics, which differ by a fraction between hosts.
const top = (page: import("@playwright/test").Page, selector: string) =>
  page.locator(selector).first().evaluate((e) => { const b = e.getBoundingClientRect(); return { top: Math.round(b.top), height: Math.round(b.height), bottom: Math.round(b.bottom) }; });

test("govuk: a case's workspace gains at least 100 px of height, the strip and toolbar untouched", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/keyboard/places-harness.html?banner=1&brand=govuk");
  const content = await top(page, 'main[aria-label="Place content"]');
  expect.soft(content.top, "the canvas starts at least 100 px higher than main's 257").toBeLessThanOrEqual(257 - 100);
  expect.soft((await top(page, ".govuk-header")).height, "a slim header").toBeLessThanOrEqual(48);
  await expect(page.locator(".govuk-header").getByRole("navigation", { name: "Places" })).toBeVisible();
  const banner = page.getByRole("region", { name: "Service phase" });
  await expect(banner).toHaveText(DEMO_WORDS);
  expect.soft((await top(page, '[aria-label="Service phase"]')).height, "the banner on one slim line").toBeLessThanOrEqual(30);
  expect.soft((await top(page, ".classification-strip")).height, "the marking strip untouched").toBe(20);
  expect.soft((await top(page, ".top-bar")).height, "the toolbar untouched").toBe(44);
});

for (const place of ["glass", "ingest", "rules", "admin"] as const) {
  test(`govuk: the context bar is one row, "You are in" at its start, its region and name kept (${place})`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`/keyboard/places-harness.html?banner=1&brand=govuk&place=${place}&rights=investigate,edit_pipelines,triage_alerts,read_alert_queue,manage_people`);
    const name = { glass: "You are in the Glass", ingest: "You are in the Ingest Studio", rules: "You are in Rules and Monitoring", admin: "You are in Admin" }[place];
    const region = page.getByRole("region", { name });
    // Each claim judged on its own (rule 15), so each was shown red alone at 054f24b.
    await expect.soft(region.getByRole("heading", { level: 2, name })).toBeVisible();
    const bar = await region.evaluate((e) => e.getBoundingClientRect().height);
    expect.soft(bar, "one row").toBeLessThanOrEqual(40);
    const heading = region.getByRole("heading", { level: 2 });
    const size = (e: Element) => getComputedStyle(e).fontSize;
    const rowSize = await region.evaluate((e) => getComputedStyle(e.querySelector(".govuk-notification-banner__content") ?? e).fontSize);
    expect.soft(await heading.evaluate(size), "the title at the row's size").toBe(rowSize);
    if (place === "glass") {
      const title = await heading.boundingBox();
      const caseSection = await region.getByRole("button", { name: "Graph", exact: true }).boundingBox();
      expect.soft(Math.abs(title!.y + title!.height / 2 - (caseSection!.y + caseSection!.height / 2)), "on the same row as Graph").toBeLessThan(6);
      expect.soft(title!.x, "at the row's start").toBeLessThan(caseSection!.x);
      expect.soft(await region.getByRole("button", { name: "Graph", exact: true }).evaluate(size), "Graph at the row's size").toBe(rowSize);
    }
  });
}

// ADR-145 Amendment 13 against ADR-132 Amendment 8's slim row: at 1440 the open mode's note is in the row,
// which stays one row (32 px measured); at 1024 it does not fit there and is on the line under it, still in
// the region (66 px measured, the cross-link on that line too). Each mode's note, as each is a different length.
for (const [width, most, inRow] of [[1440, 40, true], [1024, 72, false]] as const) {
  for (const mode of ["Graph", "Drawing board"] as const) {
    test(`govuk ${width}: the context row with ${mode}'s note is ${inRow ? "one row" : "at most two lines, the note under the row"}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto("/keyboard/places-harness.html?banner=1&brand=govuk");
      const region = page.getByRole("region", { name: "You are in the Glass" });
      await region.getByRole("button", { name: mode, exact: true }).focus();
      await page.keyboard.press("Enter");
      const note = region.locator(".context-banner__note");
      await expect(note).toHaveText(mode === "Graph" ? /^Graph: the case's data/ : /^Drawing board: your sketch/);
      const box = (await region.boundingBox())!;
      const title = (await region.getByRole("heading", { level: 2 }).boundingBox())!;
      const line = (await note.boundingBox())!;
      expect.soft(box.height, "the region's height").toBeLessThanOrEqual(most);
      expect.soft(line.y >= box.y && line.y + line.height <= box.y + box.height, "the note inside the region").toBe(true);
      if (inRow) expect.soft(Math.abs(line.y + line.height / 2 - (title.y + title.height / 2)), "the note on the title's row").toBeLessThan(6);
      else expect.soft(line.y, "the note under the title's row").toBeGreaterThanOrEqual(title.y + title.height);
    });
  }
}

for (const theme of ["dark", "light"] as const) {
  test(`ospreyflow ${theme}: a case's workspace top is as it was`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/keyboard/places-harness.html?banner=1");
    if (theme === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
    expect((await top(page, 'main[aria-label="Place content"]')).top).toBe(130);
    expect((await top(page, '[aria-labelledby="context-banner-title"]')).height).toBe(41);
  });
}

for (const [screen, harness] of [["Home", "start-harness.html"], ["the sign-in page", "sign-in-harness.html"]] as const) {
  test(`govuk: ${screen} keeps the full header and banner`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`/keyboard/${harness}?brand=govuk`);
    await expect(page.locator(".govuk-header")).toBeVisible();
    expect.soft((await top(page, ".govuk-header")).height).toBe(61);
    expect.soft((await top(page, '[aria-label="Service phase"]')).height).toBe(41);
  });
}

// ADR-132 Amendment 8 (the owner's ruling, 13 November 2026): off gov.uk the header draws no crown, the word
// mark and its link kept; on a gov.uk host the crown is drawn, as before.
for (const [where, query, crown] of [["off gov.uk", "", 0], ["on gov.uk", "&host=demo.service.gov.uk", 1]] as const) {
  test(`govuk ${where}: the header's crown ${crown ? "is drawn" : "is not drawn"}, the GOV.UK link kept`, async ({ page }) => {
    await page.goto(`/keyboard/shell-harness.html?brand=govuk${query}`);
    const header = page.locator(".govuk-header");
    await expect(header.getByRole("link", { name: /GOV\.UK/ })).toBeVisible();
    await expect(header.locator(".govuk-header__logotype g")).toHaveCount(crown);
  });
}

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

// ADR-132 Amendment 7: the deployment's own banner words are text, not a control: the banner adds no
// Tab stop, the skip link stays the first, and the words are read in the "Service phase" region.
for (const [brand, theme] of [["ospreyflow", "dark"], ["ospreyflow", "light"], ["govuk", "light"]] as const) {
  test(`${brand} ${theme}: the deployment's banner words add no Tab stop and are read in their region`, async ({ page }) => {
    await page.goto(`/keyboard/shell-harness.html?brand=${brand}&banner=1`);
    // As the scans in `a11y/every-harness.spec.ts` choose a theme (GOV.UK holds the page light).
    await page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);
    const region = page.getByRole("region", { name: "Service phase" });
    await expect(region).toContainText("Demonstration only: this is not a government service, and all data is synthetic.");
    await expect(region.locator("a, button, input, [tabindex]")).toHaveCount(0);
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement?.textContent?.trim())).toBe("Skip to main content");
  });
}

// ADR-132 Amendment 7 (the owner's ruling of 13 November 2026): off gov.uk the workspace's footer is one
// line, its two links still reached by Tab and nothing of the Crown in it; on gov.uk, the full footer.
test("govuk off gov.uk: the one-line footer's links are reached by Tab, and nothing of the Crown is drawn", async ({ page }) => {
  await page.goto("/keyboard/shell-harness.html?brand=govuk");
  const footer = page.locator(".govuk-footer");
  await expect(footer).toHaveClass(/govuk-footer--slim/);
  await expect(footer).not.toContainText("Crown copyright");
  await expect(footer).not.toContainText("Open Government Licence");
  await expect(footer.locator(".govuk-footer__crown")).toHaveCount(0);
  await footer.getByRole("link", { name: "Accessibility statement" }).focus();
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.activeElement?.textContent?.trim())).toBe("Cookies");
});

test("govuk on gov.uk: the full footer, Crown copyright reached by Tab", async ({ page }) => {
  await page.goto("/keyboard/shell-harness.html?brand=govuk&host=demo.service.gov.uk");
  const footer = page.locator(".govuk-footer");
  await expect(footer).not.toHaveClass(/govuk-footer--slim/);
  await expect(footer.locator(".govuk-footer__crown")).toHaveCount(1);
  await footer.getByRole("link", { name: "Cookies" }).focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.activeElement?.textContent?.trim())).toBe("© Crown copyright");
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

// ADR-145 Amendment 14 decision 2 (the owner, 13 November 2026: "the Cases panel covers the top navigation"):
// a drawer opens under the top bar and the context row, so the places, the top bar's controls, the GOV.UK header's
// navigation and the row's case switcher and cross-link stay in view and can be clicked while it is open. In each
// look the scans use, at 1440 and again after the window narrows to 900, where the bar and the row wrap and the
// drawer is measured again.
for (const [brand, theme] of [["ospreyflow", "dark"], ["ospreyflow", "light"], ["govuk", "light"]] as const) {
  test(`${brand} ${theme}: an open drawer starts under the top bar and the context row, the navigation above it uncovered`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/keyboard/shell-harness.html?brand=${brand}&drawer=1`);
    await page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);
    const drawer = page.getByRole("dialog", { name: "Cases" });
    await expect(drawer).toBeVisible();
    // What the case asserts, returned rather than thrown, so `expect.poll` can wait for the frame after a resize.
    const measure = async () => {
      const row = (await page.getByRole("region", { name: "You are in the Glass" }).boundingBox())!;
      const bar = (await page.locator(".top-bar").boundingBox())!;
      const box = (await drawer.boundingBox())!;
      // Every control above the drawer's top and inside its columns is the topmost thing at its own centre.
      const covered = await page.evaluate(() => {
        const top = document.querySelector<HTMLElement>("[role='dialog']")!.getBoundingClientRect();
        return [...document.querySelectorAll<HTMLElement>("header a, header button, .top-bar a, .top-bar button, [aria-labelledby='context-banner-title'] button")]
          .filter((el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0 && r.right > top.left;
          })
          .filter((el) => {
            const r = el.getBoundingClientRect();
            const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return !(hit && (hit === el || el.contains(hit)));
          })
          .map((el) => el.getAttribute("aria-label") ?? el.textContent?.trim());
      });
      return { underTheChrome: box.y >= Math.floor(Math.max(bar.y + bar.height, row.y + row.height)), covered, top: box.y, chrome: row.y + row.height };
    };
    await expect.poll(measure).toMatchObject({ underTheChrome: true, covered: [] });
    const wide = await measure();
    await page.setViewportSize({ width: 900, height: 900 });
    // At 900 the row wraps, so the chrome is deeper; the drawer is measured again and follows it.
    await expect.poll(async () => (await measure()).chrome).toBeGreaterThan(wide.chrome);
    await expect.poll(measure).toMatchObject({ underTheChrome: true, covered: [] });
    // Its own way out is reached by keyboard: the drawer takes focus as it opens, and Tab reaches Close.
    await drawer.focus();
    await page.keyboard.press("Tab");
    await expect(drawer.getByRole("button", { name: "Close Cases" })).toBeFocused();
  });
}
