// The deck's Operation Ledger captures — the real components, photographed over the synthetic
// financial-fraud fixture (rule 9), at the deck's own 1512×807@2x. Writes JPEGs straight into
// `OspreyFlow_deck_screens/`; `deck_build/build_deck.py` places them.
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { test, expect, type Page } from "@playwright/test";

import { layoutSettled } from "../keyboard/layoutSettled";
import {
  FRAUD_NODES,
  FRAUD_QUESTION,
  SAR_CANDIDATES,
  SAR_TEXT,
} from "./fraudFixture";

const HERE = dirname(fileURLToPath(import.meta.url));
const SHOTS = join(HERE, "../../../../../OspreyFlow_deck_screens");
const FONTS = join(HERE, "../../../../OspreyFlow_Data/basemap/fonts");

function shot(name: string) {
  return { path: join(SHOTS, name), type: "jpeg" as const, quality: 90 };
}

// The owner's choice, 10 October 2026: the deck reads better in the light theme. The attribute
// is set before any module runs, so canvas-painted colours (the graph, the map) follow it too.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("ospreyflow.theme", "light");
    } catch {
      /* storage may be blocked; the attribute below still decides this page */
    }
    document.documentElement.setAttribute("data-theme", "light");
  });
});

const json = (body: unknown) => ({
  status: 200,
  contentType: "application/json",
  body: JSON.stringify(body),
});

// --- The Glass ---------------------------------------------------------------

test("network — the ring on the canvas", async ({ page }) => {
  await page.goto("/deck-capture/fraud-network-harness.html");
  await page.getByRole("button", { name: "Communities" }).click();
  await layoutSettled(page, ["p-hale", "a-brightpath", "o-crescent", "l-carter-home"]);
  await page.screenshot(shot("f01_fraud_network.jpg"));
});

test("social network — centrality and communities beside the canvas", async ({ page }) => {
  // The Vault's answers, mocked at the transport exactly as the keyboard suite mocks compute.
  const ids = FRAUD_NODES.map((n) => n.id);
  const degree = Object.fromEntries(ids.map((id) => [id, 1]));
  Object.assign(degree, { "p-hale": 6, "a-brightpath": 11, "p-carter": 5, "o-brightpath": 4, "a-crescent": 3 });
  const betweenness = Object.fromEntries(ids.map((id) => [id, 0.01]));
  Object.assign(betweenness, { "p-hale": 0.61, "a-brightpath": 0.55, "p-carter": 0.34, "a-crescent": 0.22 });
  const communities: Record<string, string> = {};
  for (const id of ids) {
    communities[id] =
      id.startsWith("a-") || id.startsWith("o-") ? "money" : id.startsWith("p-") ? "people" : "places";
  }
  await page.route("**/compute/degree", (route) => route.fulfill(json({ mode: "sync", values: degree })));
  await page.route("**/compute/betweenness", (route) =>
    route.fulfill(json({ mode: "sync", values: betweenness })),
  );
  await page.route("**/compute/communities", (route) =>
    route.fulfill(json({ mode: "sync", communities })),
  );
  await page.route("**/compute/*", (route) => route.fulfill(json({ mode: "sync", values: degree })), {
    times: 0,
  });
  await page.goto("/deck-capture/fraud-metrics-harness.html");
  await layoutSettled(page, ["p-hale", "a-brightpath"]);
  await page.screenshot(shot("f02_fraud_social_metrics.jpg"));
});

