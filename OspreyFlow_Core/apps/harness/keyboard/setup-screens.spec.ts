// A scripted, keyboard-only walkthrough of the three setup screens — `06_DECISIONS.md` ADR-049
// Stage 2 §6 amendment 21, proving reachability end to end for this surface's own first three
// keyboard-driven actions. Like `apps/workspace/keyboard/*.spec.ts`, this test never calls
// `page.mouse`/`.click()`. Against the real `harness.webapp` server (this directory's own
// `playwright.config.ts` starts it) and a real `PUT /api/config`, not a mocked response.
import { expect, type Page, type Response, test } from "@playwright/test";

import { assertAllCovered, registerCovered, SETUP_SCREENS_ACTIONS } from "./actions";

test("Tab reaches the Profile screen's own options and a real keyboard Enter saves it", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("radio", { name: /local-lite/ }).waitFor();

  // Starting focus is the document body — proving Tab actually reaches each control, the same
  // discipline every spec in `apps/workspace/keyboard/` already follows.
  await page.keyboard.press("Tab"); // the light and dark button comes first
  await expect(page.getByRole("button", { name: /Switch to the light theme/ })).toBeFocused();
  await page.keyboard.press("Tab"); // Profile nav button
  await expect(page.getByRole("button", { name: "Profile", exact: true })).toBeFocused();
  await page.keyboard.press("Tab"); // Components nav button
  await page.keyboard.press("Tab"); // Models nav button
  await page.keyboard.press("Tab"); // Governance nav button
  await page.keyboard.press("Tab"); // Geospatial nav button
  await page.keyboard.press("Tab"); // Preflight nav button
  await page.keyboard.press("Tab"); // the radio group (one tab stop, lands on the checked radio)
  await expect(page.getByRole("radio", { name: /local-lite/ })).toBeFocused();
  await page.keyboard.press("ArrowDown"); // moves selection to "small" within the radio group
  await expect(page.getByRole("radio", { name: /^small/ })).toBeChecked();
  await page.keyboard.press("Tab"); // Tab exits the radio group as a whole, straight to Save
  await expect(page.getByRole("button", { name: "Save profile" })).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/config") && r.request().method() === "PUT"),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  await expect(page.getByText("Profile", { exact: false }).first()).toBeVisible();
  await expect(page.locator(".summary-rail").getByText("decided")).toBeVisible();

  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-profile");
});

test("a keyboard-activated screen switch reaches Components and a real Enter saves it", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Components", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("combobox", { name: "Graph store" }).waitFor();

  // Activating "Components" leaves focus on that nav button itself (Enter on a button never
  // moves focus away from it) — the next Tabs reach the remaining nav buttons still in the DOM
  // after it (Models, Governance, Geospatial, Preflight), and only the one after those reaches
  // the newly-rendered screen's own field.
  await page.keyboard.press("Tab"); // Models nav button
  await page.keyboard.press("Tab"); // Governance nav button
  await page.keyboard.press("Tab"); // Geospatial nav button
  await page.keyboard.press("Tab"); // Preflight nav button
  await page.keyboard.press("Tab"); // graph store select
  await expect(page.getByRole("combobox", { name: "Graph store" })).toBeFocused();
  await page.keyboard.press("Tab"); // analytics engine select
  await expect(page.getByRole("combobox", { name: "Analytics engine" })).toBeFocused();
  await page.keyboard.press("Tab"); // the ingest folder (folder watch, ADR-110 Amendment 4)
  await expect(page.getByRole("textbox", { name: "Ingest folder" })).toBeFocused();
  await page.keyboard.press("Tab"); // Save components button
  await expect(page.getByRole("button", { name: "Save components" })).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/config") && r.request().method() === "PUT"),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);

  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-components");
});

