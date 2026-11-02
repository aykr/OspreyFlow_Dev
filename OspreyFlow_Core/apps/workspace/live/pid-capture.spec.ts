// The Prison Intelligence demo's screen captures (Brief 3 Part C), against the deployed Glass and
// the loaded synthetic PID case. Every shot is a function of a named case state that this file
// puts there itself; nothing is mocked and no image is edited. See `pid-capture.config.ts` for how
// to run it, and `CAPTURE_RUNBOOK_v4.md` beside the demo script for the order and the deployment
// state each shot needs. Each PNG is named exactly its capture id and written to the demo's
// `screens/` folder, or to `OSPREY_PID_CAPTURE_SCREENS` when it is set (the second brand's shots).
// The shared helpers are in `capture-kit.ts`; never import from this file (it would run it).
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import {
  CORE,
  PRESENTATIONS,
  closeOpenedAlert,
  dismissWelcome,
  lightTheme,
  monitoringTab,
  openCaseNamed,
  openQueuedAlert,
  rail,
  reportsTab,
  runNowAndWait,
  scrollAllToTop,
  shotInto,
  signInAs,
  type Persona,
} from "./capture-kit";

const SCREENS =
  process.env.OSPREY_PID_CAPTURE_SCREENS ?? join(PRESENTATIONS, "prison_intelligence_demo/screens");
const ENV_FILE =
  process.env.OSPREY_PID_CAPTURE_ENV ?? join(CORE, "deploy/generated/local-lite/deployment.env");

export const CASE_NAME = "Prison Intelligence Dataset (synthetic demo)";

/** A value of the demo plan or its monitoring batches, read from the generator itself (Python), so
 * no number is written in this file: Brief 1's J2 check refuses any file of the repository that
 * writes the coordinator's number, so that a search for it finds the PID's data and nothing else. */
function fromPlan(expression: string): string[] {
  return execFileSync(
    join(CORE, ".venv/bin/python"),
    [
      "-c",
      "from demo_fixtures import pid_plan, pid_monitoring; plan = pid_plan.build_plan('demo')\n" +
        `for line in (${expression}): print(line)`,
    ],
    { cwd: CORE, env: { ...process.env, PYTHONPATH: ".:packages" } },
  )
    .toString()
    .trim()
    .split("\n");
}

/** The coordinator's number, as the plan writes it (`07`… national form) and as it is stored
 * (`+44`…). */
function coordinatorNumber(): { national: string; international: string } {
  const e = "plan.entity('number:coordinator').properties";
  const [national, international] = fromPlan(`${e}['value_raw'], ${e}['value_normalised']`);
  if (!national || !international) throw new Error("the plan gave no coordinator's number");
  return { national, international };
}

/** The number on the seized handset that the PIN first contacts reach (S1's subject), stored form. */
function unownedNumber(): string {
  const [number] = fromPlan("[pid_monitoring.EXPECTED_ALERTS[2].number]");
  if (!number) throw new Error("the monitoring batches gave no rule-alert number");
  return number;
}

test.skip(
  process.env.OSPREY_PID_CAPTURE !== "1",
  "captures the owner's deployment; opt in with OSPREY_PID_CAPTURE=1",
);

test.beforeEach(async ({ page }) => {
  await lightTheme(page);
});

/** Signs in as the persona through the deployment's own sign-in page. */
export async function signIn(page: Page, persona: Persona): Promise<void> {
  await signInAs(page, ENV_FILE, persona);
}

/** Opens the PID case (or another by name). */
export async function openCase(page: Page, name = CASE_NAME): Promise<void> {
  await openCaseNamed(page, name);
}