test("entity extraction — the SAR read, findings highlighted by type", async ({ page }) => {
  // The reader only marks a span whose words hash to the candidate's own excerpt_hash (the same
  // check the server makes) — so the fixture's hashes are computed over the real text here.
  const candidates = SAR_CANDIDATES.map((candidate) => {
    const match = /^char span (\d+)-(\d+)$/.exec(candidate.locator)!;
    const words = SAR_TEXT.slice(Number(match[1]), Number(match[2]));
    return { ...candidate, excerpt_hash: createHash("sha256").update(words, "utf8").digest("hex") };
  });
  await page.route("**/v1/investigations/inv-1/documents/*/reader", (route) =>
    route.fulfill(
      json({
        document_id: "doc-sar-0412",
        title: "SAR 2026-0412 — Brightpath Consulting Ltd",
        text: SAR_TEXT,
        truncated: false,
        spans: [],
        sent_at: null,
        sender_id: null,
        recipient_id: null,
        edge_id: null,
        event_id: null,
        has_file: true,
      }),
    ),
  );
  await page.route("**/v1/investigations/inv-1/documents/*/extract", (route) =>
    route.fulfill(json({ document_id: "doc-sar-0412", text: SAR_TEXT, candidates })),
  );
  await page.goto("/keyboard/reader-harness.html");
  await page.getByRole("button", { name: "Quick scan" }).click();
  await expect(page.getByRole("list", { name: "Entities found" })).toBeVisible();
  await expect(page.getByText("Accept all pending (9)")).toBeVisible();
  await expect(page.getByTitle("Person — found, not yet accepted").first()).toBeVisible();
  await expect(page.getByText("found by spaCy").first()).toBeVisible();
  await page.screenshot(shot("f03_fraud_reader_extraction.jpg"));
});