test("a keyboard-activated screen switch reaches Models and a real Enter saves it", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Models", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("checkbox", { name: /Local only/ }).waitFor();
  // The model choices are read from the harness after the screen opens (ADR-095).
  await page.getByRole("combobox", { name: "Entity extraction model" }).waitFor();

  // Models is no longer the last nav button (Governance, Geospatial, Preflight follow it in the
  // DOM) — the same "Enter leaves focus on the activated button itself" finding as Components
  // above.
  await page.keyboard.press("Tab"); // Governance nav button
  await page.keyboard.press("Tab"); // Geospatial nav button
  await page.keyboard.press("Tab"); // Preflight nav button
  // ADR-095: the four model choices come first, the extraction model on its shipped default.
  await page.keyboard.press("Tab");
  const extraction = page.getByRole("combobox", { name: "Entity extraction model" });
  await expect(extraction).toBeFocused();
  await expect(extraction).toHaveValue("qwen2.5:7b-instruct");
  // Typing chooses an option on every platform (an arrow key opens the menu on macOS).
  await page.keyboard.type("qwen2.5:14");
  await expect(extraction).toHaveValue("qwen2.5:14b-instruct");
  await page.keyboard.press("Tab"); // image description model
  await page.keyboard.press("Tab"); // transcription model
  await page.keyboard.press("Tab"); // embedding model
  await page.keyboard.press("Tab"); // the "local only" checkbox
  await expect(page.getByRole("checkbox", { name: /Local only/ })).toBeFocused();
  await page.keyboard.press("Tab"); // Save models button (hosted-fallback fields hidden while local only)
  await expect(page.getByRole("button", { name: "Save models" })).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/config") && r.request().method() === "PUT"),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  expect(((await response.json()) as { models: { extraction: string } }).models.extraction).toBe(
    "qwen2.5:14b-instruct",
  );

  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-models");
});

test("Tab reaches the Governance screen and a real keyboard Enter saves it", async ({ page }) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Governance", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("textbox", { name: "Identity provider" }).waitFor();

  // Governance is the 4th of 6 nav buttons — two siblings (Geospatial, Preflight) follow it in
  // the DOM, the same "Enter leaves focus on the activated button itself" finding
  // `setup-screens.spec.ts`'s own Components case already established.
  await page.keyboard.press("Tab"); // Geospatial nav button
  await page.keyboard.press("Tab"); // Preflight nav button
  await page.keyboard.press("Tab"); // Identity provider input
  await expect(page.getByRole("textbox", { name: "Identity provider" })).toBeFocused();
  await page.keyboard.press("Tab"); // Handling scheme select
  await expect(page.getByRole("combobox", { name: "Handling scheme" })).toBeFocused();
  await page.keyboard.press("Tab"); // Ontology input
  await expect(page.getByRole("textbox", { name: "Ontology" })).toBeFocused();
  await page.keyboard.press("Tab"); // Real-data exceptions file path input
  await expect(page.getByRole("textbox", { name: "Real-data exceptions file path" })).toBeFocused();
  await page.keyboard.press("Tab"); // Save governance button
  await expect(page.getByRole("button", { name: "Save governance" })).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/config") && r.request().method() === "PUT"),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);

  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-governance");
});

test("a real keyboard walkthrough adds a real-data exception through the Governance panel", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Governance", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("textbox", { name: "Dataset name" }).waitFor();

  await page.keyboard.press("Tab"); // Geospatial nav button
  await page.keyboard.press("Tab"); // Preflight nav button
  await page.keyboard.press("Tab"); // Identity provider
  await page.keyboard.press("Tab"); // Handling scheme
  await page.keyboard.press("Tab"); // Ontology
  await page.keyboard.press("Tab"); // Real-data exceptions file path
  await page.keyboard.press("Tab"); // Save governance button
  await page.keyboard.press("Tab"); // Dataset name input
  await expect(page.getByRole("textbox", { name: "Dataset name" })).toBeFocused();
  await page.keyboard.type("Keyboard Spec Corpus");

  await page.keyboard.press("Tab"); // local_development checkbox
  await expect(page.getByRole("checkbox", { name: "local_development" })).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page.getByRole("checkbox", { name: "local_development" })).toBeChecked();

  await page.keyboard.press("Tab"); // scale_testing checkbox
  await page.keyboard.press("Tab"); // owner_run_demonstration checkbox
  await page.keyboard.press("Tab"); // Added by
  await expect(page.getByRole("textbox", { name: "Added by" })).toBeFocused();
  await page.keyboard.type("keyboard-spec");

  await page.keyboard.press("Tab"); // Device
  await page.keyboard.type("ci-runner");

  await page.keyboard.press("Tab"); // Justification
  await page.keyboard.type("proving the panel is keyboard reachable");

  await page.keyboard.press("Tab"); // Decision record
  await page.keyboard.type("ADR-035 §C3");

  await page.keyboard.press("Tab"); // Add exception button
  await expect(page.getByRole("button", { name: "Add exception" })).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/real-data-exceptions") && r.request().method() === "POST",
    ),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  await expect(page.getByText("Keyboard Spec Corpus")).toBeVisible();

  registerCovered("SETUP_SCREENS_ACTIONS", "submit-add-exception");
});

