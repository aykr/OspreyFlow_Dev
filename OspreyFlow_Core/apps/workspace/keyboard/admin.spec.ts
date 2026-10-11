// A keyboard-only walkthrough of the Admin area (ADR-110 Amendment 1, ADR-112, `CLAUDE.md` rule 13):
// save a person's roles, register and remove a dashboard, ask the system again — no `page.mouse`, no
// `.click()`; each proves its call reached the server.
import { expect, test, type Page } from "@playwright/test";

import { ADMIN_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "ADMIN_ACTIONS";
const PERSON = { id: "u1", username: "osprey-demo-analyst", name: "Demo Analyst", enabled: true, roles: ["analyst"],
                 clearance: "OFFICIAL", org_unit: "verify" };  // prettier-ignore

async function serve(page: Page): Promise<string[]> {
  const asked: string[] = [];
  let dashboards = [{ client_id: "osprey-dashboard-old", account_id: "sa-0", clearance: "OFFICIAL", org_unit: "verify" }];
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/v1/admin/", "");
    asked.push(`${request.method()} ${path}`);
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "people") return json(200, [PERSON]);
    if (path === "people/u1/roles") return json(200, { ...PERSON, roles: (request.postDataJSON() as { roles: string[] }).roles });
    if (path === "dashboards" && request.method() === "POST") {
      const made = { client_id: "osprey-dashboard-board", account_id: "sa-1", clearance: "OFFICIAL", org_unit: "verify" };
      dashboards = [...dashboards, made];
      return json(201, { dashboard: made, secret: "s3cret" });
    }
    if (path === "dashboards") return json(200, dashboards);
    if (path.startsWith("dashboards/")) return route.fulfill({ status: 204 });
    if (path === "/v1/handling-scheme") return json(200, { classification: ["OFFICIAL", "SECRET"] });
    if (path === "system") return json(200, { components: [{ name: "Graph store", ok: true, millis: 12 }] });
    return json(404, {});
  });
  return asked;
}

async function press(page: Page, name: string) {
  await page.getByRole("button", { name, exact: true }).focus();
  await page.keyboard.press("Enter");
}

test("a person's roles are saved by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html");
  await page.getByLabel("Data Engineer for osprey-demo-analyst").focus();
  await page.keyboard.press("Space");
  await press(page, "Save roles for osprey-demo-analyst");
  await expect(page.getByText("Saved.")).toBeVisible();
  expect(asked).toContain("PUT people/u1/roles");
  registerCovered(REGISTRY, "save-a-persons-roles-by-keyboard");
});

test("a dashboard is registered and removed by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_dashboards");
  await page.getByLabel("Dashboard name").fill("Board");
  await page.getByLabel("Dashboard unit").fill("verify");
  await press(page, "Register");
  await expect(page.getByText("s3cret")).toBeVisible();
  registerCovered(REGISTRY, "register-a-dashboard-by-keyboard");
  await press(page, "Remove osprey-dashboard-old");
  await expect.poll(() => asked).toContain("DELETE dashboards/osprey-dashboard-old");
  registerCovered(REGISTRY, "remove-a-dashboard-by-keyboard");
});

test("the system is asked again by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await expect(page.getByText("answered in 12 ms")).toBeVisible();
  await press(page, "Ask again");
  await expect.poll(() => asked.filter((a) => a === "GET system").length).toBe(2);
  registerCovered(REGISTRY, "ask-the-system-again-by-keyboard");
});

test("every registered Admin action has its own proving test case above", () => {
  assertAllCovered("ADMIN_ACTIONS", ADMIN_ACTIONS);
});
