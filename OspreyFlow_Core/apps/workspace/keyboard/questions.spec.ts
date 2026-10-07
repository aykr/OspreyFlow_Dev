// A keyboard-only walkthrough of the case's questions to the model (ADR-098 decision 4, rule 13):
// ask, open what the answer draws on, accept and reject what it proposes. No `page.mouse`, no
// `.click()`. The routes are intercepted at the transport, so the request that went out can be
// read back.
import { expect, test, type Page } from "@playwright/test";

import { QUESTIONS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "QUESTIONS_ACTIONS";

const ANSWER = {
  id: "q1",
  author: "analyst-1",
  question: "Who wrote about the plant?",
  answer: "Dana Mercer wrote about it [1].",
  citations: [{ document_id: "email:ev-1", title: "Dabhol" }],
  candidates: [
    { id: "c1", document_id: "email:ev-1", entity_type: "Person", properties: { name: "Dana Mercer" }, confidence: 0.8, status: "pending", model: "qwen" },
    { id: "c2", document_id: "email:ev-1", entity_type: "Location", properties: { name: "Dabhol" }, confidence: 0.7, status: "pending", model: "qwen" },
  ],
  unplaced: 0,
  created_at: "2026-10-07T10:00:00Z",
};

async function serve(page: Page, history: unknown[] = []) {
  const asked: string[] = [];
  const decided: string[] = [];
  await page.route("**/*/v1/investigations/b1/questions**", async (route) => {
    const request = route.request();
    const url = request.url();
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (request.method() === "GET") return json(200, history);
    if (url.endsWith("/questions")) {
      asked.push((request.postDataJSON() as { question: string }).question);
      return json(200, ANSWER);
    }
    decided.push(url.split("/questions/")[1]!);
    if (url.endsWith("/accept")) return json(200, { node_id: "n9", delta: { seq: 2, op: "add", nodes: [], edges: [] } });
    return json(200, { rejected: true });
  });
  await page.goto("/keyboard/questions-harness.html");
  return { asked, decided };
}

test("Ctrl+Enter in the question asks it, and the answer joins the conversation", async ({ page }) => {
  const { asked } = await serve(page);
  await expect(page.getByText("No questions asked in this case yet.")).toBeVisible();
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who wrote about the plant?");
  await page.keyboard.press("Control+Enter");
  await expect(page.getByText("Dana Mercer wrote about it [1].")).toBeVisible();
  expect(asked).toEqual(["Who wrote about the plant?"]);
  registerCovered(REGISTRY, "ask-a-question-with-ctrl-enter");
});

test("Tab from the question reaches Ask, and Enter asks", async ({ page }) => {
  const { asked } = await serve(page);
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who wrote about the plant?");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Ask", exact: true })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Dana Mercer wrote about it [1].")).toBeVisible();
  expect(asked).toEqual(["Who wrote about the plant?"]);
  registerCovered(REGISTRY, "ask-a-question-with-the-ask-button");
});

test("a document the answer draws on opens to read by keyboard", async ({ page }) => {
  await serve(page, [ANSWER]);
  await page.getByRole("button", { name: "Dabhol", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__QUESTIONS__?.opened)).toBe("email:ev-1");
  registerCovered(REGISTRY, "open-a-cited-document-by-keyboard");
});

test("a proposal is accepted by keyboard, and its change reaches the view", async ({ page }) => {
  const { decided } = await serve(page, [ANSWER]);
  await page.getByRole("button", { name: "Accept Person · Dana Mercer" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => decided).toEqual(["candidates/c1/accept"]);
  await expect.poll(() => page.evaluate(() => window.__QUESTIONS__?.deltas.length)).toBe(1);
  await expect(page.getByText("Accepted")).toBeVisible();
  registerCovered(REGISTRY, "accept-a-proposal-by-keyboard");
});

test("a proposal is rejected by keyboard, and nothing reaches the view", async ({ page }) => {
  const { decided } = await serve(page, [ANSWER]);
  await page.getByRole("button", { name: "Reject Location · Dabhol" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => decided).toEqual(["candidates/c2/reject"]);
  await expect(page.getByText("Rejected")).toBeVisible();
  expect(await page.evaluate(() => window.__QUESTIONS__?.deltas.length)).toBe(0);
  registerCovered(REGISTRY, "reject-a-proposal-by-keyboard");
});

test("every registered questions action has its own proving test case above", () => {
  assertAllCovered("QUESTIONS_ACTIONS", QUESTIONS_ACTIONS);
});
