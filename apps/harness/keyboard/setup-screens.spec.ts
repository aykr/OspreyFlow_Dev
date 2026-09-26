// A scripted, keyboard-only walkthrough of the three setup screens — `06_DECISIONS.md` ADR-049
// Stage 2 §6 amendment 21, proving reachability end to end for this surface's own first three
// keyboard-driven actions. Like `apps/workspace/keyboard/*.spec.ts`, this test never calls
// `page.mouse`/`.click()`. Against the real `harness.webapp` server (this directory's own
// `playwright.config.ts` starts it) and a real `PUT /api/config`, not a mocked response.
import { expect, test } from "@playwright/test";

import { assertAllCovered, registerCovered, SETUP_SCREENS_ACTIONS } from "./actions";

test("Tab reaches the Profile screen's own options and a real keyboard Enter saves it", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("radio", { name: /local-lite/ }).waitFor();

  // Starting focus is the document body — proving Tab actually reaches each control, the same
  // discipline every spec in `apps/workspace/keyboard/` already follows.
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

  // Models is no longer the last nav button (Governance, Geospatial, Preflight follow it in the
  // DOM) — the same "Enter leaves focus on the activated button itself" finding as Components
  // above.
  await page.keyboard.press("Tab"); // Governance nav button
  await page.keyboard.press("Tab"); // Geospatial nav button
  await page.keyboard.press("Tab"); // Preflight nav button
  await page.keyboard.press("Tab"); // the "local only" checkbox
  await expect(page.getByRole("checkbox", { name: /Local only/ })).toBeFocused();
  await page.keyboard.press("Tab"); // Save models button (hosted-fallback fields hidden while local only)
  await expect(page.getByRole("button", { name: "Save models" })).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/config") && r.request().method() === "PUT"),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);

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

test("every registered setup-screen action has its own proving test case above", () => {
  assertAllCovered("SETUP_SCREENS_ACTIONS", SETUP_SCREENS_ACTIONS);
});