export async function shot(page: Page, id: string): Promise<void> {
  await shotInto(page, SCREENS, id);
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
  // The case's saved working set arrives after the page draws: checked at once, Clear view was still
  // disabled and the saved nodes landed after it (357 of them, 1 November 2026). So it is checked
  // again until the canvas reads empty.
  await expect(counts(page)).toBeVisible();
  await page.waitForTimeout(3000);
  for (let attempt = 0; attempt < 3; attempt++) {
    if (/^0 nodes/.test((await counts(page).textContent()) ?? "")) break;
    if (await clear.isEnabled().catch(() => false)) {
      await clear.click();
      await page.getByRole("button", { name: /^Clear all/ }).click();
    }
    await page.waitForTimeout(3000);
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
  // OSPREY_PID_COHORT_LIST is the demo's 40-identifier list (`pid_files.cohort_list`, script J3:
  // 37 found, 3 match nothing, 1 repeated), not the scale cohort's 3,000: those are in another case.
  test.setTimeout(900_000);
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
  // No community grouping (script v3, J3): grouped, the 11 links folded into the clusters and the
  // slide read as nodes with no links (found reviewing the deck, 1 November 2026).
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
  // The pack a presenter makes in rehearsal; made here when the deployment has none yet.
  const pack = page.getByRole("button", { name: /^Wing F supply route/ }).first();
  if (!(await pack.isVisible().catch(() => false))) {
    await page.getByLabel("New pack title").fill("Wing F supply route");
    await page.getByRole("button", { name: "Create pack" }).click();
    await page.waitForTimeout(2500);
  }
  await pack.click();
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
  const cadence = page.getByLabel("Run on a schedule (how often)");
  console.log(`V6 cadences: ${JSON.stringify(await cadence.locator("option").allTextContents())}`);
  await cadence.selectOption("weekdays");
  await page.getByLabel("At (time)", { exact: true }).fill("07:30");
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
  // A published recipe opens on its Publish screen; a draft opens on its canvas first. There the
  // first "Publish" is the pipeline's Publish stage, which only moves to the Publish screen; the
  // Publish button on that screen is what publishes it. On a deployment whose recipes were all
  // published in earlier rehearsals the second press was never needed (found capturing a fresh
  // GOV.UK-brand deployment, 31 October 2026).
  try {
    await run.waitFor({ timeout: 10_000 });
  } catch {
    await publish.click();
    try {
      await run.waitFor({ timeout: 10_000 });
    } catch {
      await publish.click();
    }
  }
  // The new run's own answer, never the runs list's older "Succeeded:" (step 9d finding 7).
  const runs = await runNowAndWait(page, run, 240_000);
  await page.waitForTimeout(3000);
  // The Publish screen's own way back to the recipe list, by its exact name: `/Back/` also matched
  // the rail's "Back to the investigation", which left the Studio (31 October 2026).
  await page.getByRole("button", { name: "← Back", exact: true }).click();
  // A pipeline with a canvas (the reports pipeline once published by the fallback) goes back to its
  // canvas, not to the list: its "Pipelines" button is the way to the list (2 November 2026).
  const toList = page.getByRole("button", { name: "Pipelines", exact: true });
  if (await toList.isVisible().catch(() => false)) await toList.click();
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

// --- Chapter 9: a hotlist, a rule and three alerts (script v4; ADR-127 Amendment 41) -----------
// Run in this order, after `--release-batch-2` (which lists all three chapter-9 files): 9a, 9b, C9,
// M4-a, 9c, C9Q-a, 9d, C9S, 9e, C9Q-b. Each "chapter …" test changes the deployment's state as the
// presenter would; each CAP- test only reads and shoots, except where its comment says otherwise.

/** The rule P1 deploys (`pid_monitoring.P1_RULE_NAME`). */
const P1_RULE = "Calls to a number on a seized handset";

/** The incoming folder `pid_files.write_files` writes the chapter-9 files to, as the Conduit sees
 * it: the demo loads them, the seed does not. */
const INCOMING = "/var/lib/osprey/ingest/uploaded/prison-intelligence/incoming";

/** Runs a published pipeline over one of the chapter-9 files from its Publish screen, as the data
 * engineer, and says what its runs list reads afterwards. */
async function loadIncoming(page: Page, open: RegExp, file: string): Promise<void> {
  await studio(page);
  await page.getByRole("button", { name: open }).click();
  const run = page.getByRole("button", { name: "Run now" });
  await run.waitFor();
  await page.getByLabel(/^Source file/).fill(`${INCOMING}/${file}`);
  // The new run's own answer, never the runs list's older "Succeeded" (step 9d finding 7).
  console.log(`${file}: ${await runNowAndWait(page, run)}`);
  await page.waitForTimeout(5000);
}

/** The queue's hotlist rows, newest first (high severity, then newest: `alerts.py`'s order), so
 * `nth(0)` is H2 (the bookings) and `nth(1)` is H1 (batch 2) once both are raised. */
const hotlistRows = (page: Page) =>
  page
    .getByRole("region", { name: "Alert queue" })
    .getByRole("button", { name: /^Open alert: .*Hotlist/ });

async function openHotlistAlert(page: Page, nth: number) {
  const row = hotlistRows(page).nth(nth);
  await expect(row).toBeVisible({ timeout: 60_000 });
  await row.click();
  const detail = page.getByRole("region", { name: "What fired this alert" });
  await expect(detail).toBeVisible();
  await page.waitForTimeout(1500);
  return detail;
}

/** S1's row: its words begin with the number it names (`EXPECTED_ALERTS[2]`). */
const ruleAlertSummary = () => new RegExp(unownedNumber().replace(/[+]/g, "\\+") + ".*within 2 step");

test("chapter 9a: the analyst hotlists the coordinator's number", async ({ page }) => {
  await freshCase(page);
  await monitoringTab(page, "Watches");
  await page.getByLabel("Identifier", { exact: true }).fill(coordinatorNumber().national);
  await page.getByLabel("Review date").fill("2027-01-31");
  await page.getByRole("button", { name: "Add to hotlist" }).click();
  await page.waitForTimeout(2500);
  console.log(`hotlist: ${await page.locator(".hotlist-panel").textContent()}`);
});

test("chapter 9b: the engineer loads batch 2", async ({ page }) => {
  test.setTimeout(600_000);
  await loadIncoming(page, /^Open Seized media/, "pid_seized_comms_batch2.csv");
});

test("CAP-A2-C9", async ({ page }) => {
  // The Watches tab of Monitoring (the rail's Watches entry is gone, the owner's answer of
  // 1 November 2026): the hotlist and its Alert inbox. The alert explains itself (ADR-130 decision
  // 1): the identifier as typed and its review date, and the node it matched with the files and
  // rows that put it there.
  await freshCase(page);
  await monitoringTab(page, "Watches");
  await expect(page.getByText(/^Hotlist: /).first()).toBeVisible({ timeout: 60_000 });
  // The alert's explanation sits below the hotlists, under the fold at 1440 by 900: brought into view
  // so the shot shows it, not only the inbox's heading (2 November 2026); CAP-M4-a keeps the top. It is
  // aligned at the bottom so the hotlist stays in view: under the GOV.UK brand the whole page scrolls,
  // and aligning the inbox's heading at the top showed the footer instead.
  await page.getByRole("button", { name: "Jump into investigation" }).first().evaluate((el) => el.scrollIntoView({ block: "end" }));
  await page.waitForTimeout(1500);
  await shot(page, "CAP-A2-C9");
  await shot(page, "CAP-M4-b");
});

test("CAP-M4-a", async ({ page }) => {
  await freshCase(page);
  await monitoringTab(page, "Watches");
  await page.waitForTimeout(2500);
  await shot(page, "CAP-M4-a");
});

test("chapter 9c: the engineer loads the visit bookings", async ({ page }) => {
  test.setTimeout(600_000);
  await loadIncoming(page, /^Open Visit bookings/, "pid_visit_bookings.csv");
});

test("CAP-A2-C9Q-a", async ({ page }) => {
  // P2: the one queue holds both hotlist alerts; H2 (the bookings, newest) is opened. It is the
  // analyst's alone ("Only its owner") and was raised as the bookings loaded, before the visit.
  await freshCase(page);
  await monitoringTab(page, "Queue");
  console.log(`queue: ${await page.getByRole("region", { name: "Alert queue" }).textContent()}`);
  await openHotlistAlert(page, 0);
  await shot(page, "CAP-A2-C9Q-a");
});

test("chapter 9d: the case's Author writes the rule as a sentence, previews it and deploys it", async ({ page }) => {
  // A rule for the case team needs the case's Author level (ADR-109 ruling 4; the sentence route);
  // the demo analyst is an Editor, and the demo admin, who holds the Analyst role too, is the
  // case's Author. Deployed only after the bookings load: before it, the rule would also flag the
  // coordinator's number as the bookings touch it (ADR-127 Amendment 41, "The order").
  // Shoots CAP-A2-C9R-a (the sentence, its drawn pattern and its preview) before deploying.
  test.setTimeout(600_000);
  await freshCase(page, "admin");
  await monitoringTab(page, "Rules");
  const rules = page.getByRole("list", { name: "Rules" });
  // An active rule offers Retire; a retired one does not.
  if (await page.getByRole("button", { name: `Retire ${P1_RULE}` }).isVisible().catch(() => false)) {
    console.log(`rules: ${await rules.textContent()}`);
    throw new Error(`"${P1_RULE}" is already deployed: retire it first (a rule raises a finding once)`);
  }
  const form = page.getByRole("form", { name: "Write a rule as a sentence" });
  await form.getByRole("combobox", { name: "Subject" }).selectOption("Endpoint");
  await form.getByRole("button", { name: "Add a condition" }).click();
  await form.getByRole("combobox", { name: "Condition 1: property" }).selectOption("endpoint_kind");
  await form.getByRole("combobox", { name: "Condition 1: test" }).selectOption("equals");
  await form.getByRole("combobox", { name: "Condition 1: value" }).selectOption("msisdn");
  await form.getByRole("combobox", { name: "Relationship" }).selectOption("within_steps");
  await form.getByRole("combobox", { name: "Steps" }).selectOption("2");
  await form.getByRole("combobox", { name: "Of a (the type near it)" }).selectOption("Device");
  await form.getByRole("combobox", { name: "Severity" }).selectOption("high");
  await form.getByRole("combobox", { name: "For (scope)" }).selectOption("this_case");
  await form.getByRole("combobox", { name: "Alert goes to (team)" }).selectOption("case");
  await form.getByRole("combobox", { name: "Runs" }).selectOption("post_commit");
  await form.getByRole("button", { name: "Show the drawn pattern" }).click();
  await expect(form.getByRole("region", { name: "The drawn pattern" })).toBeVisible();
  await form.getByRole("button", { name: "Preview on the last 90 days" }).click();
  const preview = form.getByRole("region", { name: "Preview" });
  await expect(preview).toBeVisible({ timeout: 240_000 });
  console.log(`P1 drawn pattern: ${await form.getByRole("region", { name: "The drawn pattern" }).textContent()}`);
  console.log(`P1 preview: ${await preview.textContent()}`);
  await form.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1000);
  await shot(page, "CAP-A2-C9R-a");
  await form.getByRole("textbox", { name: "Name of the sentence rule" }).fill(P1_RULE);
  await form.getByRole("button", { name: "Deploy the sentence" }).click();
  await expect(page.getByRole("status").filter({ hasText: P1_RULE })).toBeVisible({ timeout: 60_000 });
  console.log(`deployed: ${await page.getByRole("status").filter({ hasText: P1_RULE }).textContent()}`);
});

test("CAP-A2-C9S", async ({ page }) => {
  // Checks on load and Verify's would-be alerts, as the data engineer. Shown on the Intelligence
  // reports pipeline, which has a canvas (and so the Checks on load and Verify buttons) since
  // chapter 4: the seed publishes the PIN first contacts pipeline from its recipe with no canvas,
  // so reaching its own Checks on load means Reopen for editing, a new version (not done here).
  // Reads only: the checks are not saved, and Verify is a dry run that writes nothing.
  test.setTimeout(600_000);
  await studio(page);
  await page.getByRole("button", { name: /^Open Intelligence reports/ }).click();
  await page.getByRole("button", { name: "Checks on load", exact: true }).click();
  const table = page.getByRole("table", { name: "Rules this pipeline may be checked by" });
  await expect(table.or(page.getByText(/No rule of this case/)).first()).toBeVisible({ timeout: 60_000 });
  // The Studio has no `main` landmark: waiting on one hung the test for its whole timeout
  // (2 November 2026), so the log reads the checks' own table.
  console.log(`checks: ${await table.or(page.getByText(/No rule of this case/)).first().textContent({ timeout: 10_000 }).catch(() => "")}`.slice(0, 800));
  await page.waitForTimeout(1000);
  await shot(page, "CAP-A2-C9S-a");
  await page.getByRole("button", { name: "← Back to the pipeline" }).click();
  await page.getByRole("button", { name: "Verify", exact: true }).click();
  await page.getByRole("button", { name: "Run verify" }).click();
  const would = page.getByRole("heading", { name: "Alerts this sample would raise" });
  await expect(would).toBeVisible({ timeout: 240_000 });
  await would.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1500);
  console.log(`would raise: ${await would.locator("xpath=../..").textContent()}`.slice(0, 600));
  await shot(page, "CAP-A2-C9S-b");
});

