// Operation Ledger's monitoring week (A1 to A4; `DEMO_GUIDE.md` §8b; ADR-108 Amendment 5), captured
// from the deployed Glass over the synthetic Ledger case. Every shot is a function of a named case
// state; the "ledger …" tests put that state there as the presenter would (a list refresh, a
// hotlist, two rules, a close, a pack item), and the CAP-L tests shoot it. Nothing is mocked and no
// image is edited. The week's own load is not here: the walkthrough has the data engineer build its
// pipeline in the Ingest Studio by hand, so the presenter does that between "ledger 1b" and
// CAP-L-A1-c (`CAPTURE_RUNBOOK_v4.md`). See `ledger-capture.config.ts` for how to run it, one test
// at a time. The shared helpers are in `capture-kit.ts`; never import from this file (it would
// run it).
import { execFileSync } from "node:child_process";
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
  reportsTab,
  scrollAllToTop,
  shotInto,
  signInAs,
  type Persona,
} from "./capture-kit";

const SCREENS =
  process.env.OSPREY_LEDGER_CAPTURE_SCREENS ?? join(PRESENTATIONS, "operation_ledger_demo/screens");
const ENV_FILE =
  process.env.OSPREY_CAPTURE_ENV ?? join(CORE, "deploy/generated/local-lite/deployment.env");

const CASE_NAME = "Operation Ledger (synthetic demo)";
/** The pipeline the data engineer builds over the week's file; its name is the presenter's. */
const WEEK_PIPELINE = process.env.OSPREY_LEDGER_WEEK_PIPELINE ?? "Weekly transactions";
const PACK = "Operation Ledger — monitoring week";

test.skip(
  process.env.OSPREY_LEDGER_CAPTURE !== "1",
  "captures a deployment; opt in with OSPREY_LEDGER_CAPTURE=1",
);

test.beforeEach(async ({ page }) => {
  await lightTheme(page);
});

/** A value of the Ledger's monitoring week, read from its generator (`ledger_monitoring.py`). */
function fromWeek(name: string): string {
  const out = execFileSync(
    join(CORE, ".venv/bin/python"),
    ["-c", `from demo_fixtures import ledger_monitoring as m; print(m.${name})`],
    { cwd: CORE, env: { ...process.env, PYTHONPATH: ".:packages" } },
  )
    .toString()
    .trim();
  if (!out) throw new Error(`ledger_monitoring.${name} is empty`);
  return out;
}

async function freshCase(page: Page, persona: Persona = "analyst"): Promise<void> {
  await signInAs(page, ENV_FILE, persona);
  await openCaseNamed(page, CASE_NAME);
  await dismissWelcome(page);
}

const shot = (page: Page, id: string) => shotInto(page, SCREENS, id);

/** The list's row in the Lists tab, refreshed with its own *Refresh now*; returns what it said. */
async function refreshList(page: Page): Promise<string> {
  const listName = fromWeek("UK_LIST_NAME");
  await page.getByRole("button", { name: `Refresh now: ${listName}` }).click();
  const said = page.getByRole("status").first();
  await expect(said).toBeVisible({ timeout: 120_000 });
  await page.waitForTimeout(2000);
  return (await said.textContent()) ?? "";
}

/** Deploys one template with its name and the fields to change, as the case's Author. */
async function deployTemplate(page: Page, template: string, name: string, fields: Record<string, string>) {
  await page.getByRole("button", { name: `Use the template: ${template}` }).click();
  const form = page.getByRole("form", { name: "Deploy a rule" });
  await form.getByRole("textbox", { name: "Rule name" }).fill(name);
  for (const [label, value] of Object.entries(fields)) await form.getByLabel(label, { exact: true }).fill(value);
  const runs = form.getByRole("combobox", { name: "When the rule runs" });
  if (await runs.isVisible().catch(() => false)) await runs.selectOption("post_commit");
  await form.getByRole("button", { name: "Deploy", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: name })).toBeVisible({ timeout: 60_000 });
}