test("geospatial — the registered offices on the basemap", async ({ page }) => {
  // The bundled style asks this origin for its glyphs; answer them from the local font build.
  await page.route("**/fonts/**", (route) => {
    const url = new URL(route.request().url());
    const file = join(FONTS, decodeURIComponent(url.pathname.replace(/^\/fonts\//, "")));
    if (!existsSync(file)) return route.fulfill({ status: 404, body: "" });
    return route.fulfill({ status: 200, contentType: "application/x-protobuf", body: readFileSync(file) });
  });
  await page.goto("/deck-capture/fraud-map-harness.html");
  // MapLibre has no single "all tiles drawn" event exposed here; a steady pause after the canvas
  // appears is what the owner's own captures used.
  await expect(page.locator("canvas").first()).toBeVisible();
  await page.waitForTimeout(9000);
  await page.screenshot(shot("f04_fraud_map.jpg"));
});

test("questions — the case asked in plain words, the answer cited", async ({ page }) => {
  await page.route("**/v1/investigations/b1/questions*", (route) => {
    if (route.request().method() === "GET") return route.fulfill(json([FRAUD_QUESTION]));
    return route.fulfill(json(FRAUD_QUESTION));
  });
  await page.goto("/keyboard/questions-harness.html");
  await expect(page.getByText(/sole director Elena Petrov/)).toBeVisible();
  await page.screenshot(shot("f05_fraud_questions.jpg"));
});


test("timeline — the fraud over time", async ({ page }) => {
  // Operation Ledger's own fortnight, bucketed per day: the structuring drumbeat (every deposit
  // under the threshold), the weekend gaps, then the two large transfers and quiet.
  const day = (d: number, count: number) => ({
    start: `2026-09-${String(d).padStart(2, "0")}T00:00:00Z`,
    end: `2026-09-${String(d + 1).padStart(2, "0")}T00:00:00Z`,
    count,
  });
  const counts: [number, number][] = [
    [1, 2], [2, 3], [3, 2], [4, 0], [5, 3], [6, 0], [7, 0], [8, 3], [9, 2], [10, 3],
    [11, 3], [12, 3], [13, 1], [14, 1], [15, 0], [16, 0], [17, 0], [18, 0],
  ];
  await page.route("**/v1/analytics/histogram", (route) =>
    route.fulfill(
      json({
        bucketing: "fixed_interval",
        buckets: counts.map(([d, count]) => day(d, count)),
        total: counts.reduce((sum, [, count]) => sum + count, 0),
      }),
    ),
  );
  await page.goto("/deck-capture/fraud-timeline-harness.html");
  await expect(page.locator("svg, canvas").first()).toBeVisible();
  await page.waitForTimeout(1500);
  await page.screenshot(shot("f11_fraud_timeline.jpg"));
});

// --- The Ingest Studio -------------------------------------------------------

const FRAUD_PIPELINE = {
  nodes: [
    { id: "domain", kind: "domain_model", label: "Domain model", config: { pack: "fibo" } },
    { id: "source", kind: "source", label: "Bank transactions", config: {} },
    { id: "profile", kind: "profile", label: "Profile", config: {} },
    { id: "map", kind: "map", label: "Map", config: {} },
    { id: "load", kind: "load", label: "Load", config: {} },
    {
      id: "source-b",
      kind: "source",
      label: "KYC customer list",
      config: { connector_profile: "generic-csv", source_location: "/ingest/kyc-customers.csv" },
    },
    { id: "source-b-profile", kind: "profile", label: "Profile", config: {} },
    { id: "source-b-map", kind: "map", label: "Map", config: {} },
    { id: "source-b-load", kind: "load", label: "Load", config: {} },
    {
      id: "extract",
      kind: "extract",
      label: "SAR narratives",
      config: { library: "spacy", media: "text", output: "review_queue" },
    },
    { id: "extract-load", kind: "load", label: "Load", config: {} },
    { id: "enrich", kind: "enrich", label: "Registered offices", config: { geocoder: "local_gazetteer" } },
    { id: "enrich-load", kind: "load", label: "Load", config: {} },
  ],
  edges: [
    { source: "domain", target: "source" },
    { source: "source", target: "profile" },
    { source: "profile", target: "map" },
    { source: "map", target: "load" },
    { source: "domain", target: "source-b" },
    { source: "source-b", target: "source-b-profile" },
    { source: "source-b-profile", target: "source-b-map" },
    { source: "source-b-map", target: "source-b-load" },
    { source: "map", target: "extract" },
    { source: "extract", target: "extract-load" },
    { source: "map", target: "enrich" },
    { source: "enrich", target: "enrich-load" },
  ],
};

const PACKS = [
  { name: "pole", label: "Bespoke POLE (the core model)", entity_types: [], edge_types: [] },
  {
    name: "fibo",
    label: "Financial fraud and AML (FIBO)",
    entity_types: ["Account"],
    edge_types: ["BENEFICIAL_OWNER_OF", "CONTROLS", "HOLDS_ACCOUNT", "TRANSACTED"],
  },
  { name: "niem", label: "Justice and public safety (NIEM)", entity_types: [], edge_types: ["USED_AS", "ROLE_IN"] },
  { name: "stix", label: "Cyber threat analytics (STIX 2.1)", entity_types: ["ThreatActor", "Campaign"], edge_types: ["TARGETS"] },
];

function fraudDraft(status = "draft") {
  return {
    recipe_id: "r-ledger",
    version: 2,
    status,
    label: "Suspicious transactions — Operation Ledger",
    connector_profile: "generic-csv",
    source_location: "/ingest/bank-transactions.csv",
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    legal_basis: "POCA 2002 s339ZH — production order 2026/0871",
    owning_unit: "unit-1",
    created_by: "a1",
    created_by_name: "Avery Whitfield",
    created_at: "2026-10-10T09:00:00Z",
    ...(status === "published"
      ? { git_path: "recipes/r-ledger.yaml", published_by: "a2", published_by_name: "Rowan Hart", published_at: "2026-10-10T10:00:00Z", ontology_version: 14 }
      : {}),
    pipeline: FRAUD_PIPELINE,
    unmapped_fields: [],
    ready_for_profile: true,
  };
}

async function serveStudio(page: Page, status = "draft") {
  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url()).pathname;
    const method = request.method();
    if (url.endsWith("/v1/ingest/packs")) return route.fulfill(json(PACKS));
    if (url.endsWith("/v1/ingest/connectors"))
      return route.fulfill(
        json([
          { id: "generic-csv", label: "CSV file", group: "Generic", structured: true, available: true },
          { id: "cell-site-csv", label: "Cell-site export (CSV)", group: "Telecoms", structured: true, available: true },
          { id: "pdf", label: "PDF document", group: "Documents", structured: false, available: false },
        ]),
      );
    if (url.endsWith("/v1/handling-scheme"))
      return route.fulfill(
        json({
          name: "uk-le",
          classification: ["PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"],
          handling_codes: { P: { label: "Permissive", dissemination: "permitted" } },
        }),
      );
    if (url.endsWith("/ingest/source-files"))
      return route.fulfill(
        json({
          root: "/ingest",
          files: [
            { name: "bank-transactions.csv", source_location: "/ingest/bank-transactions.csv", size_bytes: 48230, uploaded: true },
            { name: "kyc-customers.csv", source_location: "/ingest/kyc-customers.csv", size_bytes: 6120, uploaded: true },
          ],
        }),
      );
    if (url.endsWith("/pipeline") && method === "PUT")
      return route.fulfill(json(fraudDraft(status)));
    if (url.endsWith("/ingest/recipes/r-ledger/run") && method === "POST")
      return route.fulfill(
        json({
          load_id: "L-0912",
          recipe_id: "r-ledger",
          recipe_version: 2,
          branches: [
            {
              source_id: "source",
              source_label: "Bank transactions",
              source_location: "/ingest/bank-transactions.csv",
              report: {
                load_id: "L-0912:source", recipe_id: "r-ledger", recipe_version: 2,
                rows_read: 212, rows_deduplicated: 0, nodes_created: 9, nodes_referenced: 406, edges_created: 198,
              },
            },
            {
              source_id: "source-b",
              source_label: "KYC customer list",
              source_location: "/ingest/kyc-customers.csv",
              report: {
                load_id: "L-0912:source-b", recipe_id: "r-ledger", recipe_version: 2,
                rows_read: 48, rows_deduplicated: 0, nodes_created: 14, nodes_referenced: 48, edges_created: 62,
              },
            },
          ],
          extracts: [
            {
              node_id: "extract", library: "spacy", output: "review_queue",
              documents_read: 1, candidates_queued: 9, nodes_written_inferred: 0, handling_overridden: 0, refusals: [],
            },
          ],
          enriches: [
            {
              node_id: "enrich", geocoder: "local_gazetteer",
              locations_considered: 4, matched_local: 3, matched_online: 0, unmatched: 1, refusals: [],
            },
          ],
          rows_read: 260, nodes_created: 23, nodes_referenced: 454, edges_created: 260, rejections: [],
        }),
      );
    if (/\/ingest\/recipes\/r-ledger$/.test(url) && method === "GET")
      return route.fulfill(json(fraudDraft(status)));
    if (/\/ingest\/recipes\/r-ledger$/.test(url) && method === "PATCH")
      return route.fulfill(json(fraudDraft(status)));
    if (url.endsWith("/ingest/recipes") && method === "GET") return route.fulfill(json([fraudDraft(status)]));
    return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  await page.goto("/keyboard/pipeline-studio-harness.html");
}

async function openLedger(page: Page) {
  await page.getByRole("button", { name: "Open Suspicious transactions — Operation Ledger" }).click();
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeVisible();
}

test("studio — the pipelines home", async ({ page }) => {
  await serveStudio(page);
  await expect(page.getByText(/journey into this case's graph/)).toBeVisible();
  await page.screenshot(shot("f06_fraud_pipelines_home.jpg"));
});

test("studio — the pipeline on the canvas", async ({ page }) => {
  await serveStudio(page);
  await openLedger(page);
  await page.getByRole("button", { name: "Extract: SAR narratives" }).click();
  await expect(page.getByLabel("Extraction library")).toBeVisible();
  await page.screenshot(shot("f07_fraud_pipeline_canvas.jpg"));
});

test("studio — the domain pack chosen", async ({ page }) => {
  await serveStudio(page);
  await openLedger(page);
  await page.getByRole("button", { name: "Domain model: Domain model" }).click();
  await expect(page.getByRole("radiogroup", { name: "Domain pack" })).toBeVisible();
  await page.screenshot(shot("f08_fraud_domain_pack.jpg"));
});

test("studio — the source's Connect gate", async ({ page }) => {
  await serveStudio(page);
  await openLedger(page);
  await page.getByRole("button", { name: "Source: Bank transactions" }).click();
  await page.getByRole("button", { name: "Open source settings" }).click();
  await expect(page.getByRole("button", { name: "Back to the pipeline" })).toBeVisible();
  // "Save" (not "Create draft") proves the screen resumed the pinned draft's own form.
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Choose file…" })).toBeVisible();
  await page.screenshot(shot("f09_fraud_source_connect.jpg"));
});

test("studio — the run, answered per stage", async ({ page }) => {
  await serveStudio(page, "published");
  await openLedger(page);
  await page.getByRole("button", { name: "Publish" }).click();
  await page.getByRole("button", { name: /Run now/ }).click();
  await expect(page.getByRole("list", { name: "Pipeline stages" })).toBeVisible();
  await page.screenshot(shot("f10_fraud_run_report.jpg"));
});
