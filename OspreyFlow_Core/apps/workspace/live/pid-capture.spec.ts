// The Prison Intelligence demo's screen captures (Brief 3 Part C), against the deployed Glass and
// the loaded synthetic PID case. Every shot is a function of a named case state that this file
// puts there itself; nothing is mocked and no image is edited. See `pid-capture.config.ts` for how
// to run it. Each PNG is named exactly its capture id and written to the demo's `screens/` folder.
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE = join(HERE, "../../..");
const SCREENS = join(CORE, "../OspreyFlow_presentations/prison_intelligence_demo/screens");
const ENV_FILE =
  process.env.OSPREY_PID_CAPTURE_ENV ?? join(CORE, "deploy/generated/local-lite/deployment.env");

export const CASE_NAME = "Prison Intelligence Dataset (synthetic demo)";

/** The coordinator's number, as the plan writes it (`07`… national form) and as it is stored
 * (`+44`…), read from the plan itself: Brief 1's J2 check refuses any file of the repository that
 * writes it, so that a search for it finds the PID's data and nothing else. */
function coordinatorNumber(): { national: string; international: string } {
  const out = execFileSync(
    join(CORE, ".venv/bin/python"),
    [
      "-c",
      "from demo_fixtures import pid_plan; e = pid_plan.build_plan('demo').entity('number:coordinator');" +
        " print(e.properties['value_raw']); print(e.properties['value_normalised'])",
    ],
    { cwd: CORE, env: { ...process.env, PYTHONPATH: ".:packages" } },
  )
    .toString()
    .trim()
    .split("\n");
  const [national, international] = out;
  if (!national || !international) throw new Error("the plan gave no coordinator's number");
  return { national, international };
}

test.skip(
  process.env.OSPREY_PID_CAPTURE !== "1",
  "captures the owner's deployment; opt in with OSPREY_PID_CAPTURE=1",
);

type Persona = "analyst" | "engineer" | "viewer" | "admin";

const ACCOUNTS: Record<Persona, { username: string; secret: string }> = {
  analyst: { username: "osprey-demo-analyst", secret: "OSPREY_DEMO_ANALYST_PASSWORD" },
  engineer: { username: "osprey-demo-engineer", secret: "OSPREY_DEMO_ENGINEER_PASSWORD" },
  viewer: { username: "osprey-demo-report-viewer", secret: "OSPREY_DEMO_REPORT_VIEWER_PASSWORD" },
  admin: { username: "osprey-demo-admin", secret: "OSPREY_DEMO_ADMIN_PASSWORD" },
};

/** The persona's password, read from the deployment's own file and never printed or logged. */
function passwordOf(persona: Persona): string {
  const name = ACCOUNTS[persona].secret;
  for (const line of readFileSync(ENV_FILE, "utf-8").split("\n")) {
    if (line.startsWith(`${name}=`)) return line.slice(name.length + 1).replace(/^"|"$/g, "");
  }
  throw new Error(`${name} is not in the deployment's env file`);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("ospreyflow.theme", "light");
    } catch {
      /* storage may be blocked; the attribute below still decides this page */
    }
    document.documentElement.setAttribute("data-theme", "light");
  });
});

/** Through the deployment's own sign-in page, as a person would. Tokens live in memory only, so
 * a shot never reloads the page after this. */
export async function signIn(page: Page, persona: Persona): Promise<void> {
  await page.goto("/");
  const glass = new URL(page.url()).hostname;
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.locator("#username").fill(ACCOUNTS[persona].username);
  await page.locator("#password").fill(passwordOf(persona));
  await page.locator("#kc-login").click();
  // Back on the Glass's own address, once it has taken the code out of the address bar.
  await page.waitForURL((url) => url.hostname === glass && !url.searchParams.has("code"));
}

/** Opens the PID case by its name in the case switcher, or from the case picker on first entry. */
export async function openCase(page: Page, name = CASE_NAME): Promise<void> {
  const picker = page.getByRole("button", { name, exact: true });
  const switcher = page.getByRole("button", { name: /^Case:/ });
  await expect(picker.or(switcher).first()).toBeVisible();
  if (!(await picker.first().isVisible())) await switcher.click();
  await page.getByRole("button", { name, exact: true }).first().click();
  await expect(page.getByRole("button", { name: /^Case:/ })).toContainText(name);
}

export async function shot(page: Page, id: string): Promise<void> {
  mkdirSync(SCREENS, { recursive: true });
  await page.screenshot({ path: join(SCREENS, `${id}.png`) });
}


/** Closes the welcome panel when it is open, so it does not sit over the canvas in a shot. */
export async function dismissWelcome(page: Page): Promise<void> {
  const welcome = page.getByRole("dialog", { name: "Welcome back" });
  if (await welcome.isVisible().catch(() => false)) {
    await page.keyboard.press("Escape");
  }
  const close = page.getByRole("button", { name: /close/i }).filter({ hasText: "×" });
  if (await close.first().isVisible().catch(() => false)) await close.first().click();
}

