// A keyboard-only walkthrough of the pipeline Studio (ADR-108 phase B, rule 13): create and open
// a pipeline, grow it, choose a domain pack, declare an extract, remove a node, and reach the map
// editor — no `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { PIPELINE_STUDIO_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "PIPELINE_STUDIO_ACTIONS";

const CHAIN = {
  nodes: [
    { id: "domain", kind: "domain_model", label: "Domain model", config: { pack: "pole" } },
    { id: "source", kind: "source", label: "Carrier B", config: {} },
    { id: "profile", kind: "profile", label: "Profile", config: {} },
    { id: "map", kind: "map", label: "Map", config: {} },
    { id: "load", kind: "load", label: "Load", config: {} },
  ],
  edges: [
    { source: "domain", target: "source" },
    { source: "source", target: "profile" },
    { source: "profile", target: "map" },
    { source: "map", target: "load" },
  ],
};

const PACKS = [
  { name: "pole", label: "Bespoke POLE (the core model)", entity_types: [], edge_types: [] },
  { name: "stix", label: "Cyber threat analytics (STIX 2.1)", entity_types: ["ThreatActor"], edge_types: ["TARGETS"] },
];

function draft(pipeline: unknown) {
  return {
    recipe_id: "r1",
    version: 1,
    status: "draft",
    label: "Carrier B intake",
    connector_profile: "generic-csv",
    source_location: null,
    handling: {},
    legal_basis: null,
    owning_unit: "unit-1",
    created_by: "a1",
    created_at: "2026-10-10T09:00:00Z",
    pipeline,
    unmapped_fields: [],
    ready_for_profile: false,
  };
}

async function serve(page: Page) {
  const puts: unknown[] = [];
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url()).pathname;
    const method = request.method();
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.endsWith("/v1/ingest/packs")) return json(200, PACKS);
    if (url.endsWith("/pipeline") && method === "PUT") {
      const sent = request.postDataJSON();
      puts.push(sent);
      return json(200, draft(sent));
    }
    if (url.endsWith("/ingest/recipes/r1") && method === "GET") return json(200, draft(CHAIN));
    if (url.endsWith("/ingest/recipes/r1") && method === "PATCH") return json(200, draft(CHAIN));
    if (url.endsWith("/ingest/recipes") && method === "POST") return json(201, draft(null));
    if (url.endsWith("/ingest/recipes") && method === "GET") return json(200, [draft(CHAIN)]);
    return json(404, {});
  });
  await page.goto("/keyboard/pipeline-studio-harness.html");
  return puts;
}

async function openPipeline(page: Page) {
  const open = page.getByRole("button", { name: "Open Carrier B intake" });
  await open.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeVisible();
}

test("a pipeline is named and created by keyboard", async ({ page }) => {
  await serve(page);
  await page.getByLabel("Pipeline name").focus();
  await page.keyboard.type("Fresh");
  await page.getByRole("button", { name: "New pipeline" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeVisible();
  registerCovered(REGISTRY, "create-a-pipeline-by-keyboard");
});

test("a listed pipeline opens by keyboard", async ({ page }) => {
  await serve(page);
  await openPipeline(page);
  registerCovered(REGISTRY, "open-a-pipeline-by-keyboard");
});

test("a source branch is added by keyboard and the save goes out", async ({ page }) => {
  const puts = await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "+ Source" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => puts.length).toBe(1);
  expect((puts[0] as { nodes: unknown[] }).nodes).toHaveLength(9);
  registerCovered(REGISTRY, "add-a-source-branch-by-keyboard");
});

test("a domain pack is chosen by keyboard", async ({ page }) => {
  const puts = await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "Domain model: Domain model" }).focus();
  await page.keyboard.press("Enter");
  const stix = page.getByRole("radio", { name: /STIX/ });
  await stix.focus();
  await page.keyboard.press(" ");
  await expect.poll(() => puts.length).toBe(1);
  const nodes = (puts[0] as { nodes: { kind: string; config: { pack?: string } }[] }).nodes;
  expect(nodes.find((n) => n.kind === "domain_model")!.config.pack).toBe("stix");
  registerCovered(REGISTRY, "choose-a-domain-pack-by-keyboard");
});

test("extract settings are declared by keyboard", async ({ page }) => {
  const puts = await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "+ Extract" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => puts.length).toBe(1);
  await page.getByRole("button", { name: "Extract: Extract" }).focus();
  await page.keyboard.press("Enter");
  const library = page.getByLabel("Extraction library");
  await library.focus();
  await library.selectOption("spacy");
  await page.getByRole("button", { name: "Apply extract settings" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => puts.length).toBe(2);
  const nodes = (puts[1] as { nodes: { kind: string; config: { library?: string } }[] }).nodes;
  expect(nodes.find((n) => n.kind === "extract")!.config.library).toBe("spacy");
  registerCovered(REGISTRY, "apply-extract-settings-by-keyboard");
});

test("a node is removed by keyboard", async ({ page }) => {
  const puts = await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "Load: Load" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Remove selected" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => puts.length).toBe(1);
  expect((puts[0] as { nodes: unknown[] }).nodes).toHaveLength(4);
  registerCovered(REGISTRY, "remove-a-node-by-keyboard");
});

test("the map editor opens from its node by keyboard", async ({ page }) => {
  await serve(page);
  await openPipeline(page);
  await page.getByRole("button", { name: "Map: Map" }).focus();
  await page.keyboard.press("Enter");
  const open = page.getByRole("button", { name: "Open map editor" });
  await open.focus();
  await page.keyboard.press("Enter");
  // The map editor is the existing MapScreen, proven by its own specs; reaching it is this test's.
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeHidden();
  registerCovered(REGISTRY, "open-the-map-editor-by-keyboard");
});

test("every registered pipeline-studio action has its own proving test case above", () => {
  assertAllCovered("PIPELINE_STUDIO_ACTIONS", PIPELINE_STUDIO_ACTIONS);
});
