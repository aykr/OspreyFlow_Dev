// Files added straight to a case (ADR-094 step 3), by keyboard alone (rule 13): from the strip over
// the canvas, standing alone, and from a node's menu, held by it. The upload is intercepted so the
// request that went out can be read back. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { ADD_FILES_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

declare global {
  interface Window {
    __KEYBOARD__?: { focused: string | null; selectedEdge: string | null };
    __CANVAS__?: { hasNode: (nodeId: string) => boolean };
  }
}

const sent: URL[] = [];

async function serve(page: Page) {
  sent.length = 0;
  await page.route("**/v1/handling-scheme", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ classification: ["OFFICIAL"] }) }),
  );
  await page.route("**/v1/investigations/keyboard-fixture/documents?**", async (route) => {
    const url = new URL(route.request().url());
    sent.push(url);
    const id = `content:${url.searchParams.get("name")}`;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        document_id: id,
        delta: {
          seq: 2,
          op: "add",
          nodes: [
            {
              id,
              type: "Document",
              properties: { title: url.searchParams.get("name"), media_kind: "text" },
              provenance: { state: "asserted", sources: [{ document_id: "u", locator: "whole file", excerpt_hash: "" }], first_seen: "2026-10-05T00:00:00Z" },
              handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
              audit: { created_at: "2026-10-05T00:00:00Z", created_by: "analyst-1" },
            },
          ],
          edges: [],
        },
      }),
    });
  });
}

async function tabTo(page: Page, name: RegExp, max = 30) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const text = await page.evaluate(
      () => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent ?? "",
    );
    if (name.test(text.trim())) return;
  }
  throw new Error(`Tab never reached ${String(name)}`);
}

async function fillAndAdd(page: Page) {
  await page.getByLabel("Files", { exact: true }).setInputFiles({ name: "note.txt", mimeType: "text/plain", buffer: Buffer.from("Gate 3") });
  await page.getByLabel("Legal basis").focus();
  await page.keyboard.type("PACE s19 seizure");
  await tabTo(page, /^Add 1 file$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "1 file added." })).toBeVisible();
}

test("Add files on the strip adds a file to the case, standing alone", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/harness.html?fixture=emails");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await tabTo(page, /^Add files$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Add files" })).toBeVisible();
  await fillAndAdd(page);
  expect(sent[0]?.searchParams.get("holder")).toBeNull();
  expect(sent[0]?.searchParams.get("legal_basis")).toBe("PACE s19 seizure");
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.hasNode("content:note.txt"))).toBe(true);
  registerCovered("ADD_FILES_ACTIONS", "add-files-to-the-case-from-the-strip");
});

test("A node's menu adds a file it holds", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/harness.html?fixture=emails");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.focused)).toBe("ea");
  await page.keyboard.press("\\"); // the node's menu, as a list
  await tabTo(page, /^Add files held by this…/);
  await page.keyboard.press("Enter");
  await expect(page.getByText(/held by/)).toBeVisible();
  await fillAndAdd(page);
  expect(sent[0]?.searchParams.get("holder")).toBe("ea");
  registerCovered("ADD_FILES_ACTIONS", "add-files-held-by-a-node-from-its-menu");
});

test("every registered add-files action has its own proving test case above", () => {
  assertAllCovered("ADD_FILES_ACTIONS", ADD_FILES_ACTIONS);
});
