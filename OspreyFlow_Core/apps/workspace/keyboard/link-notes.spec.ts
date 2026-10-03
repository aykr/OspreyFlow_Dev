// A scripted, keyboard-only walkthrough of the Notes section for a selected link (ADR-075, rule
// 13). Like the other keyboard specs it never calls `page.mouse` or `.click()`. The four routes are
// intercepted at the transport and held in a small in-memory list, so each result is deterministic
// and the request that went out can be read back.
import { expect, test, type Page } from "@playwright/test";

import { LINK_NOTES_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

interface Note {
  id: string;
  investigation_id: string;
  edge_id: string;
  author: string;
  body: string;
  created_at: string;
  edited_at: string | null;
  mine: boolean;
}

const REGISTRY = "LINK_NOTES_ACTIONS";

async function serve(page: Page, initial: Note[] = []) {
  let notes = [...initial];
  const requests: { method: string; url: string; body?: { body: string } }[] = [];
  let next = 1;
  await page.route("**/*/v1/investigations/inv-1/links/e1/notes**", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = request.url();
    const body = method === "POST" || method === "PUT" ? request.postDataJSON() : undefined;
    requests.push({ method, url, body });
    const json = (status: number, payload?: unknown) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: payload === undefined ? "" : JSON.stringify(payload),
      });
    if (method === "GET") return json(200, { notes });
    if (method === "POST") {
      const added: Note = {
        id: `new-${next++}`,
        investigation_id: "inv-1",
        edge_id: "e1",
        author: "analyst-1",
        body: body!.body,
        created_at: "2026-10-03T10:00:00Z",
        edited_at: null,
        mine: true,
      };
      notes = [added, ...notes];
      return json(201, added);
    }
    const id = url.split("/").pop()!;
    if (method === "PUT") {
      notes = notes.map((n) => (n.id === id ? { ...n, body: body!.body, edited_at: "2026-10-03T11:00:00Z" } : n));
      return json(200, notes.find((n) => n.id === id));
    }
    notes = notes.filter((n) => n.id !== id);
    return json(204);
  });
  return { requests, current: () => notes };
}

const own: Note = {
  id: "n1",
  investigation_id: "inv-1",
  edge_id: "e1",
  author: "analyst-1",
  body: "Original wording.",
  created_at: "2026-10-01T09:00:00Z",
  edited_at: null,
  mine: true,
};

async function focusedName(page: Page): Promise<string> {
  return page.evaluate(
    () =>
      document.activeElement?.getAttribute("aria-label") ??
      document.activeElement?.textContent ??
      "",
  );
}

async function tabTo(page: Page, name: string, max = 20) {
  for (let i = 0; i < max; i++) {
    if ((await focusedName(page)).trim() === name) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Tab never reached "${name}"`);
}

test("Ctrl+Enter in the box adds the note", async ({ page }) => {
  const server = await serve(page);
  await page.goto("/keyboard/link-notes-harness.html");
  await page.getByLabel("New note").focus();
  await page.keyboard.type("Added without a mouse.");
  await page.keyboard.press("Control+Enter");
  await expect(page.getByText("Added without a mouse.")).toBeVisible();
  expect(server.requests.find((r) => r.method === "POST")?.body).toEqual({ body: "Added without a mouse." });
  registerCovered(REGISTRY, "ctrl-enter-adds-a-note");
});

test("Tab from the box to Add note and Enter adds the note", async ({ page }) => {
  const server = await serve(page);
  await page.goto("/keyboard/link-notes-harness.html");
  await page.getByLabel("New note").focus();
  await page.keyboard.type("Via the button.");
  await page.keyboard.press("Tab");
  expect(await focusedName(page)).toBe("Add note");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Via the button.")).toBeVisible();
  expect(server.requests.filter((r) => r.method === "POST")).toHaveLength(1);
  registerCovered(REGISTRY, "add-note-button-by-keyboard");
});

test("Edit, change the text and Save by keyboard", async ({ page }) => {
  const server = await serve(page, [own]);
  await page.goto("/keyboard/link-notes-harness.html");
  await expect(page.getByText("Original wording.")).toBeVisible();
  await page.getByLabel("New note").focus();
  await tabTo(page, "Edit note");
  await page.keyboard.press("Enter");
  const box = page.getByLabel("Note text");
  await expect(box).toBeFocused();
  await page.keyboard.press("Control+A");
  await page.keyboard.type("Revised wording.");
  await tabTo(page, "Save");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Revised wording.")).toBeVisible();
  const put = server.requests.find((r) => r.method === "PUT");
  expect(put?.url).toMatch(/\/notes\/n1$/);
  expect(put?.body).toEqual({ body: "Revised wording." });
  await expect(page.getByText(/edited/)).toBeVisible();
  registerCovered(REGISTRY, "edit-own-note-and-save-by-keyboard");
});

test("Escape cancels an edit, changes nothing and returns focus to Edit", async ({ page }) => {
  const server = await serve(page, [own]);
  await page.goto("/keyboard/link-notes-harness.html");
  await expect(page.getByText("Original wording.")).toBeVisible();
  await page.getByLabel("New note").focus();
  await tabTo(page, "Edit note");
  await page.keyboard.press("Enter");
  await page.keyboard.type(" Typed then abandoned.");
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Note text")).toHaveCount(0);
  await expect(page.getByText("Original wording.")).toBeVisible();
  await expect.poll(() => focusedName(page)).toBe("Edit note");
  expect(server.requests.some((r) => r.method === "PUT")).toBe(false);
  registerCovered(REGISTRY, "escape-cancels-an-edit-and-returns-focus");
});

test("Delete asks first; confirming by keyboard removes the note", async ({ page }) => {
  const server = await serve(page, [own]);
  await page.goto("/keyboard/link-notes-harness.html");
  await expect(page.getByText("Original wording.")).toBeVisible();
  await page.getByLabel("New note").focus();
  await tabTo(page, "Delete note");
  await page.keyboard.press("Enter");
  expect(server.requests.some((r) => r.method === "DELETE")).toBe(false);
  await tabTo(page, "Confirm delete");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Original wording.")).toHaveCount(0);
  expect(server.requests.filter((r) => r.method === "DELETE")).toHaveLength(1);
  registerCovered(REGISTRY, "delete-own-note-by-keyboard-after-confirming");
});

test("Cancelling a delete by keyboard keeps the note", async ({ page }) => {
  const server = await serve(page, [own]);
  await page.goto("/keyboard/link-notes-harness.html");
  await expect(page.getByText("Original wording.")).toBeVisible();
  await page.getByLabel("New note").focus();
  await tabTo(page, "Delete note");
  await page.keyboard.press("Enter");
  await tabTo(page, "Cancel");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Original wording.")).toBeVisible();
  expect(server.requests.some((r) => r.method === "DELETE")).toBe(false);
  registerCovered(REGISTRY, "cancel-a-delete-by-keyboard");
});

test("every registered link-notes action has its own proving test case above", () => {
  assertAllCovered("LINK_NOTES_ACTIONS", LINK_NOTES_ACTIONS);
});