test("chapter 9e: the engineer loads the PIN first contacts", async ({ page }) => {
  test.setTimeout(600_000);
  await loadIncoming(page, /^Open PIN phone first contacts/, "pid_pin_new_contacts.csv");
});

test("CAP-A2-C9Q-b", async ({ page }) => {
  // P1: the rule's alert, S1, for the case team, naming the number Pryce's seized handset called.
  await freshCase(page);
  await monitoringTab(page, "Queue");
  console.log(`queue: ${await page.getByRole("region", { name: "Alert queue" }).textContent()}`);
  const detail = await openQueuedAlert(page, ruleAlertSummary());
  console.log(`S1: ${(await detail.textContent())?.slice(0, 600)}`);
  await shot(page, "CAP-A2-C9Q-b");
});

// --- Chapter 10: closes, the trend and the figures (P3, P4) ---------------------------------------
// After chapter 9, in this order: 10a, 10b, (10c, the open question), C10M-d, C11M, (C10M-e).

test("chapter 10a: the analyst closes H2 as Referred, alone (CAP-A2-C10M-a)", async ({ page }) => {
  // H2 is "Only its owner": its owner closes it with no second person (ADR-133 Amendment 4 item 5).
  await freshCase(page);
  await monitoringTab(page, "Queue");
  await openHotlistAlert(page, 0);
  await closeOpenedAlert(page, "Referred", "To the visits team: the visit goes ahead under closed conditions.");
  await shot(page, "CAP-A2-C10M-a");
});