/** The search box: types `text` and returns the type-ahead's options. */
export async function searchFor(page: Page, text: string) {
  const box = page.getByRole("combobox", { name: /Search entities/ });
  await box.fill(text);
  return page.getByRole("listbox").getByRole("option");
}

/** Searches `text` and picks the result reading `pick`, waiting for the answer to `text` rather
 * than clicking an earlier query's result. */
export async function pickFromSearch(page: Page, text: string, pick: RegExp): Promise<void> {
  const options = await searchFor(page, text);
  const wanted = options.filter({ hasText: pick }).first();
  await expect(wanted).toBeVisible();
  await wanted.click();
}

// --- the shared states -----------------------------------------------------------------------

/** The working set is the server's, per case, so a shot starts by emptying what an earlier one
 * left, through the view's own Clear view and its confirmation. */
export async function clearCanvas(page: Page): Promise<void> {
  const clear = page.getByRole("button", { name: "Clear view" });
  if (await clear.isEnabled().catch(() => false)) {
    await clear.click();
    await page.getByRole("button", { name: /^Clear all/ }).click();
  }
  await expect(counts(page)).toContainText(/^0 nodes/);
  // The working set is the server's: wait out a late delta from an earlier shot before adding.
  await page.waitForTimeout(3000);
  await expect(counts(page)).toContainText(/^0 nodes/);
}

/** The status bar's live counts ("N nodes N edges N dimmed by filter"). */
export const counts = (page: Page) => page.locator(".status-bar__counts");

/** Opens the case for `persona` on an empty canvas with the welcome panel closed. */
export async function freshCase(page: Page, persona: Persona = "analyst"): Promise<void> {
  await signIn(page, persona);
  await openCase(page);
  await dismissWelcome(page);
  await clearCanvas(page);
}

export const rail = (page: Page, name: string) =>
  page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name });

/** Explore, Most connected, the node's Add…, then "With all N links…". */
export async function addWithAllLinks(page: Page, label: string): Promise<void> {
  await rail(page, "Explore").click();
  const explore = page.getByRole("dialog", { name: "Explore" });
  const add = explore.getByRole("button", { name: `Add ${label} to the graph` });
  // Most connected first; after chapter 4 the reports outrank people there, so By entity type next.
  await explore.getByRole("button", { name: "Most connected" }).click();
  await page.waitForTimeout(2500);
  for (let more = 0; more < 4 && !(await add.isVisible().catch(() => false)); more++) {
    const showMore = explore.getByRole("button", { name: /^Show \d+ more$/ });
    if (!(await showMore.isVisible().catch(() => false))) break;
    await showMore.click();
    await page.waitForTimeout(2000);
  }
  if (!(await add.isVisible().catch(() => false))) {
    await explore.getByRole("button", { name: "By entity type" }).click();
    await explore.getByRole("button", { name: /^Person · / }).click();
    await page.waitForTimeout(2500);
  }
  await add.click();
  await explore.getByRole("button", { name: /^With all .* links…$/ }).first().click();
  await page.waitForTimeout(3000);
  if (await explore.isVisible().catch(() => false)) {
    await explore.getByRole("button", { name: "Close", exact: true }).click();
  }
  await closeMessages(page);
}

/** Closes any transient canvas message ("Nothing new: …"), saying what it said. */
export async function closeMessages(page: Page): Promise<void> {
  for (const close of await page.getByRole("button", { name: "Close message" }).all()) {
    console.log(`message: ${await close.locator("xpath=..").textContent()}`);
    await close.click();
  }
}

const inspector = (page: Page) => page.getByRole("region", { name: "Inspector" });

const SIDE_PANELS = ["Inspector", "Metrics", "Query builder", "Find connections"] as const;

/** Folds the side panels a shot does not need (each panel's own header, in its "<Panel> position"
 * toolbar), so the one it does has the room; `keep` is opened if it was folded. */
export async function onlyPanel(page: Page, keep: string = "Inspector"): Promise<void> {
  for (const panel of SIDE_PANELS) {
    const head = page
      .getByRole("toolbar", { name: `${panel} position` })
      .getByRole("button", { name: panel, exact: true });
    if (!(await head.isVisible().catch(() => false))) continue;
    const open = (await head.getAttribute("aria-expanded")) === "true";
    if (open !== (panel === keep)) await head.click();
  }
}

/** Lays the view out and fits it to the window. */
export async function arrange(page: Page, layout: string): Promise<void> {
  await page.getByRole("combobox", { name: "Layout" }).selectOption(layout);
  await page.waitForTimeout(2500);
  await page.getByRole("button", { name: "Fit to view" }).click();
  await page.waitForTimeout(1000);
}