// --- Before the act -------------------------------------------------------------------------------

test("ledger 0: the admin reads the UK Sanctions List's first version (CAP-L-A0-a, CAP-L-A0-b)", async ({ page }) => {
  await freshCase(page, "admin");
  await monitoringTab(page, "Lists");
  console.log(`list v1: ${await refreshList(page)}`);
  await scrollAllToTop(page);
  await shot(page, "CAP-L-A0-a");
  // OFSI marked as reading a closed list (ADR-133 Amendment 6): the subscribe form says so when its
  // connector is chosen. Nothing is subscribed: the form is never submitted.
  const form = page.getByRole("form", { name: "Subscribe to a list" });
  await form.getByRole("combobox", { name: "Connector" }).selectOption("ofsi_consolidated");
  await expect(form.getByText(/^Closed list: /)).toBeVisible();
  await form.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1000);
  await shot(page, "CAP-L-A0-b");
});

// --- 1. After the SAR ---------------------------------------------------------------------------

test("ledger 1a: the analyst hotlists Carter's account (CAP-L-A1-a)", async ({ page }) => {
  await freshCase(page);
  await monitoringTab(page, "Watches");
  await page.getByLabel("Identifier", { exact: true }).fill(fromWeek("HOTLISTED_ACCOUNT"));
  await page.getByLabel("Review date").fill("2027-01-31");
  await page.getByRole("button", { name: "Add to hotlist" }).click();
  await page.waitForTimeout(2500);
  console.log(`hotlist: ${await page.locator(".hotlist-panel").textContent()}`);
  await shot(page, "CAP-L-A1-a");
});

test("ledger 1b: the case's Author deploys the two templates (CAP-L-A1-b)", async ({ page }) => {
  // Deploying a case rule needs the case's Author level; on a demonstration deployment that is the
  // demo admin, who also holds the Analyst role. The demo analyst is an Editor of the case.
  await freshCase(page, "admin");
  await monitoringTab(page, "Rules");
  const rapid = fromWeek("RAPID_MOVEMENT_NAME");
  const circle = fromWeek("CIRCULAR_FLOW_NAME");
  for (const name of [rapid, circle]) {
    if (await page.getByRole("button", { name: `Retire ${name}` }).isVisible().catch(() => false)) {
      throw new Error(`"${name}" is already deployed: retire it first (a rule raises a finding once)`);
    }
  }
  await deployTemplate(page, "Rapid movement", rapid, {});
  await deployTemplate(page, "Circular flow", circle, { "Within (days)": "7" });
  console.log(`rules: ${await page.getByRole("list", { name: "Rules" }).textContent()}`);
  await scrollAllToTop(page);
  await shot(page, "CAP-L-A1-b");
});

// --- 2. The next weekly export (the presenter releases it; the engineer builds and runs it) -------

test("CAP-L-A1-c: Checks on load and Verify on the week's pipeline", async ({ page }) => {
  // Reads only: the checks are not saved and Verify is a dry run. Taken after the engineer has
  // built the pipeline over the week's file and before it is run (its name: OSPREY_LEDGER_WEEK_PIPELINE).
  test.setTimeout(600_000);
  await signInAs(page, ENV_FILE, "engineer");
  await page.getByRole("button", { name: /Open Ingest Studio/ }).or(page.getByRole("link", { name: /Open Ingest Studio/ })).first().click();
  await page.getByRole("button", { name: CASE_NAME, exact: true }).click();
  await page.getByRole("button", { name: new RegExp(`^Open ${WEEK_PIPELINE}`) }).click();
  await page.getByRole("button", { name: "Checks on load", exact: true }).click();
  await expect(page.getByRole("table", { name: "Rules this pipeline may be checked by" })).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(1000);
  await shot(page, "CAP-L-A1-c");
  await page.getByRole("button", { name: "← Back to the pipeline" }).click();
  await page.getByRole("button", { name: "Verify", exact: true }).click();
  await page.getByRole("button", { name: "Run verify" }).click();
  const would = page.getByRole("heading", { name: "Alerts this sample would raise" });
  await expect(would).toBeVisible({ timeout: 240_000 });
  await would.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1500);
  await shot(page, "CAP-L-A1-d");
});