test("chapter 10b: the analyst proposes S1's close as Referred (CAP-A2-C10M-b)", async ({ page }) => {
  // High severity, for the case team: closing it proposes the close, which waits for a second
  // person (ADR-133 decision 7, stage (d)). Never True match in a rehearsal: the reset then refuses.
  await freshCase(page);
  await monitoringTab(page, "Queue");
  await openQueuedAlert(page, ruleAlertSummary());
  await closeOpenedAlert(page, "Referred", "To the regional intelligence unit for a subscriber check on the number.");
  await shot(page, "CAP-A2-C10M-b");
});

test("chapter 10c, open question 13: the admin approves S1's close as the second person (CAP-A2-C10M-c)", async ({ page }) => {
  // Not part of the script's stage path (the script narrates the approval from a slide). The demo
  // admin holds the Analyst role and is the case's Author, so the Conduit should accept it as the
  // second person (`approve_close` refuses only the proposer); this test is how that is found out.
  // Shoots the approval before and after. Run it only when the owner wants the slide's images.
  await freshCase(page, "admin");
  await monitoringTab(page, "Queue");
  const detail = await openQueuedAlert(page, ruleAlertSummary());
  const approve = detail.getByRole("button", { name: "Approve the close" });
  await expect(approve).toBeVisible();
  await shot(page, "CAP-A2-C10M-c");
  await approve.click();
  await expect(detail.getByRole("status")).toBeVisible({ timeout: 30_000 });
  console.log(`approval: ${await detail.getByRole("status").textContent()}`);
  await page.waitForTimeout(1500);
  await shot(page, "CAP-A2-C10M-c2");
});

