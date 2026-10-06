// Words selected with the pointer in the reader's text fill the marking form (ADR-098 decision 5).
// A pointer test, outside the keyboard registry; the keyboard route is typing the words.
import { expect, test } from "@playwright/test";

const EMAIL = {
  document_id: "email:ev-1",
  title: "Dabhol",
  text: "Dana MERCER wrote about the plant.",
  truncated: false,
  spans: [],
  sent_at: "2001-05-14T10:00:00Z",
  sender_id: "a",
  recipient_id: "b",
  edge_id: "e1",
  event_id: "ev-1",
};

test("double-clicking a word in the text puts it in Words to mark, and Mark sends its place", async ({ page }) => {
  await page.route("**/v1/investigations/inv-1/documents/*/reader", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(EMAIL) }),
  );
  let sent: { text: string; start: number; end: number } | null = null;
  await page.route("**/v1/investigations/inv-1/documents/*/designations", async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ node_id: "m1", delta: { seq: 4, op: "add", nodes: [], edges: [] } }),
    });
  });
  await page.goto("/keyboard/reader-harness.html");
  await page.getByText("plant", { exact: false }).first().waitFor();
  const text = page.locator("p", { hasText: "Dana MERCER wrote about the plant." }).first();
  const box = (await text.boundingBox())!;
  // "wrote" sits after "Dana MERCER "; double-click roughly over it.
  await text.dblclick({ position: { x: Math.min(box.width - 4, 125), y: box.height / 2 } });
  const words = page.getByRole("textbox", { name: "Words to mark" });
  await expect(words).not.toHaveValue("");
  const chosen = await words.inputValue();
  expect(EMAIL.text).toContain(chosen);
  await page.getByRole("button", { name: "Mark", exact: true }).click();
  await expect.poll(() => sent?.text).toBe(chosen);
  expect(EMAIL.text.slice(sent!.start, sent!.end)).toBe(chosen);
});