test("a real keyboard Enter removes a real-data exception through the Governance panel", async ({
  page,
  request,
}) => {
  // Seeded directly, not through the UI — this test's own scope is proving Remove is keyboard
  // reachable and really calls DELETE, not re-proving Add (the previous test's own scope).
  await request.post("/api/real-data-exceptions", {
    data: {
      dataset: "Seeded For Removal",
      approved_uses: ["local_development"],
      added_by: "seed",
      device: "ci-runner",
      justification: "seeded for the remove test",
      decision_record: "ADR-035 §C3",
    },
  });

  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Governance", exact: true }).focus();
  await page.keyboard.press("Enter");

  // Scoped to this test's own seeded row — the previous test's own "Keyboard Spec Corpus" entry
  // is still present in the same scratch file (one server, one file, across the whole run), so an
  // unscoped "Remove" would match more than one row.
  const removeButton = page
    .getByRole("listitem")
    .filter({ hasText: "Seeded For Removal" })
    .getByRole("button", { name: "Remove" });
  await removeButton.waitFor();
  await removeButton.focus();
  await expect(removeButton).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/real-data-exceptions/") && r.request().method() === "DELETE",
    ),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  await expect(page.getByText("Seeded For Removal")).toHaveCount(0);

  registerCovered("SETUP_SCREENS_ACTIONS", "submit-remove-exception");
});

test("a real keyboard walkthrough registers a local provider through the Geospatial screen", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Geospatial", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("textbox", { name: "Provider id" }).waitFor();

  // Geospatial is the 5th of 6 nav buttons — one sibling (Preflight) follows it in the DOM.
  await page.keyboard.press("Tab"); // Preflight nav button
  await page.keyboard.press("Tab");
  await expect(page.getByRole("textbox", { name: "Provider id" })).toBeFocused();
  await page.keyboard.type("osm-local-keyboard-spec");

  await page.keyboard.press("Tab");
  await expect(page.getByRole("textbox", { name: "Label" })).toBeFocused();
  await page.keyboard.type("Keyboard spec region");

  await page.keyboard.press("Tab");
  await expect(page.getByRole("textbox", { name: "PMTiles path" })).toBeFocused();
  await page.keyboard.type("/tmp/keyboard-spec.pmtiles");

  await page.keyboard.press("Tab"); // Register provider button
  await expect(page.getByRole("button", { name: "Register provider" })).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/geospatial/register-provider")),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);

  registerCovered("SETUP_SCREENS_ACTIONS", "submit-register-provider");
});

test("Tab reaches Build local basemap and Verify, each a real keyboard-triggered call", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Geospatial", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Build local basemap" }).waitFor();

  await page.keyboard.press("Tab"); // Preflight nav button
  await page.keyboard.press("Tab"); // Provider id
  await page.keyboard.press("Tab"); // Label
  await page.keyboard.press("Tab"); // PMTiles path
  await page.keyboard.press("Tab"); // Register provider button
  await page.keyboard.press("Tab"); // Build local basemap button
  await expect(page.getByRole("button", { name: "Build local basemap" })).toBeFocused();

  // Always a real 501 — `harness/geospatial.py`'s own docstring has the confirmed-by-import
  // reason; this test proves the button is keyboard-reachable and really calls the route, not
  // that the route succeeds (`test_webapp_geospatial.py` proves the 501 itself, at the route).
  const [buildResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/geospatial/build-basemap")),
    page.keyboard.press("Enter"),
  ]);
  expect(buildResponse.status()).toBe(501);
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-build-basemap");

  await page.keyboard.press("Tab"); // Verify button
  await expect(page.getByRole("button", { name: "Verify" })).toBeFocused();

  const [verifyResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/geospatial/verify")),
    page.keyboard.press("Enter"),
  ]);
  expect(verifyResponse.status()).toBe(501);
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-verify-map");
});