/** P3's trend: the case's alerts, counted by week and split by rule (ADR-134 decision 3). */
const ALERT_TREND = "Alerts by rule, weekly";

test("CAP-A2-C10M-d", async ({ page }) => {
  // Saves the trend (a state change chapter 11 needs), once: a second run finds it saved.
  await freshCase(page);
  await reportsTab(page, "Trends");
  await page.getByLabel("Title", { exact: true }).fill(ALERT_TREND);
  await page.getByRole("radiogroup", { name: "What to count" }).getByRole("radio", { name: "Alerts" }).check();
  await page.getByLabel("Interval").selectOption("week");
  await page.getByLabel("Series").selectOption({ label: "By rule" });
  await page.getByRole("button", { name: /^Preview/ }).click();
  await page.waitForTimeout(5000);
  await scrollAllToTop(page);
  await shot(page, "CAP-A2-C10M-d");
  const saved = page.getByRole("region", { name: "Saved trends" });
  if (!((await saved.textContent().catch(() => "")) ?? "").includes(ALERT_TREND)) {
    await page.getByRole("button", { name: "Save trend" }).click();
    await page.waitForTimeout(2500);
  }
});

test("CAP-A2-C11M", async ({ page }) => {
  // Chapter 11's pack: the alert trend and H1, still open, as an `alert` item (ADR-134 decision 1).
  // Adds the two items to the briefing pack (a state change), then shoots the pack.
  await freshCase(page);
  await reportsTab(page, "Packs");
  const pack = page.getByRole("button", { name: /^Wing F supply route/ }).first();
  if (!(await pack.isVisible().catch(() => false))) {
    await page.getByLabel("New pack title").fill("Wing F supply route");
    await page.getByRole("button", { name: "Create pack" }).click();
    await page.waitForTimeout(2500);
  }
  await pack.click();
  await page.getByLabel("Item kind").selectOption("trend");
  await page.getByLabel("Saved trend").selectOption({ label: ALERT_TREND });
  await page.getByRole("button", { name: "Add item" }).click();
  await page.waitForTimeout(3000);
  await page.getByLabel("Item kind").selectOption("alert");
  const options = await page.getByLabel("Alert", { exact: true }).locator("option").allTextContents();
  console.log(`alerts offered: ${JSON.stringify(options)}`);
  const h1 = options.find((o) => /Open/.test(o) && /hotlisted/.test(o));
  if (!h1) throw new Error("H1 (the open hotlist alert) is not offered for the pack");
  await page.getByLabel("Alert", { exact: true }).selectOption({ label: h1 });
  await page.getByRole("button", { name: "Add item" }).click();
  await page.waitForTimeout(3000);
  await scrollAllToTop(page);
  // The new items are the pack's last: on a pack with earlier rehearsals' items the top of the pack
  // showed none of them (2 November 2026), so the alert item is brought into view.
  await page.getByText(/hotlisted identifier appeared/).last().evaluate((el) => el.scrollIntoView({ block: "center" }));
  await page.waitForTimeout(1000);
  await shot(page, "CAP-A2-C11M");
});