test("CAP-L-A1-e: the queue after the week loads, the pass-through opened", async ({ page }) => {
  await freshCase(page);
  await monitoringTab(page, "Queue");
  console.log(`queue: ${await page.getByRole("region", { name: "Alert queue" }).textContent()}`);
  await openQueuedAlert(page, /pass-through/);
  await shot(page, "CAP-L-A1-e");
});

// --- 3. A list update ----------------------------------------------------------------------------

test("ledger 3: the admin refreshes the list after its update is released (CAP-L-A3-a)", async ({ page }) => {
  await freshCase(page, "admin");
  await monitoringTab(page, "Lists");
  console.log(`list v2: ${await refreshList(page)}`);
  await scrollAllToTop(page);
  await shot(page, "CAP-L-A3-a");
});

test("CAP-L-A3-b: the screening alert on an existing customer", async ({ page }) => {
  await freshCase(page);
  await monitoringTab(page, "Queue");
  const detail = await openQueuedAlert(page, /sanctions list|RUIZ, Sofia/);
  console.log(`K1: ${(await detail.textContent())?.slice(0, 600)}`);
  await shot(page, "CAP-L-A3-b");
});

// --- 4. Close and report -------------------------------------------------------------------------

test("ledger 4a: the analyst adds the pass-through to the pack while it is open", async ({ page }) => {
  // The pack's alert picker offers the queue's open, claimed and closing alerts only, so the alert
  // goes into the pack first and its item is refreshed after the close (ADR-134 decision 1: "so an
  // alert added while open can say how it was closed").
  await freshCase(page);
  await reportsTab(page, "Packs");
  const pack = page.getByRole("button", { name: new RegExp(`^${PACK}`) }).first();
  if (!(await pack.isVisible().catch(() => false))) {
    await page.getByLabel("New pack title").fill(PACK);
    await page.getByRole("button", { name: "Create pack" }).click();
    await page.waitForTimeout(2500);
  }
  await pack.click();
  await page.getByLabel("Item kind").selectOption("alert");
  const options = await page.getByLabel("Alert", { exact: true }).locator("option").allTextContents();
  console.log(`alerts offered: ${JSON.stringify(options)}`);
  const r1 = options.find((o) => /pass-through/.test(o));
  if (!r1) throw new Error("R1 (the pass-through) is not offered for the pack");
  await page.getByLabel("Alert", { exact: true }).selectOption({ label: r1 });
  await page.getByRole("button", { name: "Add item" }).click();
  await page.waitForTimeout(3000);
});

test("ledger 4b: the analyst closes the pass-through as Referred (CAP-L-A4-a)", async ({ page }) => {
  // Medium severity: closed by one person. Never True match in a rehearsal: it confirms the alert's
  // own node, and reverting the week's load then refuses.
  await freshCase(page);
  await monitoringTab(page, "Queue");
  await openQueuedAlert(page, /pass-through/);
  await closeOpenedAlert(page, "Referred", "To the MLRO: a further SAR on the Monzo account, citing the circle through Crescent.");
  await shot(page, "CAP-L-A4-a");
});

test("CAP-L-A4-b: the pack item refreshed, saying how the alert was closed", async ({ page }) => {
  await freshCase(page);
  await reportsTab(page, "Packs");
  await page.getByRole("button", { name: new RegExp(`^${PACK}`) }).first().click();
  await page.waitForTimeout(2500);
  const refresh = page.getByRole("button", { name: "Refresh", exact: true });
  if (await refresh.first().isVisible().catch(() => false)) await refresh.last().click();
  await page.waitForTimeout(3000);
  await scrollAllToTop(page);
  await shot(page, "CAP-L-A4-b");
});