test("CAP-A1-J1", async ({ page }) => {
  await freshCase(page);
  await addWithAllLinks(page, "Vance, Callum");
  await page.waitForTimeout(4000);
  console.log(`J1 counts: ${await counts(page).textContent()}`);
  await onlyPanel(page);
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await arrange(page, "Radial around selected node");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press("l");
    const text = (await inspector(page).textContent()) ?? "";
    if (/Shared a cell with/i.test(text)) break;
  }
  await page.waitForTimeout(800);
  await shot(page, "CAP-A1-J1");
});

/** A large draw asks first; a shot that wants only what is near takes Cancel. */
export async function declineLargeDraw(page: Page): Promise<void> {
  const cancel = page.getByRole("button", { name: "Cancel", exact: true });
  await page.waitForTimeout(3000);
  if (await cancel.isVisible().catch(() => false)) await cancel.click();
  await page.waitForTimeout(1500);
}

/** Leaves only the named link types ticked in the legend's "Links in view". */
export async function onlyLinkTypes(page: Page, keep: string[]): Promise<void> {
  const boxes = page.locator('ul[aria-label="Links in view"]').getByRole("checkbox");
  for (const box of await boxes.all()) {
    const name = (await box.getAttribute("aria-label")) ?? (await box.locator("xpath=..").textContent()) ?? "";
    const wanted = keep.some((k) => name.includes(k));
    if ((await box.isChecked()) !== wanted) await box.click();
  }
}

test("CAP-A1-J2", async ({ page }) => {
  await freshCase(page);
  const { national } = coordinatorNumber();
  await pickFromSearch(page, `+44 ${national.slice(1)}`, /^Endpoint/);
  await declineLargeDraw(page);
  console.log(`J2 counts: ${await counts(page).textContent()}`);
  await onlyPanel(page);
  await onlyLinkTypes(page, ["Uses", "Communicated with"]);
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await arrange(page, "Radial around selected node");
  await shot(page, "CAP-A1-J2");
});

const COHORT = process.env.OSPREY_PID_COHORT_LIST ?? "";

test("CAP-A1-J3", async ({ page }) => {
  await freshCase(page);
  await page.getByRole("button", { name: "Add many from a list", exact: true }).first().click();
  await page.getByRole("textbox", { name: /identifiers/i }).fill(readFileSync(COHORT, "utf-8"));
  await page.getByRole("button", { name: "Count" }).click();
  await page.waitForTimeout(3000);
  await page.getByRole("button", { name: "Add with all links" }).click();
  await page.waitForTimeout(5000);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await closeMessages(page);
  console.log(`J3 counts: ${await counts(page).textContent()}`);
  await page.getByRole("button", { name: "Communities" }).click();
  await page.waitForTimeout(3000);
  await page.getByRole("button", { name: "Fit to view" }).click();
  await rail(page, "Explore").click();
  const explore = page.getByRole("dialog", { name: "Explore" });
  await explore.getByRole("button", { name: "Busiest links" }).click();
  await page.waitForTimeout(3000);
  await shot(page, "CAP-A1-J3");
});

test("CAP-A2-C1", async ({ page }) => {
  await freshCase(page);
  await rail(page, "Cases").click();
  const brief = page.getByRole("region", { name: "Brief" });
  await expect(brief).toBeVisible();
  await brief.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1000);
  await shot(page, "CAP-A2-C1");
});

const canvas = (page: Page) => page.getByRole("application", { name: "Network canvas" });

/** The principal with all his links, laid out round him and fitted (J1's state). */
export async function principalStar(page: Page, panel = "Inspector"): Promise<void> {
  await freshCase(page);
  await addWithAllLinks(page, "Vance, Callum");
  await page.waitForTimeout(3000);
  await onlyPanel(page, panel);
  await canvas(page).focus();
  await arrange(page, "Radial around selected node");
}

/** Picks an end of Find connections by its own search box. */
async function chooseEnd(page: Page, end: "From" | "To", typed: string, pick: RegExp) {
  await page.getByRole("combobox", { name: `Search for ${end}` }).fill(typed);
  const option = page.getByRole("listbox").getByRole("option").filter({ hasText: pick }).first();
  await expect(option).toBeVisible();
  await option.click();
}

test("CAP-A1-J5", async ({ page }) => {
  await principalStar(page, "Find connections");
  await chooseEnd(page, "From", "Z2486ZZ", /Vance/);
  await chooseEnd(page, "To", "Z2513ZZ", /Skellion/);
  await page.getByRole("button", { name: /^Find connections$/ }).last().click();
  const said = page.getByRole("status").filter({ hasText: "degrees apart" });
  await expect(said).toBeVisible();
  console.log(`J5: ${await said.textContent()}`);
  await page.waitForTimeout(2000);
  await shot(page, "CAP-A1-J5");
});

test("CAP-A1-J7", async ({ page }) => {
  await principalStar(page, "Metrics");
  await page.getByRole("combobox", { name: "Primary metric" }).selectOption({ label: "Betweenness" });
  await page.waitForTimeout(4000);
  const ranked = page.getByRole("list", { name: "Ranked nodes" });
  console.log(`J7: ${(await ranked.textContent())?.slice(0, 200)}`);
  await shot(page, "CAP-A1-J7");
});

