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

async function serve(page: Page, history: unknown[] = [], answer: unknown = ANSWER, harness = "/keyboard/questions-harness.html") {
  const asked: string[] = [];
  const scopes: unknown[] = [];
  const decided: string[] = [];
  await page.route("**/*/v1/investigations/*/questions**", async (route) => {
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
  await page.goto(harness);
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

declare global {
  interface Window {
    __KEYBOARD__?: { focused: string | null; selection: string[]; selectedEdge: string | null };
  }
}

const GRAPH_FACTS = {
  ...ANSWER,
  id: "q3",
  answer: "One link [G-1]; a link not in view [G-2]; two links [G-3]; nothing in view [G-4]; the one link again [G-1].",
  graph_citations: [
    { number: 1, label: "[G-1]", node_ids: ["n0", "n1"], link_ids: ["e0"] },
    { number: 2, label: "[G-2]", node_ids: ["n2", "n3"], link_ids: ["gone"] },
    { number: 3, label: "[G-3]", node_ids: ["n1", "n2", "n3"], link_ids: ["e1", "e2"] },
    { number: 4, label: "[G-4]", node_ids: ["nowhere"], link_ids: ["nothing"] },
  ],
};

/** Presses Tab until the focused element's accessible name is `name`; the walk an analyst makes. */
async function tabToLabel(page: Page, name: string, max = 40) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const label = await page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? "");
    if (label === name) return;
  }
  throw new Error(`Tab never reached ${name}`);
}

test("asking, then reaching a [G-n] from the answer by Tab, selects what it stands for on the real canvas", async ({ page }) => {
  // ADR-129 decision 1, against the real canvas (harness.html?questions=1), not a recording fake: a
  // fact with one drawn link selects the link; a link not drawn, or several links, select the nodes;
  // a fact with nothing in view leaves the selection as it was; a repeated marker is a button too.
  const { scopes } = await serve(page, [], GRAPH_FACTS, "/keyboard/harness.html?questions=1");
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who is connected to n0?");
  await page.keyboard.press("Control+Enter");
  await expect(page.getByRole("button", { name: "Select [G-1] on the canvas" })).toHaveCount(2);
  expect(scopes).toEqual([{ question: "Who is connected to n0?", selected_node_ids: [], selected_link_ids: [] }]);
  const state = () => page.evaluate(() => ({ nodes: window.__KEYBOARD__!.selection, edge: window.__KEYBOARD__!.selectedEdge }));
  await page.getByLabel("Your question").focus();

  await tabToLabel(page, "Select [G-1] on the canvas");
  await page.keyboard.press("Enter");
  await expect.poll(state).toEqual({ nodes: [], edge: "e0" });

  await tabToLabel(page, "Select [G-2] on the canvas");
  await page.keyboard.press("Enter");
  await expect.poll(state).toEqual({ nodes: ["n2", "n3"], edge: null });

  await tabToLabel(page, "Select [G-3] on the canvas");
  await page.keyboard.press("Enter");
  await expect.poll(state).toEqual({ nodes: ["n1", "n2", "n3"], edge: null });

  await tabToLabel(page, "Select [G-4] on the canvas");
  await page.keyboard.press("Enter");
  // Nothing in view: the selection is left as it was.
  await expect.poll(state).toEqual({ nodes: ["n1", "n2", "n3"], edge: null });
  registerCovered(REGISTRY, "select-a-graph-fact-from-an-answer-by-keyboard");
});

test("every registered questions action has its own proving test case above", () => {
  assertAllCovered("QUESTIONS_ACTIONS", QUESTIONS_ACTIONS);
});
