// What a case reads, by keyboard alone (ADR-099, rule 13): ticking the data a new case reads and
// creating it, and the Author changing what a case reads. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { CASE_DATASETS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const DATASETS = [
  { id: "enron", name: "Enron corpus", owning_unit: "unit-1" },
  { id: "fixture-corp", name: "Fixture Corp", owning_unit: "unit-1" },
];

async function serve(page: Page) {
  const sent: { method: string; url: string; body: unknown }[] = [];
  const json = (status: number, body: unknown) => ({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url()).pathname;
    const method = request.method();
    sent.push({ method, url, body: method === "GET" ? undefined : request.postDataJSON() });
    if (url === "/v1/datasets") return route.fulfill(json(200, DATASETS));
    if (url === "/v1/investigations" && method === "GET") {
      return route.fulfill(json(200, [{ id: "c1", name: "C", level: "author", created_at: "", created_by: "" }]));
    }
    if (url === "/v1/investigations" && method === "POST") return route.fulfill(json(201, { id: "new-1", name: "N" }));
    if (url === "/v1/investigations/c1/datasets" && method === "GET") return route.fulfill(json(200, [DATASETS[1]]));
    if (url === "/v1/investigations/c1/datasets" && method === "PUT") return route.fulfill(json(200, DATASETS));
    return route.fulfill(json(404, {}));
  });
  await page.goto("/keyboard/case-datasets-harness.html");
  return sent;
}

test("a dataset is ticked with Space and the case made with Enter, reading it", async ({ page }) => {
  const sent = await serve(page);
  await page.getByLabel("Case name").focus();
  await page.keyboard.type("Shipping");
  await page.getByRole("checkbox", { name: "Enron corpus" }).focus();
  await page.keyboard.press(" ");
  await expect(page.getByRole("checkbox", { name: "Enron corpus" })).toBeChecked();
  await page.getByRole("button", { name: "Create case" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__CASE_DATASETS__?.created)).toBe("new-1");
  expect(sent.find((s) => s.method === "POST" && s.url === "/v1/investigations")?.body).toEqual({
    name: "Shipping",
    dataset_ids: ["enron"],
  });
  registerCovered("CASE_DATASETS_ACTIONS", "tick-datasets-and-create-a-case-by-keyboard");
});

test("the Author changes what the case reads by keyboard", async ({ page }) => {
  const sent = await serve(page);
  const section = page.getByRole("region", { name: "Data this case reads" });
  await section.getByRole("button", { name: "Change what this case reads" }).focus();
  await page.keyboard.press("Enter");
  await section.getByRole("checkbox", { name: "Enron corpus" }).focus();
  await page.keyboard.press(" ");
  await section.getByRole("button", { name: "Save" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__CASE_DATASETS__?.changed)).toBe(1);
  expect(sent.find((s) => s.method === "PUT")?.body).toEqual({ dataset_ids: ["fixture-corp", "enron"] });
  await expect(section.getByText("Enron corpus, Fixture Corp")).toBeVisible();
  registerCovered("CASE_DATASETS_ACTIONS", "change-what-a-case-reads-by-keyboard");
});

test("every registered case datasets action has its own proving test case above", () => {
  assertAllCovered("CASE_DATASETS_ACTIONS", CASE_DATASETS_ACTIONS);
});
