// **B6's rendering half, in a real browser — round 13cg.**
//
// `08_ACCEPTANCE_SCENARIOS.md`'s B6 row: "Inspect the shared endpoint's messages … message
// content renders with the entity spans highlighted in place." Round 13cdd proved the data half
// over the wire (`test_b6_the_shared_endpoints_messages_open_with_the_entity_spans_in_place`):
// the document view returns real text and a span with character offsets that cover the seeded
// endpoint's identifier. What that test cannot show — HTTP has no rendering — is the "in place"
// clause: that the Glass actually paints a highlight over that text, at the extracted node, for a
// principal who opened it by clicking through the working set like an analyst does. That is this
// file's whole job.
//
// **The transcript and the retry bound are the over-the-wire case's own, unchanged.** The pinned
// `qwen2.5:0.5b-instruct` is sampled and finds the shared endpoint on roughly 4 attempts in 10
// (round 13cdd's own measurement); this file retries the same way and for the same reason, not
// because anything here is flaky — what varies is the model's willingness to find something, not
// what the document view does once it has.
//
// **A second, real node, not the seeded one — and that is on purpose, not a gap.** The seeded
// shared endpoint (`scripts/seed_scenarios.py`'s `scenarios-shared-endpoint`) carries the same
// identifier value this transcript mentions, but accepting an extracted candidate never resolves
// it onto that node: ADR-024 makes an identifier-to-identifier link an analyst's own asserted
// write, never something extraction does silently. So two `Endpoint` nodes share one identifier
// value in the graph, and the search box returns both — this file selects by the accepted node's
// own id, captured from the accept response, never by the identifier text alone.
import {
  expect,
  type APIRequestContext,
  type Page,
  test,
} from "@playwright/test";

import { apiBaseUrl, freshInvestigation, liveOnly, required } from "./live";

test.beforeEach(liveOnly);

const B6_SHARED_ENDPOINT = "+447700900500";
const B6_TRANSCRIPT =
  "Message transcript, handset exhibit AB/1.\n\n" +
  `[09:14] Outgoing to ${B6_SHARED_ENDPOINT}: confirming the drop for tonight.\n` +
  `[09:16] Incoming from ${B6_SHARED_ENDPOINT}: same yard as last time.\n` +
  "[09:20] Outgoing to +447700900777: bring the second bag.\n";
const B6_EXTRACTION_ATTEMPTS = 12;

interface Candidate {
  id: string;
  properties: Record<string, unknown>;
}

function authHeader(): Record<string, string> {
  return { Authorization: `Bearer ${required("OSPREY_LIVE_BEARER_TOKEN")}` };
}

/** Extracts the transcript against `investigation`, retried the same bounded number of times the
 * over-the-wire case uses, and accepts the first candidate that carries the shared endpoint's
 * value. Returns the new node's own id — never the seeded endpoint's. */
async function extractAndAcceptB6Candidate(
  request: APIRequestContext,
  investigation: string,
): Promise<{ documentId: string; nodeId: string }> {
  for (let attempt = 0; attempt < B6_EXTRACTION_ATTEMPTS; attempt++) {
    const documentId = `b6-live-transcript-${attempt}`;
    const extracted = await request.post(
      `${apiBaseUrl()}/v1/investigations/${investigation}/ingest/extract`,
      {
        headers: authHeader(),
        data: {
          document_id: documentId,
          text: B6_TRANSCRIPT,
          profile: { entity_types: ["Endpoint"] },
          handling: {
            classification: "OFFICIAL",
            handling_code: "P",
            originator: "unit-1",
            owning_unit: "unit-1",
          },
          model: "qwen2.5:0.5b-instruct",
        },
      },
    );
    if (!extracted.ok()) {
      throw new Error(
        `extraction did not answer on this deployment: ${extracted.status()} ` +
          (await extracted.text()).slice(0, 400),
      );
    }
    const candidates = (await extracted.json()) as Candidate[];
    const candidate = candidates.find(
      (c) => c.properties["value_normalised"] === B6_SHARED_ENDPOINT,
    );
    if (!candidate) continue;

    const accepted = await request.post(
      `${apiBaseUrl()}/v1/investigations/${investigation}/ingest/candidates/${candidate.id}/accept`,
      { headers: authHeader(), data: {} },
    );
    if (!accepted.ok()) {
      throw new Error(
        `accept failed: ${accepted.status()} ${await accepted.text()}`,
      );
    }
    const { node_id: nodeId } = (await accepted.json()) as { node_id: string };
    return { documentId, nodeId };
  }
  throw new Error(
    `${B6_EXTRACTION_ATTEMPTS} extraction attempts produced no candidate carrying ` +
      `${B6_SHARED_ENDPOINT} — see this file's own header for the measured per-attempt rate`,
  );
}

