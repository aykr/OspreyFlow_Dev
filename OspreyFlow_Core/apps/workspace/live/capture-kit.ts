// The helpers the deployed-Glass capture specs share (`pid-capture.spec.ts`, `ledger-capture.spec.ts`):
// signing in as a demo persona through the deployment's own identity provider, opening a case,
// reaching a Monitoring tab, and writing a shot. **This is not a spec, and it registers no test.**
// Import helpers from here, never from a `*.spec.ts` file: a spec registers its tests when it is
// imported, so importing one runs its whole capture suite against whatever deployment it points at
// (29 October 2026: sixteen screenshots overwritten, a trend saved twice, a pack item added).
//
// Nothing here is mocked. Each helper drives the real Glass as a person would, and reads a persona's
// password from the deployment's own env file without ever printing or logging it.
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Locator, type Page } from "@playwright/test";

import { isRunNowRequest, runNowOutcome } from "./run-wait";

const HERE = dirname(fileURLToPath(import.meta.url));
/** `OspreyFlow_Core`, the checkout the capture specs run from. */
export const CORE = join(HERE, "../../..");
/** The owner's presentations folder beside the checkout (git-excluded, never committed). */
export const PRESENTATIONS = join(CORE, "../OspreyFlow_presentations");

export type Persona = "analyst" | "engineer" | "viewer" | "admin";

/** The four demo accounts (`DEMO_GUIDE.md` §8a) and the env-file line holding each password. */
export const ACCOUNTS: Record<Persona, { username: string; secret: string }> = {
  analyst: { username: "osprey-demo-analyst", secret: "OSPREY_DEMO_ANALYST_PASSWORD" },
  engineer: { username: "osprey-demo-engineer", secret: "OSPREY_DEMO_ENGINEER_PASSWORD" },
  viewer: { username: "osprey-demo-report-viewer", secret: "OSPREY_DEMO_REPORT_VIEWER_PASSWORD" },
  admin: { username: "osprey-demo-admin", secret: "OSPREY_DEMO_ADMIN_PASSWORD" },
};

/** The persona's password, read from the deployment's own env file and never printed or logged. */
export function passwordOf(envFile: string, persona: Persona): string {
  const name = ACCOUNTS[persona].secret;
  for (const line of readFileSync(envFile, "utf-8").split("\n")) {
    if (line.startsWith(`${name}=`)) return line.slice(name.length + 1).replace(/^"|"$/g, "");
  }
  throw new Error(`${name} is not in the deployment's env file`);
}

/** Every shot in the light theme, whatever the browser profile last chose. */
export async function lightTheme(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("ospreyflow.theme", "light");
    } catch {
      /* storage may be blocked; the attribute below still decides this page */
    }
    document.documentElement.setAttribute("data-theme", "light");
  });
}

/** Through the deployment's own sign-in page, as a person would. Tokens live in memory only, so a
 * shot never reloads the page after this. */
export async function signInAs(page: Page, envFile: string, persona: Persona): Promise<void> {
  await page.goto("/");
  const glass = new URL(page.url()).hostname;
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.locator("#username").fill(ACCOUNTS[persona].username);
  await page.locator("#password").fill(passwordOf(envFile, persona));
  await page.locator("#kc-login").click();
  // Back on the Glass's own address, once it has taken the code out of the address bar.
  await page.waitForURL((url) => url.hostname === glass && !url.searchParams.has("code"));
}

/** Opens a case by its name in the case switcher, or from the case picker on first entry. On a
 * deployment holding several cases, sign-in lands on Home, whose recent list need not name this
 * one: Open Glass is taken first, then the picker or the switcher. */
export async function openCaseNamed(page: Page, name: string): Promise<void> {
  const picker = page.getByRole("button", { name, exact: true });
  const switcher = page.getByRole("button", { name: /^Case:/ });
  const openGlass = page.getByRole("button", { name: /^Open Glass/ });
  await expect(picker.or(switcher).or(openGlass).first()).toBeVisible();
  if (!(await picker.first().isVisible()) && (await openGlass.isVisible())) await openGlass.click();
  await expect(picker.or(switcher).first()).toBeVisible();
  if (!(await picker.first().isVisible())) await switcher.click();
  await page.getByRole("button", { name, exact: true }).first().click();
  await expect(page.getByRole("button", { name: /^Case:/ })).toContainText(name);
}

/** Writes the page as `<dir>/<id>.png`, making the folder when it is missing. */
export async function shotInto(page: Page, dir: string, id: string): Promise<void> {
  mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: join(dir, `${id}.png`) });
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

/** A left-rail entry by its name. The rail names an entry with an open count as "<name>, N open",
 * so the match is not exact. */