test("CAP-A1-J6", async ({ page }) => {
  await principalStar(page, "Metrics");
  await page.getByRole("button", { name: "Communities" }).click();
  await page.getByRole("combobox", { name: "Primary metric" }).selectOption({ label: "Clique Metric" });
  await page.waitForTimeout(3000);
  await arrange(page, "Clustered bubbles");
  await canvas(page).press("Escape");
  await page.waitForTimeout(1000);
  await shot(page, "CAP-A1-J6");
});

test("CAP-A1-J4", async ({ page }) => {
  await principalStar(page);
  await page.getByRole("button", { name: "Show the timeline" }).click();
  await page.getByRole("button", { name: "More timeline options" }).click();
  await page.getByRole("menuitem", { name: "Set exact dates" }).or(page.getByRole("button", { name: "Set exact dates" })).first().click();
  await page.getByLabel("Brush window start").fill("2025-12-01");
  await page.getByLabel("Brush window end").fill("2026-04-30");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: "More timeline options" }).click();
  await page.waitForTimeout(1500);
  console.log(`J4 counts: ${await counts(page).textContent()}`);
  await shot(page, "CAP-A1-J4");
});

/** Adds, from Explore's Most connected, each named node with all its links. */
export async function addEachWithAllLinks(page: Page, labels: string[]): Promise<void> {
  for (const label of labels) await addWithAllLinks(page, label);
}

const HOTSPOT_YARDS = ["Yard 03", "Yard 04", "Yard 05"];

/** The hotspot yards with their throw-overs, on the Map view. */
export async function yardsOnTheMap(page: Page): Promise<void> {
  await freshCase(page);
  await addEachWithAllLinks(page, HOTSPOT_YARDS);
  await page.getByRole("button", { name: "Map", exact: true }).click();
  await page.waitForTimeout(6000);
}

/** Draws a boundary through the given points of the map's own area (CSS pixels). The outline
 * shows only while it is being drawn (closing applies it and removes the outline), so a shot that
 * must show the boundary is taken before `closeBoundary`. */
export async function drawBoundary(page: Page, points: [number, number][]): Promise<void> {
  await page.getByRole("button", { name: "Draw boundary" }).click();
  await page.waitForTimeout(500);
  for (const [x, y] of points) {
    await page.mouse.click(x, y);
    await page.waitForTimeout(300);
  }
}

export async function closeBoundary(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Close boundary" }).click();
  await page.waitForTimeout(2500);
}

test("CAP-A2-C2", async ({ page }) => {
  await yardsOnTheMap(page);
  await drawBoundary(page, [[320, 340], [480, 140], [840, 300], [840, 800], [560, 800], [320, 600]]);
  await shot(page, "CAP-A2-C2");
  await closeBoundary(page);
  console.log(`C2 counts after the boundary is applied: ${await counts(page).textContent()}`);
});

test("CAP-A2-C3", async ({ page }) => {
  await freshCase(page);
  await addEachWithAllLinks(page, HOTSPOT_YARDS);
  await onlyLinkTypes(page, ["Occurred at"]);
  // The timeline is opened and sized before the Map view: opened over a drawn map, the map goes
  // blank (a finding), so the map is drawn last, at its final size.
  await page.getByRole("button", { name: "Show the timeline" }).click();
  await page.getByRole("group", { name: "Timeline view" }).getByRole("button", { name: "Cyclical" }).click();
  const sash = page.getByRole("separator", { name: "Resize the timeline" });
  const handle = await sash.boundingBox();
  if (handle) {
    await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
    await page.mouse.down();
    await page.mouse.move(handle.x + handle.width / 2, handle.y - 220, { steps: 8 });
    await page.mouse.up();
  }
  await page.getByRole("button", { name: "Map", exact: true }).click();
  await page.waitForTimeout(6000);
  // The weekend cells are brushed (ADR-130 decision 2): the grid stays whole with the chosen
  // cells marked, and the map and the canvas keep only what falls in them.
  await page.getByRole("button", { name: "More timeline options" }).click();
  const cells = page.getByRole("group", { name: "Choose cells (UTC)" });
  await cells.getByRole("checkbox", { name: "Sat" }).check();
  await cells.getByRole("checkbox", { name: "Sun" }).check();
  await page.getByRole("button", { name: "More timeline options" }).click();
  await page.waitForTimeout(3000);
  console.log(`C3 counts: ${await counts(page).textContent()}`);
  await shot(page, "CAP-A2-C3");
});

test("CAP-A1-J8-b", async ({ page }) => {
  // The principal's search pick draws three links out (ADR-070): 3,344 nodes, over the cap, so
  // the Glass asks before drawing, with its options; nothing is cut.
  await freshCase(page);
  console.log("J8-b: picking");
  await pickFromSearch(page, "Z2486ZZ", /^Person/);
  console.log("J8-b: picked");
  await expect(page.getByText(/more than 500/)).toBeVisible();
  console.log(`J8-b: offer: ${await page.getByText(/more than 500/).textContent()}`);
  await page.waitForTimeout(1500);
  await shot(page, "CAP-A1-J8-b");
  console.log("J8-b: shot");
});

