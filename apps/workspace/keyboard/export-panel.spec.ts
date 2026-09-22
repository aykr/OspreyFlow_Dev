// A scripted, keyboard-only walkthrough of the export drawer (`02_GLASS_FRONTEND.md` §10) —
// Phase 8 Stage 4e, `CLAUDE.md` rule 13 applied to the sixth keyboard-driven surface
// (`keyboard/export-panel-harness.tsx`'s own docstring has the reasoning for a separate
// harness/spec pair). Like the other five, this file never calls `page.mouse`/`.click()`.
//
// The artefact-kind `Select`'s own Tab-reachability gets no case here — only an action with a
// real network call does, the same exemption `assessment-panel.spec.ts` already establishes.
// `POST /v1/investigations/inv-1/export` and `GET .../resolution/threshold` are intercepted so
// every result is deterministic.
import { expect, test, type Page } from "@playwright/test";

import { assertAllCovered, EXPORT_PANEL_ACTIONS, registerCovered } from "./actionRegistry";

async function tabToButtonNamed(page: Page, name: string, maxTabs = 40): Promise<void> {
  for (let i = 0; i < maxTabs; i++) {
    const active = await page.evaluate(() => ({
      tag: document.activeElement?.tagName,
      text: document.activeElement?.textContent ?? "",
    }));
    if (active.tag === "BUTTON" && active.text.includes(name)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Tab never reached a button named "${name}" within ${maxTabs} presses`);
}

async function routeThreshold(page: Page): Promise<void> {
  await page.route("**/*/v1/investigations/inv-1/resolution/threshold", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ threshold: 0.95 }) });
  });
}

test("submitting a subgraph export succeeds and shows the mark, reachable by keyboard alone", async ({
  page,
}) => {
  await routeThreshold(page);
  await page.route("**/*/v1/investigations/inv-1/export", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        mark: {
          osprey_mark: "OspreyFlow",
          investigation_id: "inv-1",
          exported_at: "2026-09-22T00:00:00Z",
          resolution_threshold: 0.95,
          handling_level: "OFFICIAL",
        },
        manifest: { policy: "disclose", withheld_count: 2 },
        ledger_entry_id: "led-1",
      }),
    });
  });

  await page.goto("/keyboard/export-panel-harness.html");
  await tabToButtonNamed(page, "Export");
  await page.keyboard.press("Enter");

  await expect(page.getByText("2 hidden by handling")).toBeVisible();
  await expect(page.getByText(/OspreyFlow/)).toBeVisible();
  registerCovered("EXPORT_PANEL_ACTIONS", "submit-export-succeeds");
});

test("a blocked export is overridden with justification and originator reference, reachable by keyboard alone", async ({
  page,
}) => {
  await routeThreshold(page);
  let overrideSeen = false;
  await page.route("**/*/v1/investigations/inv-1/export", async (route) => {
    const body = route.request().postDataJSON() as {
      justification?: string;
      originator_reference?: string;
    };
    if (body.justification && body.originator_reference) {
      overrideSeen = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          mark: {
            osprey_mark: "OspreyFlow",
            investigation_id: "inv-1",
            exported_at: "2026-09-22T00:00:00Z",
            resolution_threshold: 0.95,
            handling_level: "OFFICIAL",
          },
          manifest: { policy: "disclose", withheld_count: 0 },
          ledger_entry_id: "led-2",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        error: "override_required",
        detail: "a justification and an originator reference are both required to export past this block",
        blocked: [{ id: "n1", kind: "node", label: "the S2 record", reason: "consult_originator" }],
      }),
    });
  });

  await page.goto("/keyboard/export-panel-harness.html");
  await tabToButtonNamed(page, "Export");
  await page.keyboard.press("Enter");

  await expect(page.getByText(/the S2 record/)).toBeVisible();

  const justification = page.getByLabel("Justification");
  await justification.focus();
  await page.keyboard.type("cleared by supervisor");

  const originator = page.getByLabel("Originator reference");
  await originator.focus();
  await page.keyboard.type("unit-1/ref-42");

  await tabToButtonNamed(page, "Export");
  await page.keyboard.press("Enter");

  await expect(page.getByText(/OspreyFlow/)).toBeVisible();
  expect(overrideSeen).toBe(true);
  registerCovered("EXPORT_PANEL_ACTIONS", "submit-export-after-override");
});

test("every registered export-panel action has its own proving test case above", () => {
  assertAllCovered("EXPORT_PANEL_ACTIONS", EXPORT_PANEL_ACTIONS);
});