export const rail = (page: Page, name: string) =>
  page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name });

export type MonitoringTab =
  | "Queue"
  | "Rules"
  | "Watches"
  | "Lists"
  | "Connection strength"
  | "Held rows"
  | "Audit";

/** Rules and Monitoring on one of its tabs (ADR-146 decision 2; the Monitoring place's tabs before
 * it, by their old names: Queue and Watches' inbox are *Alerts*; Rules, Watches' hotlists and Lists are
 * *What raises alerts*; Audit is *Changes*). Connection strength stayed in the Glass, under the
 * rail's More. Reached through the place switcher, as a person reaches it. */
export async function monitoringTab(page: Page, tab: MonitoringTab): Promise<void> {
  if (tab === "Connection strength") {
    await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "More" }).click();
    await page.getByRole("group", { name: "More" }).getByRole("button", { name: "Connection strength" }).click();
    await expect(page.getByRole("region", { name: "Connection strength" })).toBeVisible();
    await page.waitForTimeout(2500);
    return;
  }
  await page.getByRole("navigation", { name: "Places" }).getByRole("button", { name: /^Rules and Monitoring/ }).click();
  const place = page.getByRole("region", { name: "Rules and Monitoring" });
  await expect(place).toBeVisible();
  const now: Record<Exclude<MonitoringTab, "Connection strength">, string> = {
    Queue: "Alerts", Rules: "What raises alerts", Watches: "What raises alerts", Lists: "What raises alerts",
    "Held rows": "Held rows", Audit: "Changes",
  }; // prettier-ignore
  await place.getByRole("tab", { name: now[tab], exact: true }).click();
  await page.waitForTimeout(2500);
}

/** The queue's row whose summary matches `summary`, opened; returns the alert's explanation. The
 * row's name is "Open alert: <severity> severity, <title> — <summary>" (WCAG 2.5.3). */
export async function openQueuedAlert(page: Page, summary: RegExp) {
  const queue = page.getByRole("region", { name: "Alert queue" });
  const row = queue.getByRole("button", { name: /^Open alert: / }).filter({ hasText: summary }).first();
  await expect(row).toBeVisible({ timeout: 60_000 });
  await row.click();
  const detail = page.getByRole("region", { name: "What fired this alert" });
  await expect(detail).toBeVisible();
  await page.waitForTimeout(1500);
  return detail;
}

/** Shows the queue's closed alerts as well as the open ones. */
export async function queueShowsAll(page: Page): Promise<void> {
  await page.getByRole("combobox", { name: "Show which alerts" }).selectOption("all");
  await page.waitForTimeout(2000);
}

export type ClosingReasonLabel = "True match" | "False positive" | "Duplicate" | "No further action" | "Referred";

/** Closes (or, for a high-severity alert a second person may read, proposes closing) the opened
 * alert with one of the owner's five reasons and words. Never "True match" in a rehearsal: a true
 * match confirms the alert's node and the rehearsal reset then refuses the load. */
export async function closeOpenedAlert(page: Page, reason: Exclude<ClosingReasonLabel, "True match">, words: string) {
  const detail = page.getByRole("region", { name: "What fired this alert" });
  await detail.getByRole("radiogroup", { name: "Closing reason" }).getByRole("radio", { name: reason }).check();
  await detail.getByRole("textbox", { name: "Why, in words: the reason for closing" }).fill(words);
  await detail.getByRole("button", { name: /^(Close the alert|Propose the close)$/ }).click();
  await expect(detail.getByRole("status")).toBeVisible({ timeout: 30_000 });
  console.log(`closed: ${await detail.getByRole("status").textContent()}`);
  await page.waitForTimeout(1500);
}

/** The case's Figures (the Reports view until ADR-145 Amendment 4 decision 8) on one of its tabs. */
export async function reportsTab(page: Page, tab: string): Promise<void> {
  await page.getByRole("button", { name: "Figures", exact: true }).click();
  await page.getByRole("tab", { name: tab, exact: true }).click();
  await page.waitForTimeout(4000);
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

/** Presses a pipeline's **Run now** and waits for **that run's own** answer: the run-now request is
 * answered only once its run has finished, with its own load id and counts (`run-wait.ts`). Never
 * the Publish screen's runs list, which already shows earlier runs' "Succeeded:" before this one
 * finishes (step 9d finding 7). Returns the run's outcome in words. */
export async function runNowAndWait(page: Page, runNow: Locator, timeout = 300_000): Promise<string> {
  const own = page.waitForResponse((r) => isRunNowRequest(r.request().method(), r.url()), { timeout });
  await runNow.click();
  const response = await own;
  const body: unknown = await response.json().catch(() => null);
  return runNowOutcome(response.status(), body);
}