/** Opens `nodeId`'s messages: search-selects it (the working set's one entry point, same as
 * every other live spec), focuses the canvas, opens the radial menu the keyboard tier already
 * proves reachable (`apps/workspace/keyboard/keyboard.spec.ts`'s "backslash opens the radial menu
 * as a keyboard-navigable list"), and activates "View messages" — the B6-specific, Endpoint-only
 * item `GlassCanvas.tsx` adds. Driven by keyboard, not `page.mouse`, for the same reason the other
 * live specs give: it is the path a keyboard user has, and the canvas is a single `<canvas>`
 * element with no per-node DOM to click. */
async function openMessagesFor(
  page: Page,
  optionName: string,
  searchText: string = B6_SHARED_ENDPOINT,
): Promise<void> {
  const search = page
    .getByRole("combobox", { name: "Search entities, identifiers, documents" })
    .first();
  await search.fill(searchText);
  const option = page.getByRole("option", { name: optionName });
  await expect(
    option,
    `no search result named exactly "${optionName}"`,
  ).toBeVisible({ timeout: 30_000 });
  await option.click();

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("\\");
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();
  const viewMessages = menu.getByRole("menuitem", { name: /View messages/ });
  await expect(
    viewMessages,
    "the radial menu offered no 'View messages' item — is this node really an Endpoint?",
  ).toBeVisible();
  await viewMessages.click();
  await expect(menu).toBeHidden();
}

test("B6 — a shared endpoint with no real document behind it shows no highlighted span", async ({
  page,
  request,
}) => {
  // **The red state this row's own claim needs, and it costs nothing extra to seed**: the
  // *seeded* shared endpoint's own provenance names `document_id: "fixture"`
  // (`scripts/seed_scenarios.py`'s `_provenance` helper) — a marker, not a real ingested
  // document, so `GET /dossier/documents/fixture` resolves to nothing and `Dossier.tsx` shows its
  // own empty state. If this ever rendered a highlighted span, it would mean the document view
  // fabricated one for a document that does not exist.
  const investigation = await freshInvestigation(request);
  await page.goto(`/?investigation=${investigation}`);

  await openMessagesFor(page, "Endpoint: scenarios-shared-endpoint");

  await expect(
    page.getByText("No messages found for this endpoint."),
  ).toBeVisible();
  await expect(page.locator("p button")).toHaveCount(0);
});

test("B6 — the extracted span is highlighted in place, over the accepted node's own message", async ({
  page,
  request,
}) => {
  const investigation = await freshInvestigation(request);
  const { nodeId } = await extractAndAcceptB6Candidate(request, investigation);

  await page.goto(`/?investigation=${investigation}`);
  // The accepted node's own search result — never the seeded endpoint's, even though both share
  // `B6_SHARED_ENDPOINT` as their identifier value (this file's own header explains why).
  await openMessagesFor(page, `Endpoint: ${nodeId}`);

  // **DOM state, not a screenshot** — `HighlightedMessage.tsx` renders a highlighted run as a
  // real `<button>` inside the message paragraph, `title` set to the entity type. Scoped to `p`
  // so a same-titled control elsewhere on the page (there is none today, but the point is not to
  // rely on that) could never satisfy this.
  const highlighted = page.locator('p button[title="Endpoint"]');
  await expect(
    highlighted.first(),
    "no highlighted span appeared in the document view for the accepted candidate's own node",
  ).toBeVisible({ timeout: 30_000 });

  // Covers the identifier, not necessarily equals it — `_locate`'s own longest-property anchor
  // can over-capture (round 13cdd's own finding, carried in 08's B6 note as a recorded gap, not
  // silently tightened here).
  const text = await highlighted.first().textContent();
  expect(
    text,
    `the highlighted run (${JSON.stringify(text)}) does not cover ${B6_SHARED_ENDPOINT}`,
  ).toContain(B6_SHARED_ENDPOINT);
});
