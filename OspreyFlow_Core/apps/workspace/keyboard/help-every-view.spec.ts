// The rail's Help (?) opens its panel from every view of the real Glass, by keyboard (ADR-115 E6, ADR-145
// Amendment 12; rule 13). CARRIES 224 (the owner's demo walk-through, 13 November 2026): Help opened the Welcome
// panel in the Graph view alone and looked dead in Map, Reports, Ownership and the others. `shell.spec.ts` proves
// Help over the top bar's harness, which has one view; this drives the real `/` (signed in through
// `fakeIdentityProvider.ts`, a case kept in the tab, the Conduit faked with what the workspace reads), goes to each
// view the switch and More views offer, presses Help on the rail by keyboard, and holds that the panel opens there,
// takes focus, and closes again by Help.
import { expect, test, type Page } from "@playwright/test";

import { HELP_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";
import { API, fakeIdentityProvider } from "./fakeIdentityProvider";

const REGISTRY = "HELP_ACTIONS";
const CASE = "case-1";
// Every view the switch and More views can offer (`shell/railLayout.ts`'s VIEW_LABELS), each by the rights that
// offer it; the Graph first, as the panel's own place.
const VIEWS = ["Graph", "Map", "Drawing board", "Reports", "Matrix", "Figures", "Ownership", "Connection strength"];
const RIGHTS = ["investigate", "trace_ownership", "read_reports", "ask_model", "read_alert_queue", "view_dashboards", "read_strength"];

async function signedInToTheCase(page: Page): Promise<void> {
  await fakeIdentityProvider(page, { session: true, silentRounds: 0 });
  const answer = (path: string, json: unknown) => page.route(`${API}${path}`, (route) => route.fulfill({ json }));
  await answer("/v1/me", { id: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-a", roles: [], receivable_handling_codes: [] });
  await answer("/v1/me/rights", { rights: RIGHTS });
  await answer("/v1/ontology", { version: 1, entity_types: [{ name: "Person", pole_class: "person", channel: "cyan", shape: "circle", properties: [] }], edge_types: [] });
  await answer("/v1/map/providers", { default: "none", providers: [] });
  await answer("/v1/handling-scheme", { classification: ["OFFICIAL"], handling_codes: {} });
  const theCase = { id: CASE, name: "Kestrel case", level: "editor", created_at: "2026-11-01T09:00:00Z", created_by: "analyst-1" };
  await answer("/v1/investigations", [theCase]);
  await answer(`/v1/investigations/${CASE}`, theCase);
  await answer(`/v1/investigations/${CASE}/datasets`, []);
  await page.addInitScript(() => {
    sessionStorage.setItem("ospreyflow.investigationId", "case-1");
    sessionStorage.setItem("ospreyflow.place", "case");
    // Closed once before, so it is not open at sign-in: Help is what opens it.
    localStorage.setItem("ospreyflow.welcome-closed.analyst-1", "1");
  });
  await page.goto("/");
  await expect(page.getByRole("application", { name: "Network canvas" })).toBeVisible({ timeout: 20_000 });
}

const MORE = ["Matrix", "Figures", "Ownership", "Connection strength"];

/** Goes to a view by keyboard (the switch's own button, or More views then the view); false when it is not offered.
 * More views is a dropdown beside the switch, its button named by the view it has open, if any. */
async function goTo(page: Page, name: string): Promise<boolean> {
  if (!MORE.includes(name)) {
    const button = page.getByRole("group", { name: "View" }).getByRole("button", { name, exact: true });
    if ((await button.count()) === 0) return false;
    await button.focus();
    await page.keyboard.press("Enter");
    await expect(button).toHaveAttribute("aria-pressed", "true");
    return true;
  }
  const more = page.getByRole("banner").getByRole("button", { name: new RegExp(`^(More views|${MORE.join("|")})`) });
  if ((await more.count()) === 0) return false;
  await more.first().focus();
  await page.keyboard.press("Enter");
  const item = page.getByRole("button", { name, exact: true }).and(page.locator(".menu-panel__item"));
  if ((await item.count()) === 0) {
    await page.keyboard.press("Escape");
    return false;
  }
  await item.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("banner").getByRole("button", { name: new RegExp(`^${name}`) })).toBeVisible();
  return true;
}

test("the rail's Help opens and closes its panel by keyboard from every view of the real Glass", async ({ page }) => {
  test.setTimeout(120_000);
  await signedInToTheCase(page);
  const help = page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Help" });
  const panel = page.getByRole("dialog", { name: "Welcome back" });
  const offered: string[] = [];
  for (const view of VIEWS) {
    if (!(await goTo(page, view))) continue;
    offered.push(view);
    await expect(panel, `the panel was open in ${view} before Help`).toHaveCount(0);
    await help.focus();
    await page.keyboard.press("Enter");
    await expect(panel, `Help did not open its panel in ${view}`).toBeVisible();
    await expect(panel, `the panel opened in ${view} did not take focus`).toBeFocused();
    await help.focus();
    await page.keyboard.press("Enter");
    await expect(panel, `Help did not close its panel in ${view}`).toHaveCount(0);
  }
  // Every view, so a switch that stopped offering one cannot pass this by skipping it.
  expect(offered).toEqual(VIEWS);
  registerCovered(REGISTRY, "open-help-from-every-view-by-keyboard");
});

test("every registered Help action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, HELP_ACTIONS);
});