/** Steps the focused node's links with `L` until the Inspector names `type`. */
async function selectLinkOfType(page: Page, type: RegExp): Promise<boolean> {
  await canvas(page).focus();
  for (let i = 0; i < 80; i++) {
    await page.keyboard.press("l");
    if (type.test((await inspector(page).textContent()) ?? "")) return true;
  }
  return false;
}

test("CAP-A1-J9-a", async ({ page }) => {
  await principalStar(page);
  // The inferred link (drawn dashed) beside a solid one: the principal's Passes items to.
  const found = await selectLinkOfType(page, /Passes items to/);
  console.log(`J9-a inferred link selected: ${found}`);
  await page.waitForTimeout(800);
  await shot(page, "CAP-A1-J9-a");
});

/** The Reports view on one of its tabs. */
export async function reportsTab(page: Page, tab: string): Promise<void> {
  await page.getByRole("button", { name: "Reports", exact: true }).click();
  await page.getByRole("tab", { name: tab, exact: true }).click();
  await page.waitForTimeout(4000);
}

test("CAP-A1-J9-b", async ({ page }) => {
  await freshCase(page);
  await reportsTab(page, "Data feeds");
  await shot(page, "CAP-A1-J9-b");
});

test("CAP-A1-J9-c", async ({ page }) => {
  await freshCase(page);
  await throwOverTrend(page);
  await page.getByRole("button", { name: "Save trend" }).click();
  await page.waitForTimeout(2500);
  await page.getByRole("tab", { name: "Packs", exact: true }).click();
  await page.waitForTimeout(2500);
  await page.getByRole("button", { name: /^Wing F supply route/ }).first().click();
  await page.getByLabel("Saved trend").selectOption({ label: "Throw-overs by yard" });
  await page.getByRole("button", { name: "Add item" }).click();
  await page.waitForTimeout(3000);
  await shot(page, "CAP-A1-J9-c");
});

/** A trend of the throw-overs per month, split by yard, previewed (not saved). */
export async function throwOverTrend(page: Page): Promise<void> {
  await reportsTab(page, "Trends");
  await page.getByLabel("Title", { exact: true }).fill("Throw-overs by yard");
  await page.getByRole("checkbox", { name: "Occurred at" }).check();
  await page.getByLabel("Interval").selectOption("month");
  const weeks = page.getByLabel("Weeks back");
  const longest = await weeks.locator("option").evaluateAll((o) => (o as HTMLOptionElement[]).map((x) => x.value).pop());
  if (longest) await weeks.selectOption(longest);
  await page.getByLabel("Series").selectOption({ label: "By yard" });
  await page.getByRole("button", { name: /^Preview/ }).click();
  await page.waitForTimeout(5000);
  await scrollAllToTop(page);
}

