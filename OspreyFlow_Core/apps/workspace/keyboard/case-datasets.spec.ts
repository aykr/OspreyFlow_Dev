// What a case reads, and which domain models it carries, by keyboard alone (ADR-099, ADR-126,
// rule 13): ticking the data a new case reads and creating it, the Author changing what a case
// reads, choosing a new case's domain models, and the Author changing them. No `page.mouse`, no
// `.click()`. Each domain step asserts the request body sent and the packs shown afterwards.
import { expect, test, type Page } from "@playwright/test";

import { CASE_DATASETS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const DATASETS = [
  { id: "enron", name: "Enron corpus", owning_unit: "unit-1" },
  { id: "fixture-corp", name: "Fixture Corp", owning_unit: "unit-1" },
];

async function serve(page: Page) {
  const sent: { method: string; url: string; body: unknown }[] = [];
  // The server keeps the cases' packs, as the Conduit does, so what is shown afterwards is read
  // back from what was sent and not from what the test hoped for.
  const cases: { id: string; name: string; level: string; created_at: string; created_by: string; domains: string[] }[] = [
    { id: "c1", name: "C", level: "author", created_at: "", created_by: "", domains: [] },
  ];
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
    if (url === "/v1/investigations" && method === "GET") return route.fulfill(json(200, cases));
    if (url === "/v1/investigations" && method === "POST") {
      const posted = request.postDataJSON() as { name: string; domains?: string[] };
      cases.push({ id: "new-1", name: posted.name, level: "author", created_at: "", created_by: "", domains: posted.domains ?? [] });
      return route.fulfill(json(201, { id: "new-1", name: posted.name, domains: posted.domains ?? [] }));
    }
    if (url === "/v1/investigations/c1" && method === "PATCH") {
      const patched = request.postDataJSON() as { domains: string[] };
      cases[0]!.domains = patched.domains;
      return route.fulfill(json(200, { id: "c1", name: "C", domains: patched.domains }));
    }
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
  // ADR-099 Amendment 8: the datasets sit behind the "Read existing data…" choice, reached and
  // chosen by keyboard before any box can be ticked.
  await page.getByRole("radio", { name: "Read existing data…" }).focus();
  await page.keyboard.press(" ");
  await page.getByRole("checkbox", { name: "Enron corpus" }).focus();
  await page.keyboard.press(" ");
  await expect(page.getByRole("checkbox", { name: "Enron corpus" })).toBeChecked();
  await page.getByRole("button", { name: "Create case" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__CASE_DATASETS__?.created)).toBe("new-1");
  expect(sent.find((s) => s.method === "POST" && s.url === "/v1/investigations")?.body).toEqual({
    name: "Shipping",
    dataset_ids: ["enron"],
    domains: [],
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
  await expect(section.getByText("Enron corpus · enron, Fixture Corp · fixture-corp")).toBeVisible();
  registerCovered("CASE_DATASETS_ACTIONS", "change-what-a-case-reads-by-keyboard");
});

test("a new case's domain models are ticked with Space and sent when it is made with Enter", async ({ page }) => {
  const sent = await serve(page);
  await page.getByLabel("Case name").focus();
  await page.keyboard.type("Prison review");
  const group = page.getByRole("group", { name: "Domain models" });
  await expect(group.getByText("Bespoke POLE (the core model)")).toBeVisible();
  await group.getByRole("checkbox", { name: "Crime case analysis (NIEM)" }).focus();
  await page.keyboard.press(" ");
  await expect(group.getByRole("checkbox", { name: "Crime case analysis (NIEM)" })).toBeChecked();
  await expect(group.getByText("Bespoke POLE (the core model)")).toHaveCount(0);
  await page.getByRole("button", { name: "Create case" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__CASE_DATASETS__?.created)).toBe("new-1");
  expect(sent.find((s) => s.method === "POST" && s.url === "/v1/investigations")?.body).toEqual({
    name: "Prison review",
    domains: ["niem"],
  });
  // The packs shown afterwards are the new case's own, read back from the listing.
  const made = page.getByRole("region", { name: "Made case" });
  await expect(made.getByRole("region", { name: "Domain models" }).getByText("Crime case analysis (NIEM)")).toBeVisible();
  registerCovered("CASE_DATASETS_ACTIONS", "choose-a-cases-domain-models-when-creating-it-by-keyboard");
});

test("the Author changes a case's domain models by keyboard", async ({ page }) => {
  const sent = await serve(page);
  const section = page.getByRole("region", { name: "Domain models" });
  await expect(section.getByText("Bespoke POLE (the core model)")).toBeVisible();
  await section.getByRole("button", { name: "Change domain models" }).focus();
  await page.keyboard.press("Enter");
  await section.getByRole("checkbox", { name: "Financial fraud and AML (FIBO)" }).focus();
  await page.keyboard.press(" ");
  await section.getByRole("checkbox", { name: "Crime case analysis (NIEM)" }).focus();
  await page.keyboard.press(" ");
  await section.getByRole("button", { name: "Save" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => sent.some((s) => s.method === "PATCH" && s.url === "/v1/investigations/c1")).toBe(true);
  expect(sent.find((s) => s.method === "PATCH")?.body).toEqual({ domains: ["fibo", "niem"] });
  // As the Cases drawer does after a change: the listing is read again, and what is shown
  // afterwards is what that read says, not what the save answered.
  const patched = sent.findIndex((s) => s.method === "PATCH");
  await expect.poll(() => sent.findIndex((s, i) => i > patched && s.method === "GET" && s.url === "/v1/investigations")).toBeGreaterThan(patched);
  await expect(section.getByText("Financial fraud and AML (FIBO), Crime case analysis (NIEM)")).toBeVisible();
  await expect(section.getByRole("button", { name: "Save" })).toHaveCount(0);
  registerCovered("CASE_DATASETS_ACTIONS", "change-a-cases-domain-models-by-keyboard");
});

test("every registered case datasets action has its own proving test case above", () => {
  assertAllCovered("CASE_DATASETS_ACTIONS", CASE_DATASETS_ACTIONS);
});
