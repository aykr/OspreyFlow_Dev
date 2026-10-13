// A keyboard-only walkthrough of the Publish screen's schedule (ADR-110 decision 7, `CLAUDE.md` rule
// 13): choose how often and when, see it explained, save it; pause and resume it — no `page.mouse`,
// no `.click()`; each proves its call reached the server.
import { expect, test, type Page } from "@playwright/test";

import { PUBLISH_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "PUBLISH_ACTIONS";
const RECIPE = {
  recipe_id: "r1", version: 2, status: "published", label: "Carrier B intake", connector_profile: "generic-csv",
  source_location: "/exports/a.csv", handling: {}, legal_basis: "RIPA s22", owning_unit: "unit-1", created_by: "a1",
  created_at: "2026-10-10T09:00:00Z", git_path: "recipes/r1.yaml", pipeline: null, unmapped_fields: [],
  ready_for_profile: true, schedule_cron: "0 6 * * *", schedule_timezone: "Europe/London", schedule_owner: "approver-1",
  schedule_paused: false, schedule_paused_reason: null,
};  // prettier-ignore

async function serve(page: Page): Promise<{ method: string; path: string; body: unknown }[]> {
  const asked: { method: string; path: string; body: unknown }[] = [];
  let current: Record<string, unknown> = { ...RECIPE };
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const body = request.postData() ? (request.postDataJSON() as unknown) : null;
    asked.push({ method: request.method(), path, body });
    const json = (b: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(b) });
    if (path === "/v1/ingest/schedule-preview")
      return json({ words: "every weekday at 07:30 (Europe/London)",
                    next_runs: ["2026-06-08T06:30:00Z", "2026-06-09T06:30:00Z", "2026-06-10T06:30:00Z",
                                "2026-06-11T06:30:00Z", "2026-06-12T06:30:00Z"] });  // prettier-ignore
    if (path.endsWith("/schedule/pause")) return json((current = { ...current, schedule_paused: true, schedule_paused_reason: "paused by approver-1" }));
    if (path.endsWith("/schedule/resume")) return json((current = { ...current, schedule_paused: false, schedule_paused_reason: null }));
    if (path.endsWith("/runs")) return json([]);
    if (path.endsWith("/schedule")) return json((current = { ...current, ...(body as object) }));
    return json(current);
  });
  return asked;
}

async function press(page: Page, name: string) {
  await page.getByRole("button", { name, exact: true }).focus();
  await page.keyboard.press("Enter");
}

test("a schedule is chosen, explained and saved by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/publish-harness.html");
  const often = page.getByLabel("How often");
  await expect(often).toHaveValue("daily");
  await often.focus();
  // A native select is the browser's own keyboard control; driven as the other walkthroughs drive one.
  await often.selectOption("weekdays");
  await often.focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Time", { exact: true })).toBeFocused();
  await page.keyboard.type("0730");
  await expect(page.getByRole("status", { name: "Schedule preview" })).toContainText("Runs every weekday at 07:30");
  await press(page, "Update schedule");
  await expect
    .poll(() => asked.find((a) => a.method === "PATCH")?.body)
    .toEqual({ schedule_cron: "30 7 * * 1-5", schedule_watch: null, schedule_timezone: "Europe/London" });
  registerCovered(REGISTRY, "set-a-schedule-by-keyboard");
});

test("a schedule is paused and resumed by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/publish-harness.html");
  await press(page, "Pause schedule");
  await expect(page.getByText("Paused — paused by approver-1.")).toBeVisible();
  await press(page, "Resume schedule");
  await expect(page.getByRole("button", { name: "Pause schedule" })).toBeVisible();
  expect(asked.map((a) => a.path)).toEqual(expect.arrayContaining([
    "/v1/investigations/c1/ingest/recipes/r1/schedule/pause", "/v1/investigations/c1/ingest/recipes/r1/schedule/resume",
  ]));  // prettier-ignore
  registerCovered(REGISTRY, "pause-and-resume-a-schedule-by-keyboard");
});

test("every registered Publish action has its own proving test case above", () => {
  assertAllCovered("PUBLISH_ACTIONS", PUBLISH_ACTIONS);
});
