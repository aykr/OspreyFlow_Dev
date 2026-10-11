// A keyboard-only walkthrough of the Reports view (ADR-111, `CLAUDE.md` rule 13): change the period
// and download the figures — no `page.mouse`, no `.click()`; each proves its call reached the server.
import { expect, test } from "@playwright/test";

import { REPORTS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "REPORTS_ACTIONS";

const FIGURES = {
  period_weeks: 12, as_of: "2026-10-11", generated_at: "2026-10-11T08:00:00Z", alerts_total: 1,
  alerts_by_week: [{ week_start: "2026-10-05", typology: "kyc_screening", count: 1 }],
  open_by_age: [{ label: "under a day", value: 1 }],
  outcomes: [{ typology: "kyc_screening", open: 1, claimed: 0, true_positive: 0, false_positive: 0 }],
  held: null, kyc: { customers: 0, verified: 0, unverified: 0, by_band: [] },
};  // prettier-ignore

async function serve(page: import("@playwright/test").Page): Promise<string[]> {
  const asked: string[] = [];
  await page.route("**/*/v1/**", async (route) => {
    const url = new URL(route.request().url());
    asked.push(`${url.pathname.replace("/v1/investigations/inv-1/", "")}${url.search}`);
    if (url.pathname === "/v1/reports/dashboards") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([
        { slug: "compliance-board", title: "Compliance board" }, { slug: "fraud-board", title: "Fraud board" }]) });
    }
    const board = /^\/v1\/reports\/dashboards\/([^/]+)\/guest-token$/.exec(url.pathname);
    if (board) {
      return route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ token: "g", uuid: `uuid-${board[1]}`, superset_origin: "http://bi.invalid" }) });
    }
    if (url.pathname.endsWith("/reports/feed")) {
      return route.fulfill({ status: 200, contentType: "text/csv", body: "section,label,typology,week_start,value\n" });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FIGURES) });
  });
  return asked;
}

test("the Dashboards tab is opened and a board chosen by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/reports-harness.html");
  await page.getByRole("tab", { name: "Figures" }).focus();
  // ADR-113: with every right assumed the tabs run Figures, Trends, Packs, Published, Dashboards.
  for (const next of ["Trends", "Packs", "Published", "Dashboards"]) {
    await page.keyboard.press("Tab");
    await expect(page.getByRole("tab", { name: next })).toBeFocused();
  }
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EMBEDDED__?.at(-1)?.id)).toBe("uuid-compliance-board");
  await page.getByRole("button", { name: "Fraud board" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EMBEDDED__?.at(-1))).toEqual({ id: "uuid-fraud-board", domain: "http://bi.invalid" });
  expect(asked.filter((a) => a.includes("guest-token"))).toHaveLength(2);
  registerCovered(REGISTRY, "open-the-dashboards-tab-and-choose-a-board-by-keyboard");
});

test("the period is changed by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/reports-harness.html");
  await expect(page.getByText("1 alert in the last 12 weeks")).toBeVisible();
  // A native select, operated by the platform's own keys — the convention `alerts.spec.ts` follows.
  await page.getByRole("combobox", { name: "Period" }).selectOption("26");
  await expect.poll(() => asked).toContain("reports?weeks=26");
  registerCovered(REGISTRY, "change-the-reports-period-by-keyboard");
});

test("the figures are downloaded by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/reports-harness.html");
  await expect(page.getByText("1 alert in the last 12 weeks")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download the figures (CSV)" }).focus();
  await page.keyboard.press("Enter");
  expect((await download).suggestedFilename()).toBe("case-report-12-weeks.csv");
  expect(asked).toContain("reports/feed?weeks=12&format=csv");
  registerCovered(REGISTRY, "download-the-figures-by-keyboard");
});

test("every registered Reports action has its own proving test case above", () => {
  assertAllCovered("REPORTS_ACTIONS", REPORTS_ACTIONS);
});
