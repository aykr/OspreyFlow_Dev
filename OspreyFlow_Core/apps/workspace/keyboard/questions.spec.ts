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

// ADR-129: an answer that cites two graph facts; the Glass maps a number to ids from the payload.
const FACT_ANSWER = {
  ...ANSWER,
  id: "q2",
  answer: "Rohan is tied to Dana [G-1]; Dana called Callum [G-2].",
  graph_citations: [
    { number: 1, label: "[G-1]", node_ids: ["n-rohan", "n-dana"], link_ids: ["l-assoc"] },
    { number: 2, label: "[G-2]", node_ids: ["n-dana", "n-callum"], link_ids: ["l-called"] },
  ],
};

async function serve(page: Page, history: unknown[] = [], answer: unknown = ANSWER) {
  const asked: string[] = [];
  const scopes: unknown[] = [];
  const decided: string[] = [];
  await page.route("**/*/v1/investigations/b1/questions**", async (route) => {
    const request = route.request();
    const url = request.url();
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (request.method() === "GET") return json(200, history);
    if (url.endsWith("/questions")) {
      const posted = request.postDataJSON() as { question: string };
      asked.push(posted.question);
      scopes.push(posted);
      return json(200, answer);
    }
    decided.push(url.split("/questions/")[1]!);
    if (url.endsWith("/accept")) return json(200, { node_id: "n9", delta: { seq: 2, op: "add", nodes: [], edges: [] } });
    return json(200, { rejected: true });
  });
  await page.goto("/keyboard/questions-harness.html");
  return { asked, decided, scopes };
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

test("the drawer closes from its visible Close button, reached by keyboard", async ({ page }) => {
  // The owner, 9 October 2026: "how do I close the questions panel?" — Escape alone said nothing.
  await serve(page, [ANSWER]);
  const close = page.getByRole("button", { name: "Close Questions" });
  await close.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__QUESTIONS__?.closed ?? 0)).toBe(1);
  registerCovered(REGISTRY, "close-the-questions-drawer-by-keyboard");
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

test("asking, then choosing a [G-n] from the answer by keyboard selects what it stands for and brings it into view", async ({ page }) => {
  // ADR-129 decision 1: ask (the selection goes with the question), Tab to a cited fact, Enter.
  const { scopes } = await serve(page, [], FACT_ANSWER);
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who is connected to Dana?");
  await page.keyboard.press("Control+Enter");
  const fact = page.getByRole("button", { name: "Select [G-2] on the canvas" });
  await expect(fact).toBeVisible();
  expect(scopes).toEqual([
    { question: "Who is connected to Dana?", selected_node_ids: ["n-dana"], selected_link_ids: [] },
  ]);
  await fact.focus();
  await page.keyboard.press("Enter");
  await expect
    .poll(() => page.evaluate(() => window.__QUESTIONS__?.canvas))
    .toEqual({ selectedLink: "l-called", selectedNodes: [], centred: "n-dana" });
  registerCovered(REGISTRY, "select-a-graph-fact-from-an-answer-by-keyboard");
});

test("every registered questions action has its own proving test case above", () => {
  assertAllCovered("QUESTIONS_ACTIONS", QUESTIONS_ACTIONS);
});