test("a real keyboard walkthrough generates, downloads and confirms the artefacts", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Preflight", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Generate" }).waitFor();

  // Preflight is the last nav button — no nav sibling follows it, so the very next Tab reaches
  // this screen's own first field directly.
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Generate" })).toBeFocused();

  const [generateResponse] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/artefacts/generate") && r.request().method() === "POST",
    ),
    page.keyboard.press("Enter"),
  ]);
  expect(generateResponse.ok()).toBe(true);
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-generate-artefacts");
  await page.getByRole("link", { name: "Download compose.yaml" }).waitFor();

  await page.keyboard.press("Tab"); // Download compose.yaml link
  await expect(page.getByRole("link", { name: "Download compose.yaml" })).toBeFocused();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.keyboard.press("Enter"),
  ]);
  expect(download.suggestedFilename()).toBe("compose.yaml");
  registerCovered("SETUP_SCREENS_ACTIONS", "download-artefact");

  await page.keyboard.press("Tab"); // Download deployment.env link
  await page.keyboard.press("Tab"); // Download versions.lock link
  await page.keyboard.press("Tab"); // Download RUNBOOK.md link
  await page.keyboard.press("Tab"); // Confirm artefacts button
  await expect(page.getByRole("button", { name: "Confirm artefacts" })).toBeFocused();

  const [confirmResponse] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/artefacts/confirm") && r.request().method() === "POST",
    ),
    page.keyboard.press("Enter"),
  ]);
  expect(confirmResponse.ok()).toBe(true);
  await expect(page.getByRole("button", { name: "Artefacts confirmed" })).toBeVisible();
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-confirm-artefacts");
});

test("a real keyboard-triggered preflight run streams every check and enables Launch", async ({
  page,
}) => {
  // Its own starting point: `local-lite`. The Profile test above saves `small` to the same scratch
  // config, and `small` expects GPU-backed serving, so on a host with no GPU (any CI runner) its
  // Preflight failed the gpu check; on a Mac that check always skips, which hid it (15 October 2026).
  const reset = await page.request.put("/api/config", { data: { profile: "local-lite" } });
  expect(reset.ok()).toBe(true);
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Preflight", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Generate" }).waitFor();

  // Launch starts disabled — the real attribute, before any check has run and before the
  // artefacts are confirmed.
  await expect(page.getByRole("button", { name: "Launch", exact: true })).toBeDisabled();

  // A rendered deployment is what every check that reads deploy/generated/<profile>/ needs —
  // Preflight's own real dependency (`RenderedOutputMissing` otherwise), not invented for this
  // test.
  await page.getByRole("button", { name: "Generate" }).focus();
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/artefacts/generate") && r.request().method() === "POST",
    ),
    page.keyboard.press("Enter"),
  ]);

  await page.getByRole("button", { name: "Confirm artefacts" }).focus();
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/artefacts/confirm") && r.request().method() === "POST",
    ),
    page.keyboard.press("Enter"),
  ]);

  await page.getByRole("button", { name: "Run preflight" }).focus();
  const [runResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/preflight/stream")),
    page.keyboard.press("Enter"),
  ]);
  expect(runResponse.ok()).toBe(true);
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-run-preflight");

  // The stream's own last check — its result rendering is what proves every earlier one already
  // arrived and was rendered, not only that the request completed.
  await expect(page.getByText("oidc-audience — pass")).toBeVisible();
  // Every check passes or skips on the fixed-size host (keyboard/console_fixed_host.py); a failing
  // one is named here, with its reason, rather than surfacing later as a disabled Launch.
  expect(await page.getByText(/ — fail/).allTextContents(), "Preflight checks failing on this host").toEqual([]);
  // Still disabled — the artefacts are confirmed and every check passes or skips, but the Docker
  // target is not yet confirmed.
  await expect(page.getByRole("button", { name: "Launch", exact: true })).toBeDisabled();

  await page.getByRole("button", { name: "Re-check memory" }).focus();
  const [recheckResponse] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/preflight/stream") && r.url().includes("only=memory"),
    ),
    page.keyboard.press("Enter"),
  ]);
  expect(recheckResponse.ok()).toBe(true);
  await expect(page.getByText("memory — pass")).toBeVisible();
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-recheck");

  await page.getByRole("button", { name: "Confirm target" }).focus();
  const [targetResponse] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/launch/target/confirm") && r.request().method() === "POST",
    ),
    page.keyboard.press("Enter"),
  ]);
  expect(targetResponse.ok()).toBe(true);
  await expect(page.getByText("(confirmed)")).toBeVisible();
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-confirm-target");

  await expect(page.getByRole("button", { name: "Launch", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Launch", exact: true }).focus();
  const [launchResponse] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/launch/stream") && r.request().method() === "POST",
    ),
    page.keyboard.press("Enter"),
  ]);
  expect(launchResponse.ok()).toBe(true);
  // The fake `--apply-command` this suite's own `playwright.config.ts` injects — a real
  // subprocess, its own real stdout streamed and rendered, not a mocked response.
  await expect(page.getByText("apply: local-lite ready in 1s")).toBeVisible();
  await expect(page.getByText("Launch succeeded.")).toBeVisible();
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-launch");
});

