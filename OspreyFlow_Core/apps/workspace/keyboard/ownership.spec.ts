// A keyboard-only walkthrough of the Ownership place (ADR-109 phase C, `CLAUDE.md` rule 13): find
// an entity and trace it, trace again at another threshold, read a party's chains, and put the
// structure on the canvas — no `page.mouse`, no `.click()`; each proves its effect reached the
// server or the canvas callback.
import { expect, test, type Locator, type Page } from "@playwright/test";

import { OWNERSHIP_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "OWNERSHIP_ACTIONS";

function node(id: string, type: string, props: Record<string, unknown>) {
  return {
    id, type, properties: props,
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
  };  // prettier-ignore
}

const VIEW = {
  trace: {
    target: "C", threshold: 25, cycles: [],
    owners: [
      { node_id: "P", node_type: "Person", cumulative_percent: 60, beneficial_owner: true,
        paths: [{ link_ids: ["e1", "e2"], kind: "ownership", share: 60 }] },
      { node_id: "H", node_type: "Organisation", cumulative_percent: 60,
        paths: [{ link_ids: ["e2"], kind: "ownership", share: 60 }] },
    ],
  },
  nodes: [
    node("C", "Organisation", { name: "Crescent Imports Ltd" }),
    node("H", "Organisation", { name: "Tamarind Holdings Ltd" }),
    node("P", "Person", { family_name: "Petrov", given_names: "Elena" }),
  ],
  edges: [
    { id: "e1", type: "BENEFICIAL_OWNER_OF", source: "P", target: "H", properties: { percent: 100 } },
    { id: "e2", type: "BENEFICIAL_OWNER_OF", source: "H", target: "C", properties: { percent: 60 } },
  ],
};  // prettier-ignore

async function serve(page: Page): Promise<string[]> {
  const asked: string[] = [];
  await page.route("**/*/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/v1/investigations/inv-1/", "");
    asked.push(`${path}${url.search}`);
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "suggest") return json(200, { nodes: [VIEW.nodes[0]], more: false });
    if (path === "ownership/C") return json(200, VIEW);
    if (path === "kyc/C")
      return json(200, {
        node_id: "C", name: "Crescent Imports Ltd", status: "verified", risk_score: 15, risk_band: "low",
        assessed_on: "2026-10-10", documents: [], factors: [{ factor: "country_medium", weight: 15, words: "Registered in CY, a medium-risk jurisdiction" }],
      });  // prettier-ignore
    if (path === "ownership/C/canvas")
      return json(200, { delta: { seq: 1, op: "add", nodes: [], edges: [] }, added_nodes: 3, added_links: 2 });
    return json(404, {});
  });
  return asked;
}

async function press(page: Page, target: Locator) {
  await target.focus();
  await page.keyboard.press("Enter");
}

async function traceCrescent(page: Page) {
  await page.getByLabel("Organisation, account or person").fill("Cresc");
  await page.keyboard.press("Enter");
  await press(page, page.getByRole("button", { name: "Trace Crescent Imports Ltd" }));
  await expect(page.getByRole("table", { name: "Every owner and controller" })).toBeVisible();
}

test("an entity is found and its ownership traced, by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/ownership-harness.html");
  await traceCrescent(page);
  await expect(page.getByText(/Beneficial owners at 25%: Elena Petrov \(60%\)/)).toBeVisible();
  registerCovered(REGISTRY, "find-an-entity-and-trace-its-ownership-by-keyboard");
});

test("a customer's due diligence is read, by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/ownership-harness.html");
  await traceCrescent(page);
  await expect(page.getByRole("region", { name: "Due diligence" })).toContainText("Verified · Low risk (15)");
  await expect(page.getByText("Registered in CY, a medium-risk jurisdiction (+15)")).toBeVisible();
  registerCovered(REGISTRY, "read-a-customers-due-diligence-by-keyboard");
});

test("a trace is asked again at another threshold, by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/ownership-harness.html");
  await traceCrescent(page);
  await page.getByLabel("Beneficial ownership threshold").fill("10");
  await press(page, page.getByRole("button", { name: "Trace again" }));
  await expect.poll(() => asked).toContain("ownership/C?threshold=10");
  registerCovered(REGISTRY, "trace-again-at-another-threshold-by-keyboard");
});

test("a party's chains are read, by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/ownership-harness.html");
  await traceCrescent(page);
  await press(page, page.getByRole("button", { name: "Chains from Elena Petrov" }));
  await expect(
    page.getByText("Elena Petrov → Tamarind Holdings Ltd (100%) → Crescent Imports Ltd (60%) = 60%"),
  ).toBeVisible();
  registerCovered(REGISTRY, "read-a-partys-chains-by-keyboard");
});

test("the structure goes onto the canvas, by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/ownership-harness.html");
  await traceCrescent(page);
  await press(page, page.getByRole("button", { name: "Show the structure on the canvas" }));
  await expect.poll(() => page.evaluate(() => window.__OWNERSHIP__?.canvasNodeIds)).toEqual(["C", "H", "P"]);
  registerCovered(REGISTRY, "show-the-structure-on-the-canvas-by-keyboard");
});

test("every registered Ownership action has its own proving test case above", () => {
  assertAllCovered("OWNERSHIP_ACTIONS", OWNERSHIP_ACTIONS);
});
