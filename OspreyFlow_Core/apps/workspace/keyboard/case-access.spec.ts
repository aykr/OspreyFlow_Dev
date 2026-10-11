// Who can open a case, by keyboard alone (ADR-052 §9, rule 13): the Author gives an account a level
// and takes one away. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { CASE_ACCESS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

async function serve(page: Page) {
  const sent: { method: string; url: string; body: unknown }[] = [];
  const grants: Record<string, string> = { alice: "author", "dash-1": "viewer" };
  const json = (status: number, body: unknown) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url()).pathname;
    const method = request.method();
    sent.push({ method, url, body: method === "PUT" ? request.postDataJSON() : undefined });
    if (url === "/v1/investigations/c1/access" && method === "GET") {
      return route.fulfill(json(200, { your_level: "author", unit_level: null, grants, names: { alice: "Alice Author" } }));
    }
    const grant = /^\/v1\/investigations\/c1\/access\/grants\/(.+)$/.exec(url);
    if (grant && method === "PUT") {
      grants[decodeURIComponent(grant[1]!)] = (request.postDataJSON() as { level: string }).level;
      return route.fulfill({ status: 204 });
    }
    if (grant && method === "DELETE") {
      delete grants[decodeURIComponent(grant[1]!)];
      return route.fulfill({ status: 204 });
    }
    return route.fulfill(json(404, {}));
  });
  await page.goto("/keyboard/case-access-harness.html");
  return sent;
}

test("the Author gives an account a level by keyboard", async ({ page }) => {
  const sent = await serve(page);
  const panel = page.getByRole("region", { name: "Who can open this case" });
  await panel.getByLabel("Account id").focus();
  await page.keyboard.type("13942885-a6b1");
  await page.keyboard.press("Tab");
  await expect(panel.getByLabel("Level")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(panel.getByRole("button", { name: "Give access" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("list", { name: "Accounts with access" })).toContainText("13942885-a6b1");
  expect(sent.find((s) => s.method === "PUT")).toEqual({
    method: "PUT",
    url: "/v1/investigations/c1/access/grants/13942885-a6b1",
    body: { level: "viewer" },
  });
  registerCovered("CASE_ACCESS_ACTIONS", "give-an-account-access-by-keyboard");
});

test("the Author removes an account's access by keyboard", async ({ page }) => {
  const sent = await serve(page);
  const panel = page.getByRole("region", { name: "Who can open this case" });
  await panel.getByRole("button", { name: "Remove dash-1's access" }).focus();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("list", { name: "Accounts with access" })).not.toContainText("dash-1");
  expect(sent.some((s) => s.method === "DELETE" && s.url === "/v1/investigations/c1/access/grants/dash-1")).toBe(true);
  registerCovered("CASE_ACCESS_ACTIONS", "remove-an-accounts-access-by-keyboard");
});

test("every registered case access action has its own proving test case above", () => {
  assertAllCovered("CASE_ACCESS_ACTIONS", CASE_ACCESS_ACTIONS);
});