// ---- the guided install page (`ospreyflow install --gui`, ADR-114 Amendment 3, stage B2c) --------
//
// The same screens, against `harness/install_page.py` (this directory's own `playwright.config.ts`
// starts it behind a fixed token, with a stub where the real install would run). The page's token is
// an HttpOnly cookie; the spec presents the same one the printed link would have set. These cases
// share the page's one server and run in order: Lite's screens, then Small's, then Lite's Install
// last, because the page shuts itself down when an install ends.
const INSTALL_BASE = "http://localhost:5192";
const INSTALL_TOKEN = "keyboard-spec-install-token"; // the same literal is in playwright.config.ts

async function openInstallPage(page: Page) {
  await page
    .context()
    .addCookies([{ name: "osprey_install", value: INSTALL_TOKEN, url: INSTALL_BASE }]);
  await page.goto(`${INSTALL_BASE}/keyboard/install-harness.html`);
  await page.getByRole("navigation", { name: "Install screens" }).waitFor();
}

/** Tab past `count` focusable controls from where focus is, saying which one each stop is. */
async function tabTimes(page: Page, count: number) {
  for (let i = 0; i < count; i += 1) await page.keyboard.press("Tab");
}

const isAnswersPut = (r: Response) =>
  r.url().includes("/api/install/answers") && r.request().method() === "PUT";

