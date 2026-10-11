// A keyboard-only walkthrough of the Packs and Published tabs (ADR-113 stage 5, `CLAUDE.md` rule 13):
// create a pack, add a note, reorder, refresh, publish, withdraw, export and read a published pack —
// no `page.mouse`, no `.click()`; each proves its call reached the server with the right body.
import { expect, test, type Page } from "@playwright/test";

import { PACKS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";
import { LIVE_VERSION, NOTE_ITEM, PACK, TREND_ITEM, serveWorld, world } from "./reportsFixtures";

const REGISTRY = "PACKS_ACTIONS";
const PUBLISHED = { ...PACK, versions: [LIVE_VERSION] };

/** Reaches a tab the way a keyboard user does: from the first tab, with Tab, then Enter. */
async function openTab(page: Page, stepsFromFigures: number) {
  await page.getByRole("tab", { name: "Figures" }).focus();
  for (let i = 0; i < stepsFromFigures; i++) await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
}

async function openPack(page: Page) {
  await openTab(page, 2);
  await page.getByRole("button", { name: /Quarter pack/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Quarter pack" })).toBeVisible();
}

declare global {
  interface Window {
    __PRINTED__?: string[];
  }
}

test("a pack is created by keyboard", async ({ page }) => {
  const calls = await serveWorld(page, world());
  await page.goto("/keyboard/packs-harness.html");
  await openTab(page, 2);
  await page.getByLabel("New pack title").focus();
  await page.keyboard.type("Quarter pack");
  await page.getByRole("button", { name: "Create pack" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Quarter pack" })).toBeVisible();
  expect(calls.find((c) => c.method === "POST" && c.path === "packs")?.body).toEqual({ title: "Quarter pack" });
  registerCovered(REGISTRY, "create-a-pack-by-keyboard");
});

test("a note is added to a pack by keyboard, with a marking chosen", async ({ page }) => {
  const calls = await serveWorld(page, world({ packs: [PACK], items: [TREND_ITEM] }));
  await page.goto("/keyboard/packs-harness.html");
  await openPack(page);
  await page.getByRole("combobox", { name: "Item kind" }).selectOption("note");
  await page.getByLabel("Note", { exact: true }).focus();
  await page.keyboard.type("Handle with care");
  await expect(page.getByRole("button", { name: "Add item" })).toBeDisabled();
  await page.getByRole("combobox", { name: "Note marking" }).selectOption("SECRET");
  await page.getByRole("button", { name: "Add item" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("article", { name: "Note: Handle with care" })).toBeVisible();
  expect(calls.find((c) => c.method === "POST" && c.path === "packs/p1/items")?.body).toEqual({ kind: "note", text: "Handle with care", classification: "SECRET" });
  registerCovered(REGISTRY, "add-a-note-to-a-pack-by-keyboard");
});

test("an item is moved by keyboard", async ({ page }) => {
  const calls = await serveWorld(page, world({ packs: [PACK], items: [TREND_ITEM, NOTE_ITEM] }));
  await page.goto("/keyboard/packs-harness.html");
  await openPack(page);
  await page.getByRole("article", { name: /^Trend:/ }).getByRole("button", { name: "Move down" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => calls.find((c) => c.method === "PUT")?.body).toEqual({ item_ids: ["i3", "i1"] });
  await expect(page.getByRole("article").first()).toHaveAccessibleName(/^Note:/);
  registerCovered(REGISTRY, "move-a-pack-item-by-keyboard");
});

test("a trend snapshot is refreshed by keyboard", async ({ page }) => {
  const calls = await serveWorld(page, world({ packs: [PACK], items: [TREND_ITEM] }));
  await page.goto("/keyboard/packs-harness.html");
  await openPack(page);
  await page.getByRole("button", { name: "Refresh" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => calls.some((c) => c.method === "POST" && c.path === "packs/p1/items/i1/refresh")).toBe(true);
  await expect(page.getByText("The snapshot was refreshed.")).toBeVisible();
  registerCovered(REGISTRY, "refresh-a-snapshot-by-keyboard");
});

test("a pack is published by keyboard", async ({ page }) => {
  const calls = await serveWorld(page, world({ packs: [PACK], items: [TREND_ITEM] }));
  await page.goto("/keyboard/packs-harness.html");
  await openPack(page);
  await page.getByRole("button", { name: "Publish" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Published version 1.")).toBeVisible();
  expect(calls.some((c) => c.method === "POST" && c.path === "packs/p1/publish")).toBe(true);
  registerCovered(REGISTRY, "publish-a-pack-by-keyboard");
});

test("a publication is withdrawn by keyboard, with its reason", async ({ page }) => {
  const calls = await serveWorld(page, world({ packs: [PUBLISHED], items: [TREND_ITEM] }));
  await page.goto("/keyboard/packs-harness.html");
  await openPack(page);
  await page.getByRole("button", { name: "Withdraw version 1" }).focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("Reason for withdrawing").focus();
  await page.keyboard.type("figures were restated");
  await page.getByRole("button", { name: "Withdraw", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Withdrew version 1.")).toBeVisible();
  expect(calls.find((c) => c.path === "packs/p1/versions/1/withdraw")?.body).toEqual({ reason: "figures were restated" });
  registerCovered(REGISTRY, "withdraw-a-publication-by-keyboard");
});

test("a published pack is exported by keyboard, each page under its own marking", async ({ page }) => {
  const calls = await serveWorld(page, world({ packs: [PUBLISHED], items: [TREND_ITEM, NOTE_ITEM] }));
  await page.goto("/keyboard/packs-harness.html");
  await openPack(page);
  await page.getByRole("button", { name: "Export PDF" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__PRINTED__?.length)).toBe(1);
  expect(calls.some((c) => c.method === "POST" && c.path === "packs/p1/export")).toBe(true);
  const printed = await page.evaluate(() => window.__PRINTED__![0]!);
  expect(printed).toContain("Marked OFFICIAL");
  expect(printed).toContain("Marked SECRET");
  expect(printed).toContain("Handle with care");
  registerCovered(REGISTRY, "export-a-pack-by-keyboard");
});

test("a published pack is read by keyboard, read-only", async ({ page }) => {
  await serveWorld(page, world({ packs: [PUBLISHED], items: [TREND_ITEM, NOTE_ITEM], withheld: 2 }));
  await page.goto("/keyboard/packs-harness.html");
  await openTab(page, 3);
  await page.getByRole("button", { name: /Quarter pack/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("article", { name: "Note: Handle with care" })).toBeVisible();
  await expect(page.getByText("2 items in this pack are withheld from you.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Move down" })).toHaveCount(0);
  registerCovered(REGISTRY, "read-a-published-pack-by-keyboard");
});

test("every registered Packs action has its own proving test case above", () => {
  assertAllCovered("PACKS_ACTIONS", PACKS_ACTIONS);
});