/** Puts every scrolled pane back at its top, so a shot starts at the top of each. */
export async function scrollAllToTop(page: Page): Promise<void> {
  await page.evaluate(() => {
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("*"))) {
      if (el.scrollTop > 0) el.scrollTop = 0;
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(500);
}

test("CAP-A2-C10-b", async ({ page }) => {
  await freshCase(page);
  await throwOverTrend(page);
  await shot(page, "CAP-A2-C10-b");
});

/** The Ingest Studio on the PID case, as the data engineer. */
export async function studio(page: Page): Promise<void> {
  await signIn(page, "engineer");
  await page.getByRole("button", { name: /Open Ingest Studio/ }).or(page.getByRole("link", { name: /Open Ingest Studio/ })).first().click();
  await page.getByRole("button", { name: CASE_NAME, exact: true }).click();
  await expect(page.getByRole("button", { name: /^Open Intelligence reports/ })).toBeVisible();
}

test("CAP-M1", async ({ page }) => {
  await studio(page);
  await page.waitForTimeout(1500);
  await shot(page, "CAP-M1-a");
  await page.getByRole("button", { name: /^Open PIN phone contacts/ }).click();
  await page.waitForTimeout(5000);
  await shot(page, "CAP-M1-b");
  // V6: the schedule editor's preview, read and never saved (Brief 2 section 7.4).
  const cadence = page.getByLabel("How often");
  console.log(`V6 cadences: ${JSON.stringify(await cadence.locator("option").allTextContents())}`);
  await cadence.selectOption("weekdays");
  await page.getByLabel("Time", { exact: true }).fill("07:30");
  await page.waitForTimeout(3000);
  const preview = page.getByRole("status", { name: "Schedule preview" });
  console.log(`V6 preview: ${await preview.textContent().catch(() => "(none)")}`);
});

test("CAP-A2-C4", async ({ page }) => {
  await studio(page);
  await page.getByRole("button", { name: /^Open Intelligence reports/ }).click();
  await page.getByRole("button", { name: "Source: Intelligence reports" }).click();
  await page.waitForTimeout(2000);
  await page.getByRole("button", { name: "Open source settings" }).click();
  await page.waitForTimeout(3000);
  // The source's settings: the file, its marking and the columns that carry each row's marking.
  // (The fallback-published recipe shows no entity Map stage on the canvas: a finding.)
  await shot(page, "CAP-A2-C4-a");
  await page.getByRole("button", { name: "Back to the pipeline" }).click();
  await page.getByRole("button", { name: "Verify", exact: true }).click();
  await page.getByRole("button", { name: "Run verify" }).click();
  // A dry run over the profiled sample: nothing is written.
  await page.waitForTimeout(20000);
  await scrollAllToTop(page);
  await shot(page, "CAP-A2-C4-b");
});

/** Runs a published pipeline from its Publish screen and waits for the run's own outcome. */
async function runNow(page: Page, open: RegExp): Promise<string> {
  await page.getByRole("button", { name: open }).click();
  const publish = page.getByRole("button", { name: "Publish", exact: true });
  const run = page.getByRole("button", { name: "Run now" });
  // A published recipe opens on its Publish screen; a draft opens on its canvas first.
  try {
    await run.waitFor({ timeout: 10_000 });
  } catch {
    await publish.click();
  }
  await run.click();
  const outcome = page.getByText(/Succeeded:|Failed|refused/i).first();
  await expect(outcome).toBeVisible({ timeout: 240_000 });
  await page.waitForTimeout(3000);
  const runs = (await page.getByRole("list", { name: "Runs of this recipe" }).textContent()) ?? "";
  await page.getByRole("button", { name: /Back/ }).first().click();
  return runs;
}

test("chapter 4: the reports, then their incidents", async ({ page }) => {
  test.setTimeout(600_000);
  await studio(page);
  console.log(`R9: ${await runNow(page, /^Open Intelligence reports/)}`);
  console.log(`R17: ${await runNow(page, /^Open Report incidents/)}`);
});

test("chapter 4: the report incidents, once the reports are in", async ({ page }) => {
  test.setTimeout(600_000);
  await studio(page);
  console.log(`R17: ${await runNow(page, /^Open Report incidents/)}`);
});

/** A report, alone on the canvas, opened in the reader. */
export async function openReport(page: Page, title: string) {
  await freshCase(page);
  const options = await searchFor(page, title);
  await options.filter({ hasText: /^Document/ }).first().click();
  // Declining the large draw leaves the report drawn but not in the server's view (a finding:
  // the reader then says "not in your view"), so the offer's own one-relationship choice is taken.
  const mentions = page.getByRole("button", { name: /^MENTIONED_IN \(/ });
  await page.waitForTimeout(3000);
  if (await mentions.isVisible().catch(() => false)) await mentions.click();
  await page.waitForTimeout(3000);
  await closeMessages(page);
  console.log(`report view: ${await counts(page).textContent()}`);
  await canvas(page).focus();
  await page.keyboard.press("Enter");
  const reader = page.getByRole("dialog", { name: /^Reading:/ });
  await expect(reader).toBeVisible();
  return reader;
}

test("CAP-A2-C5", async ({ page }) => {
  const reader = await openReport(page, "IR 0125 — F2 landing");
  await reader.getByRole("button", { name: "Quick scan" }).click();
  await expect(reader.getByRole("button", { name: /^Accept / }).first()).toBeVisible({ timeout: 120_000 });
  await page.waitForTimeout(1500);
  // The marked text and the review list fit one view, so one image holds both halves.
  await shot(page, "CAP-A2-C5");
  await shot(page, "CAP-M3-a"); // the module's reader with marked entities is the same screen
});

test("CAP-A2-C8-a", async ({ page }) => {
  test.setTimeout(1_500_000);
  await principalStar(page);
  await canvas(page).press("Escape"); // the whole view, not one node
  await rail(page, "Questions").click();
  const cited = page.getByRole("button", { name: /^Select \[G-/ });
  await page.getByRole("list", { name: "Questions asked" }).waitFor({ timeout: 15_000 }).catch(() => undefined);
  await page.waitForTimeout(3000); // the stored answers load after the panel opens
  if (!(await cited.first().isVisible().catch(() => false))) {
    await page.getByLabel("Your question").fill(
      "Who is the principal passing items to, and what do the reports say about the throw-overs?",
    );
    const started = Date.now();
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    // A cold model can take minutes, and the Glass may lose a slow answer though the Conduit
    // keeps it (a finding): the panel is reopened until the stored answer is shown.
    for (let i = 0; i < 40 && !(await cited.first().isVisible().catch(() => false)); i++) {
      await page.waitForTimeout(30_000);
      if (await page.getByRole("button", { name: "Asking…" }).isVisible().catch(() => false)) continue;
      await page.getByRole("button", { name: "Close Questions" }).click().catch(() => undefined);
      await rail(page, "Questions").click();
    }
    console.log(`C8-a answered after ${Math.round((Date.now() - started) / 1000)} s`);
  }
  await expect(cited.first()).toBeVisible();
  await page.waitForTimeout(1500);
  await shot(page, "CAP-A2-C8-a");
  await shot(page, "CAP-M3-b");
});

test("CAP-A2-C8-b", async ({ page }) => {
  test.setTimeout(900_000);
  await freshCase(page);
  await onlyPanel(page, "Query builder");
  const ask = page.getByRole("group", { name: "Ask to search" });
  await ask.getByLabel("Ask to search").fill("Prisoners who are members of an organised crime group");
  const started = Date.now();
  await ask.getByRole("button", { name: "Ask", exact: true }).click();
  const said = page.getByText(/matches/).first();
  await expect(said.or(page.getByRole("alert").first()).or(page.getByText(/could not|cannot/i).first())).toBeVisible({ timeout: 840_000 });
  console.log(`C8-b answered in ${Math.round((Date.now() - started) / 1000)} s: ${await said.textContent().catch(() => "")}`);
  await page.waitForTimeout(1500);
  await shot(page, "CAP-A2-C8-b");
});

test("chapter 9a: the analyst hotlists the coordinator's number", async ({ page }) => {
  await freshCase(page);
  await rail(page, "Watches").click();
  await page.getByLabel("Identifier", { exact: true }).fill(coordinatorNumber().national);
  await page.getByLabel("Review date").fill("2027-01-31");
  await page.getByRole("button", { name: "Add to hotlist" }).click();
  await page.waitForTimeout(2500);
  console.log(`hotlist: ${await page.locator(".hotlist-panel").textContent()}`);
});

test("chapter 9b: the engineer loads batch 2", async ({ page }) => {
  test.setTimeout(600_000);
  await studio(page);
  await page.getByRole("button", { name: /^Open Seized media/ }).click();
  const run = page.getByRole("button", { name: "Run now" });
  await run.waitFor();
  await page.getByLabel(/^Source file/).fill(
    "/var/lib/osprey/ingest/uploaded/prison-intelligence/pid_seized_comms_batch2.csv",
  );
  await run.click();
  await expect(page.getByRole("list", { name: "Runs of this recipe" })).toContainText(/batch2|Succeeded.*\n?.*Succeeded/, { timeout: 300_000 }).catch(() => undefined);
  await page.waitForTimeout(5000);
  console.log(`batch 2 runs: ${await page.getByRole("list", { name: "Runs of this recipe" }).textContent()}`);
});

test("CAP-A2-C9", async ({ page }) => {
  // A hotlist's alert is in the Watches rail's Alert inbox; the Alerts rail is the typology rules'
  // queue. The alert explains itself (ADR-130 decision 1): the identifier as typed and its review
  // date, and the node it matched with the files and rows that put it there.
  await freshCase(page);
  await rail(page, "Watches").click();
  await expect(page.getByText(/^Hotlist: /).first()).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(1500);
  await shot(page, "CAP-A2-C9");
  await shot(page, "CAP-M4-b");
});

test("CAP-M4-a", async ({ page }) => {
  await freshCase(page);
  await rail(page, "Watches").click();
  await page.waitForTimeout(2500);
  await shot(page, "CAP-M4-a");
});

test("CAP-A2-C6", async ({ page }) => {
  await principalStar(page, "Find connections");
  // The noise unticked: what links the principal to the coordinator and the payer's pattern stay.
  await onlyLinkTypes(page, [
    "Visited", "Family of", "Member of", "Passes items to", "Uses", "Communicated with", "Transacted",
  ]);
  await canvas(page).focus();
  await arrange(page, "Organic");
  await chooseEnd(page, "From", "Z2486ZZ", /Vance/);
  await chooseEnd(page, "To", "Ellery", /Ellery/);
  await page.getByRole("button", { name: /^Find connections$/ }).last().click();
  const said = page.getByRole("status").filter({ hasText: /degrees? apart/ });
  await expect(said).toBeVisible();
  console.log(`C6: ${await said.textContent()}`);
  await page.waitForTimeout(1500);
  await shot(page, "CAP-A2-C6");
});

test("CAP-A2-C7", async ({ page, context }) => {
  await principalStar(page);
  await page.getByRole("button", { name: "Show the timeline" }).click();
  // The window in which the phones were found: January to April 2026.
  await page.getByRole("button", { name: "More timeline options" }).click();
  await page.getByRole("button", { name: "Set exact dates" }).click();
  await page.getByLabel("Brush window start").fill("2026-01-05T00:00:00Z");
  await page.keyboard.press("Tab");
  await page.getByLabel("Brush window end").fill("2026-05-01T00:00:00Z");
  await page.keyboard.press("Tab");
  await page.getByRole("button", { name: "More timeline options" }).click();
  await page.getByRole("button", { name: "Play playback" }).click();
  await page.waitForTimeout(2500);
  await page.getByRole("button", { name: "Pause playback" }).click();
  await page.getByRole("button", { name: "Select what is lit" }).click();
  await page.waitForTimeout(1500);
  console.log(`C7 counts: ${await counts(page).textContent()}`);
  await shot(page, "CAP-A2-C7-a");
  const opened = context.waitForEvent("page", { timeout: 30_000 }).catch(() => null);
  await page.getByRole("button", { name: "Branch to a new case" }).click();
  // The branch opens in a tab of its own, or in this one; either way the shot is of the branch,
  // marked ⑂ in the case switcher, never of the parent case.
  const branch = (await opened) ?? page;
  await branch.waitForLoadState();
  // The branch's name is the case's own with its window ("… › 5 Jan – 30 Apr 2026, selected").
  await expect(branch.getByRole("button", { name: /^Case: .+ › .+, selected$/ })).toBeVisible({
    timeout: 60_000,
  });
  await branch.waitForTimeout(6000);
  await shot(branch, "CAP-A2-C7-b");
});

test("CAP-A2-C10-a", async ({ page }) => {
  await principalStar(page);
  await canvas(page).press("Escape"); // the composer is offered from the Inspector's empty state
  await page.getByRole("button", { name: "Add judgement, gap or assumption" }).click();
  await page.getByLabel("Statement").fill(
    "Callum Vance directs the throw-overs onto Wing F through his cell-mates.",
  );
  const band = page.getByLabel("Probability band");
  console.log(`C10-a bands: ${JSON.stringify(await band.locator("option").allTextContents())}`);
  await band.selectOption({ label: "highly likely (0.8–0.9)" });
  const evidence = page.getByRole("combobox", { name: "Add supporting evidence" });
  await evidence.fill("Vance");
  await page.getByRole("option").filter({ hasText: /Vance, Callum/ }).first().click();
  await evidence.fill("Thackwray");
  await page.getByRole("option").filter({ hasText: /Thackwray/ }).first().click();
  await page.waitForTimeout(1000);
  await shot(page, "CAP-A2-C10-a");
});

test("CAP-M2", async ({ page }) => {
  await freshCase(page);
  await page.waitForTimeout(2000);
  await shot(page, "CAP-M2");
});

test("CAP-M6", async ({ page }) => {
  // The dataset is OFFICIAL throughout (ADR-120 Amendment 16): no link is above the analyst's
  // clearance to be shown absent, so the module's trust screen is the History panel.
  await principalStar(page);
  await rail(page, "History").click();
  await page.waitForTimeout(3000);
  await shot(page, "CAP-M6");
});

test("CAP-A2-C11", async ({ page }) => {
  await principalStar(page);
  await canvas(page).press("Escape");
  await page.getByRole("button", { name: /^Export/ }).first().click();
  const drawer = page.getByRole("dialog", { name: "Export" });
  await drawer.getByRole("button", { name: "Export", exact: true }).click();
  // The S2 report is held until a justification and the originator's reference are given.
  await expect(drawer.getByText(/consult originator/).first()).toBeVisible();
  await page.waitForTimeout(1000);
  await shot(page, "CAP-A2-C11-a");
  await drawer.getByLabel("Justification").fill("Briefing the regional intelligence unit on the Wing F supply route.");
  await drawer.getByLabel("Originator reference").fill("FMS-ORIG-2026-041");
  await drawer.getByRole("button", { name: "Export", exact: true }).click();
  await page.waitForTimeout(5000);
  console.log(`C11 after export: ${(await drawer.textContent())?.slice(0, 600)}`);
  await shot(page, "CAP-A2-C11-b");
});

test("CAP-A2-C11-c", async ({ page }) => {
  // The case's open questions: a gap recorded against the assessment, shown open in the Inspector.
  await principalStar(page);
  await canvas(page).press("Escape");
  await page.getByRole("button", { name: "Add judgement, gap or assumption" }).click();
  await page.getByRole("tab", { name: "Gap" }).or(page.getByRole("button", { name: "Gap", exact: true })).first().click();
  const question = page.getByRole("textbox", { name: "Question", exact: true });
  await question.fill("Who receives the packages on the far side of the wall?");
  await page.getByRole("button", { name: /^Save gap/ }).click();
  await page.waitForTimeout(2500);
  await shot(page, "CAP-A2-C11-c");
});

test("CAP-M5-a", async ({ page }) => {
  await freshCase(page);
  await throwOverTrend(page);
  await shot(page, "CAP-M5-a");
});

test("CAP-M5-b", async ({ page }) => {
  // The owner's ruling of 27 October 2026: no board is registered for the PID, so the viewer's
  // part of the module shows the Figures the viewer reads, not a dashboard.
  await signIn(page, "viewer");
  await openCase(page);
  await page.waitForTimeout(4000);
  await shot(page, "CAP-M5-b");
  await shot(page, "CAP-A2-C10-c");
});