test("install page: Tab reaches the Mode screen's radio group and a real Enter saves the mode", async ({
  page,
}) => {
  await openInstallPage(page);
  // Starting focus is the document body. The summary rail comes first in the page: its light and
  // dark button, then Lite's nine screens: Mode, Folders, Profile, Components, Map, Models,
  // Governance, Demo packs, Review.
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: /Switch to the light theme/ })).toBeFocused();
  await tabTimes(page, 9);
  await expect(page.getByRole("button", { name: "Review", exact: true })).toBeFocused();
  await page.keyboard.press("Tab"); // the radio group, on the checked radio
  await expect(page.getByRole("radio", { name: /^Lite/ })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Save mode" })).toBeFocused();
  const [response] = await Promise.all([
    page.waitForResponse(isAnswersPut),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  expect(((await response.json()) as { mode: string }).mode).toBe("lite");
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-mode");
});

test("install page: a keyboard-activated switch reaches Folders and a real Enter saves them", async ({
  page,
}) => {
  await openInstallPage(page);
  await page.getByRole("button", { name: "Folders", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("textbox", { name: "Ingest folder" }).waitFor();
  await tabTimes(page, 7); // Profile, Components, Map, Models, Governance, Demo packs, Review
  await page.keyboard.press("Tab");
  await expect(page.getByRole("textbox", { name: "Ingest folder" })).toBeFocused();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("/srv/osprey/ingest");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("textbox", { name: "Basemap folder" })).toBeFocused();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("/srv/osprey/basemap");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Save folders" })).toBeFocused();
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/config") && r.request().method() === "PUT"),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  const saved = (await response.json()) as { components: { storage: { ingest: string; tiles: string } } };
  expect(saved.components.storage.ingest).toBe("/srv/osprey/ingest");
  expect(saved.components.storage.tiles).toBe("/srv/osprey/basemap");
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-folders");
});

test("install page: a keyboard-activated switch reaches Demo packs and a real Enter saves the ticked pack", async ({
  page,
}) => {
  await openInstallPage(page);
  await page.getByRole("button", { name: "Demo packs", exact: true }).focus();
  await page.keyboard.press("Enter");
  const boxes = page.getByRole("checkbox");
  await boxes.first().waitFor();
  const packs = await boxes.count();
  await page.keyboard.press("Tab"); // Review nav button
  await page.keyboard.press("Tab"); // the first pack
  await expect(boxes.first()).toBeFocused();
  await page.keyboard.press("Space"); // ticks it
  await expect(boxes.first()).toBeChecked();
  await tabTimes(page, packs - 1);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Save demo packs" })).toBeFocused();
  const [response] = await Promise.all([
    page.waitForResponse(isAnswersPut),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  expect(((await response.json()) as { answers: { demo_packs: string[] } }).answers.demo_packs).toHaveLength(1);
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-demo-packs");
});

test("install page: Small's Cloud and region screen is reached by keyboard and a real Enter saves it", async ({
  page,
}) => {
  await openInstallPage(page);
  // Choose Small on the Mode screen first: Tab to the radio group, ArrowDown, Tab to Save.
  await tabTimes(page, 11); // the theme button, nine screens, the radio group
  await expect(page.getByRole("radio", { name: /^Lite/ })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("radio", { name: /^Small/ })).toBeChecked();
  await page.keyboard.press("Tab");
  const [modeResponse] = await Promise.all([
    page.waitForResponse(isAnswersPut),
    page.keyboard.press("Enter"),
  ]);
  expect(modeResponse.ok()).toBe(true);
  // Small's screens only now: Mode, Cloud and region, Domain, Components, Models, Governance,
  // Demo packs, Review.
  await expect(page.getByRole("button", { name: "Folders", exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Cloud and region", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("textbox", { name: "Region" }).waitFor();
  await tabTimes(page, 6); // Domain, Components, Models, Governance, Demo packs, Review
  await page.keyboard.press("Tab"); // the provider radio group, on AWS
  await expect(page.getByRole("radio", { name: /AWS/ })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("textbox", { name: "Region" })).toBeFocused();
  await page.keyboard.type("eu-west-2");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("combobox", { name: "Size" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Save cloud and region" })).toBeFocused();
  const [response] = await Promise.all([
    page.waitForResponse(isAnswersPut),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  expect(((await response.json()) as { answers: { cloud: { region: string } } }).answers.cloud.region).toBe(
    "eu-west-2",
  );
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-cloud");
});

test("install page: Small's Domain screen is reached by keyboard and a real Enter saves it", async ({
  page,
}) => {
  await openInstallPage(page);
  await page.getByRole("button", { name: "Domain", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("textbox", { name: "Domain name" }).waitFor();
  await tabTimes(page, 5); // Components, Models, Governance, Demo packs, Review
  await page.keyboard.press("Tab");
  await expect(page.getByRole("textbox", { name: "Domain name" })).toBeFocused();
  await page.keyboard.type("osprey.example.org");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Save domain" })).toBeFocused();
  const [response] = await Promise.all([
    page.waitForResponse(isAnswersPut),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  const saved = (await response.json()) as { answers: { cloud: { domain: string; region: string } } };
  expect(saved.answers.cloud.domain).toBe("osprey.example.org");
  expect(saved.answers.cloud.region).toBe("eu-west-2"); // what the Cloud screen saved is kept
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-domain");
});

test("install page: Small's Review says how it is built and a real Enter saves the answers", async ({
  page,
}) => {
  await openInstallPage(page);
  await page.getByRole("button", { name: "Review", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/A small server is built from a terminal on this computer/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Install", exact: true })).toHaveCount(0);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Save answers" })).toBeFocused();
  const [response] = await Promise.all([
    page.waitForResponse(isAnswersPut),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  await expect(page.getByText("Your answers are saved.")).toBeVisible();
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-answers");
});

test("install page: Lite's Install is reached by keyboard, a real Enter runs it and the page says it closes", async ({
  page,
}) => {
  await openInstallPage(page);
  // Back to Lite: Small has eight screens before the radio group.
  await tabTimes(page, 10); // the theme button, eight screens, the radio group
  await expect(page.getByRole("radio", { name: /^Small/ })).toBeFocused();
  await page.keyboard.press("ArrowUp");
  await expect(page.getByRole("radio", { name: /^Lite/ })).toBeChecked();
  await page.keyboard.press("Tab");
  const [modeResponse] = await Promise.all([
    page.waitForResponse(isAnswersPut),
    page.keyboard.press("Enter"),
  ]);
  expect(modeResponse.ok()).toBe(true);
  await page.getByRole("button", { name: "Folders", exact: true }).waitFor();

  await page.getByRole("button", { name: "Review", exact: true }).focus();
  await page.keyboard.press("Enter");
  // The doctor's lines, as the page ran it (the stub echoes what it was asked to run).
  await expect(page.getByRole("log").first()).toContainText("doctor --mode lite");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Install", exact: true })).toBeFocused();
  const [run] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/install/run") && r.request().method() === "POST"),
    page.keyboard.press("Enter"),
  ]);
  expect(run.ok()).toBe(true);
  await expect(page.getByRole("log", { name: "Install output" })).toContainText("install --mode lite");
  await expect(page.getByText(/OspreyFlow is installed/)).toBeVisible();
  await expect(page.getByText("This page closes now.")).toBeVisible();
  registerCovered("SETUP_SCREENS_ACTIONS", "submit-install");
});

test("every registered setup-screen action has its own proving test case above", () => {
  assertAllCovered("SETUP_SCREENS_ACTIONS", SETUP_SCREENS_ACTIONS);
});
