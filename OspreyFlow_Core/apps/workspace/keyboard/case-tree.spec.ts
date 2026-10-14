// The case tree by keyboard alone (ADR-084 Amendment 4, rule 13): a branch opened, renamed and deleted
// from its own row, and deleting the branch you are in returns to its case. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { CASE_TREE_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const at = "2026-10-14T16:40:00Z";
const CASES = [
  { id: "ledger", name: "Operation Ledger (synthetic demo)", level: "author", created_at: at, created_by: "a" },
  { id: "b-small", name: "Branch of Operation Ledger (synthetic demo) (2 nodes)", level: "author", created_at: at, created_by: "a", branched_from: "ledger" },
];

async function serve(page: Page, current = "ledger") {
  const sent: { method: string; url: string; body: unknown }[] = [];
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url()).pathname;
    const method = request.method();
    sent.push({ method, url, body: method === "PATCH" ? request.postDataJSON() : undefined });
    if (url === "/v1/investigations" && method === "GET") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(CASES) });
    }
    if (url === "/v1/investigations/b-small" && method === "DELETE") return route.fulfill({ status: 204 });
    if (url === "/v1/investigations/b-small" && method === "PATCH") {
      return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    }
    return route.fulfill({ status: 404, body: "{}" });
  });
  await page.goto(`/keyboard/case-tree-harness.html?current=${current}`);
  return sent;
}

const opened = (page: Page) => page.evaluate(() => document.body.dataset.opened ?? null);

test("a branch is opened from its row by keyboard", async ({ page }) => {
  await serve(page);
  const row = page.getByRole("button", { name: "2 nodes · 14 Oct 16:40", exact: true });
  await row.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => opened(page)).toBe("b-small");
  registerCovered("CASE_TREE_ACTIONS", "open-a-branch-from-the-tree");
});

test("a branch is renamed from its row by keyboard", async ({ page }) => {
  const sent = await serve(page);
  await page.getByRole("button", { name: "Actions for 2 nodes · 14 Oct 16:40" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Rename" }).focus();
  await page.keyboard.press("Enter");
  const field = page.getByRole("textbox", { name: "Branch name" });
  await expect(field).toBeFocused();
  await page.keyboard.type("Midland Pallets route");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Midland Pallets route", exact: true })).toBeVisible();
  expect(sent.find((s) => s.method === "PATCH")?.body).toEqual({ name: "Midland Pallets route" });
  registerCovered("CASE_TREE_ACTIONS", "rename-a-branch-from-the-tree");
});

test("a branch is deleted from its row by keyboard, after asking once", async ({ page }) => {
  const sent = await serve(page);
  await page.getByRole("button", { name: "Actions for 2 nodes · 14 Oct 16:40" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Delete", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Delete this branch\?/)).toBeVisible();
  await page.getByRole("button", { name: "Delete branch" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "2 nodes · 14 Oct 16:40", exact: true })).toHaveCount(0);
  expect(sent.some((s) => s.method === "DELETE" && s.url === "/v1/investigations/b-small")).toBe(true);
  registerCovered("CASE_TREE_ACTIONS", "delete-a-branch-from-the-tree");
});

test("deleting the branch you are in returns to the case it came from", async ({ page }) => {
  await serve(page, "b-small");
  await page.getByRole("button", { name: "Actions for 2 nodes · 14 Oct 16:40" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Delete", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Delete branch" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => opened(page)).toBe("ledger");
  registerCovered("CASE_TREE_ACTIONS", "delete-the-branch-you-are-in-returns-to-its-case");
});

test("every registered case tree action has its own proving test case above", () => {
  assertAllCovered("CASE_TREE_ACTIONS", CASE_TREE_ACTIONS);
});