test("CAP-A2-C10M-e", async ({ page }) => {
  // P4 on the Superset monitoring board, only where one is registered for this case (dashboards
  // on, a board built as administration guide §12 describes, its account a Viewer of the case).
  // Otherwise skipped: chapter 10 then shows P4 from a slide. The board never counts an "only me"
  // hotlist, so it holds S1 alone.
  await signIn(page, "viewer");
  await openCase(page);
  const boards = rail(page, "Dashboards");
  test.skip(!(await boards.isVisible().catch(() => false)), "no dashboard for this case: P4 is a slide");
  await boards.click();
  await page.waitForTimeout(15_000);
  // Dashboards on, the rail entry is there whether or not a board is registered for this case: the
  // place then says so, and that empty page was shot (2 November 2026). Skip it instead.
  test.skip(
    await page.getByText(/^No dashboard you may open/).isVisible().catch(() => false),
    "no dashboard registered for this case: P4 is a slide",
  );
  await shot(page, "CAP-A2-C10M-e");
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

// --- connection strength (ADR-139; the demo script's strength scene, ADR-127 Amendment 42) --------
//
// Read-only but for CAP-S6, which saves the case's own influencer as its Author (the presenter's
// step; `CAPTURE_RUNBOOK_v4.md` says how to undo it). Every person is found by the prison number
// the plan gives them, never by a name written here.

/** The cast member's prison number and the name the canvas draws ("Family, Given"). */
function castMember(key: string): { number: string; name: string } {
  const e = `plan.entity('${key}').properties`;
  const [number, family, given] = fromPlan(`${e}['prison_number'], ${e}['family_name'], ${e}['given_names']`);
  if (!number || !family) throw new Error(`the plan gave no prison number for ${key}`);
  return { number, name: `${family}, ${given}` };
}

/** Adds each cast member to an empty canvas by their prison number. */
async function addCast(page: Page, keys: string[]): Promise<{ number: string; name: string }[]> {
  const found = keys.map(castMember);
  for (const member of found) {
    await pickFromSearch(page, member.number, /^Person/);
    await page.waitForTimeout(2500);
  }
  return found;
}

/** The Matrix view, two entity rows selected together (the Inspector's "What these two share"). */
async function selectTwoInMatrix(page: Page, first: string, second: string): Promise<void> {
  await page.getByRole("group", { name: "View" }).getByRole("button", { name: "Matrix", exact: true }).click();
  const entities = page.getByRole("grid", { name: /^Entities in this view/ });
  await entities.getByRole("rowheader", { name: new RegExp(first) }).click();
  await entities.getByRole("rowheader", { name: new RegExp(second) }).click({ modifiers: ["Control"] });
  await page.waitForTimeout(2000);
}

/** The Matrix view's link row from `from` of `linkLabel`, selected (the Inspector shows the link). */
async function selectLinkInMatrix(page: Page, linkLabel: string, from: RegExp): Promise<void> {
  await page.getByRole("group", { name: "View" }).getByRole("button", { name: "Matrix", exact: true }).click();
  const links = page.getByRole("grid", { name: /^Links in this view/ });
  const row = links.getByRole("row").filter({ hasText: linkLabel }).filter({ hasText: from }).first();
  await row.getByRole("rowheader").click();
  await page.waitForTimeout(2000);
}

test("CAP-S1", async ({ page }) => {
  // The legend box: the influencers in force (shipped, so "to be confirmed with the client"), the
  // direct link types, and that rarity is worked out over what the reader may see.
  await principalStar(page);
  const legend = page.locator(".canvas-legend");
  await expect(legend.getByRole("list", { name: "Strength influencers" })).toBeVisible();
  console.log(`S1 legend: ${await legend.textContent()}`);
  await shot(page, "CAP-S1");
});

test("CAP-S2", async ({ page }) => {
  // An assault-evidenced conflict drawn stronger: the principal's conflict with calder_1, both of
  // them in assault_1; the Inspector says why, naming the Incident that evidences it.
  await principalStar(page);
  const calder = castMember("calder_1");
  await selectLinkInMatrix(page, "In conflict with", new RegExp(calder.name.split(",")[0]!));
  await onlyPanel(page, "Inspector");
  await page.getByRole("button", { name: "Connection strength", exact: true }).click();
  const why = page.getByRole("list", { name: "What this link's strength rests on" });
  await expect(why).toContainText("evidences it");
  console.log(`S2: ${await why.textContent()}`);
  await shot(page, "CAP-S2");
});

test("CAP-S3", async ({ page }) => {
  // A direct call against a shared address: two men who held the same cell at different times share
  // that address in custody and nothing direct (a), where the principal's calls to the coordinator
  // are a direct link, drawn stronger (b).
  await freshCase(page);
  const [one, two] = await addCast(page, ["cellmate_1", "cellmate_2"]);
  await selectTwoInMatrix(page, one!.name.split(",")[0]!, two!.name.split(",")[0]!);
  await onlyPanel(page, "Inspector");
  await page.getByRole("button", { name: "What these two share", exact: true }).click();
  const shared = page.getByRole("list", { name: "Shared attributes, rarest first" });
  await expect(shared).toBeVisible();
  console.log(`S3-a: ${await shared.textContent()}`);
  await shot(page, "CAP-S3-a");
  await freshCase(page);
  const { national } = coordinatorNumber();
  await pickFromSearch(page, `+44 ${national.slice(1)}`, /^Endpoint/);
  await page.getByRole("button", { name: "Expand" }).first().click().catch(() => undefined);
  await page.waitForTimeout(4000);
  await selectLinkInMatrix(page, "COMMUNICATED_WITH", /PIN-/);
  await page.getByRole("button", { name: "Connection strength", exact: true }).click();
  const why = page.getByRole("list", { name: "What this link's strength rests on" });
  await expect(why).toContainText("a direct link");
  console.log(`S3-b: ${await why.textContent()}`);
  await shot(page, "CAP-S3-b");
});

test("CAP-S4", async ({ page }) => {
  // A rare shared contact ranking above a common one: relay_1 and relay_2 share relay_4 (three
  // people know him) above the principal (linked to many) and the establishment (everyone).
  await freshCase(page);
  const [one, two] = await addCast(page, ["relay_1", "relay_2"]);
  await selectTwoInMatrix(page, one!.name.split(",")[0]!, two!.name.split(",")[0]!);
  await onlyPanel(page, "Inspector");
  await page.getByRole("button", { name: "What these two share", exact: true }).click();
  const shared = page.getByRole("list", { name: "Shared attributes, rarest first" });
  await expect(shared).toBeVisible();
  console.log(`S4: ${await shared.textContent()}`);
  await shot(page, "CAP-S4");
});

test("CAP-S5", async ({ page }) => {
  // The two filters dimming: connection strength at 0.8 (a), then shared-attribute rarity (b).
  await principalStar(page, "Metrics");
  await page.getByRole("button", { name: /^Filter/ }).click();
  await page.getByRole("combobox", { name: "Filter by metric" }).selectOption("connection_strength");
  const threshold = page.getByRole("slider", { name: "Metric value at least" });
  await expect(threshold).toBeVisible();
  await threshold.focus();
  for (let i = 0; i < 60; i++) await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(2000);
  console.log(`S5-a: ${await counts(page).textContent()}`);
  await shot(page, "CAP-S5-a");
  await page.getByRole("combobox", { name: "Filter by metric" }).selectOption("shared_attribute_rarity");
  await expect(threshold).toBeVisible();
  await threshold.focus();
  for (let i = 0; i < 50; i++) await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(2000);
  console.log(`S5-b: ${await counts(page).textContent()}`);
  await shot(page, "CAP-S5-b");
});

test("CAP-S6", async ({ page }) => {
  // A case's own influencer and a rule on strength, as the case's Author (the demo admin): an
  // assault in this case draws a conflict at least 0.95 strong (a, the tab; the legend marks it a
  // case override), and a sentence rule on conflicts reaching 0.95 is previewed (b): it would raise
  // three alerts, the principal and the two men from the assaults, whenever the case was loaded
  // (`test_pid_connection_strength.py`). Changes the case: the runbook says how to undo it.
  test.setTimeout(600_000);
  await freshCase(page, "admin");
  await monitoringTab(page, "Connection strength");
  const tab = page.locator(".strength-panel");
  const form = tab.locator("fieldset").filter({ hasText: "Add an influencer" }).first();
  await form.getByRole("textbox", { name: "Label in the legend" }).fill("Assault in this case");
  await form.getByRole("checkbox", { name: "In conflict with" }).check();
  await form.getByRole("combobox", { name: "When it applies" }).selectOption("record");
  await form.getByRole("combobox", { name: "Kind of record" }).selectOption("Incident");
  await form.getByRole("combobox", { name: "Its property" }).selectOption("category");
  await form.getByRole("checkbox", { name: "assault" }).check();
  await form.getByRole("combobox", { name: "Change" }).selectOption("floor");
  await form.getByRole("spinbutton", { name: "Size" }).fill("0.95");
  await form.getByRole("button", { name: "Add this influencer" }).click();
  await tab.getByRole("button", { name: "Save this case's influencers" }).click();
  await expect(page.getByRole("status").filter({ hasText: "saved" })).toBeVisible();
  await shot(page, "CAP-S6-a");
  await monitoringTab(page, "Rules");
  const rule = page.getByRole("form", { name: "Write a rule as a sentence" });
  await rule.getByRole("combobox", { name: "Subject" }).selectOption("Person");
  // Linked by a conflict first, so the rule judges the people with one, not every person in the case.
  await rule.getByRole("combobox", { name: "Relationship" }).selectOption("linked");
  await rule.getByRole("combobox", { name: "Link type" }).selectOption("IN_CONFLICT_WITH");
  await rule.getByRole("combobox", { name: "Linked to" }).selectOption("Person");
  await rule.getByRole("combobox", { name: "Strength", exact: true }).selectOption("connection_strength");
  await rule.getByRole("combobox", { name: "By (link type, for strength)" }).selectOption("IN_CONFLICT_WITH");
  await rule.getByRole("combobox", { name: "With (type, for strength)" }).selectOption("Person");
  await rule.getByRole("spinbutton", { name: "Reaches" }).fill("0.95");
  await rule.getByRole("combobox", { name: "Severity" }).selectOption("high");
  await rule.getByRole("button", { name: "Preview on the last 90 days" }).click();
  const preview = rule.getByRole("region", { name: "Preview" });
  await expect(preview).toBeVisible({ timeout: 240_000 });
  console.log(`S6 preview: ${await preview.textContent()}`);
  await rule.scrollIntoViewIfNeeded();
  await shot(page, "CAP-S6-b");
});
