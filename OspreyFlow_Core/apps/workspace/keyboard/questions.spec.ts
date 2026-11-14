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

/** A summary's *Whole case* fields, under another choice (ADR-098 Amendment 9). */
const NOT_CASE = { found: 0, passages: 0, limited_reason: null, counts_exact: true, more: false };

/** What the Conduit says will be read (ADR-098 Amendments 7 and 9), for the scope the panel sent. */
function willRead(posted: { read_from?: string }) {
  const selection = posted.read_from === "selection";
  if (posted.read_from === "case") {
    return {
      read: {
        read_from: "case", documents: 0, documents_without_text: 0, items: 1, links: 0, events: 0, selected: 0,
        first_selected: null, found: 2, passages: 1, limited_reason: null, counts_exact: true, more: false,
      },
      engine: "local", engine_label: "This deployment's own model", model: "qwen2.5:7b-instruct", unusable: [], refused: null,
    };  // prettier-ignore
  }
  return {
    read: {
      read_from: selection ? "selection" : "graph", documents: selection ? 1 : 2, documents_without_text: 0,
      items: selection ? 2 : 5, links: selection ? 1 : 4, events: 0, selected: selection ? 1 : 0,
      first_selected: selection ? "Mercer, Dana" : null, ...NOT_CASE,
    },
    engine: "local", engine_label: "This deployment's own model", model: "qwen2.5:7b-instruct", unusable: [], refused: null,
  };  // prettier-ignore
}

async function serve(page: Page, history: unknown[] = [], answer: unknown = ANSWER, harness = "/keyboard/questions-harness.html") {
  const asked: string[] = [];
  const scopes: unknown[] = [];
  const decided: string[] = [];
  const willReads: { read_from?: string; question?: string }[] = [];
  await page.route("**/*/v1/investigations/*/questions**", async (route) => {
    const request = route.request();
    const url = request.url();
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (request.method() === "GET") return json(200, history);
    if (url.endsWith("/will-read")) {
      const posted = request.postDataJSON() as { read_from?: string; question?: string };
      willReads.push(posted);
      return json(200, willRead(posted));
    }
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
  return { asked, decided, scopes, willReads };
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
  // ADR-145 Amendment 12: the drawer is Ask & Chat (Questions renamed), its Close named after it.
  const close = page.getByRole("button", { name: "Close Ask & Chat" });
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
  expect(scopes).toEqual([{ question: "Who is connected to n0?", selected_node_ids: [], selected_link_ids: [], read_from: "graph" }]);
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

test("the model engine is reached from the question by Shift+Tab, changed by keyboard, and named in the question", async ({ page }) => {
  // ADR-135 decision 5 (rule 13): the choice lists the engines offered, the default chosen; a
  // keyboard change is what the question sends, and the answer says which engine answered.
  // ADR-136: the case's own engines route.
  await page.route("**/*/v1/investigations/*/models/engines", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        engines: [
          { name: "local", label: "This deployment's own model", roles: ["extraction"], default_for: [] },
          { name: "gemini", label: "Gemini", roles: ["extraction"], default_for: ["extraction"] },
        ],
      }),
    }),
  );
  const { scopes } = await serve(page, [], { ...ANSWER, engine: "local", model: "qwen2.5:7b-instruct" });
  const choice = page.getByRole("combobox", { name: "Model engine" });
  await expect(choice).toHaveValue("gemini");
  await page.getByLabel("Your question").focus();
  await page.keyboard.press("Shift+Tab");
  await expect(choice).toBeFocused();
  // A closed select takes an arrow key differently by platform (macOS opens the menu); typing the
  // start of an option's label chooses it everywhere (`link-change.spec.ts`'s own note).
  await page.keyboard.type("This");
  await expect(choice).toHaveValue("local");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Your question")).toBeFocused();
  await page.keyboard.type("Who wrote about the plant?");
  await page.keyboard.press("Control+Enter");
  // Exact: "Will be answered by …" (ADR-135 Amendment 12) above the question holds these words too.
  await expect(page.getByText("Answered by This deployment's own model (qwen2.5:7b-instruct)", { exact: true })).toBeVisible();
  expect((scopes[0] as { engine?: string }).engine).toBe("local");
  registerCovered(REGISTRY, "choose-the-model-engine-by-keyboard");
});

test("asked in a view, the questions go through it, and Ask about the whole case instead leaves it, by keyboard (ADR-144 decision 4)", async ({ page }) => {
  const lists: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "GET" && /\/v1\/investigations\/[^/]+\/questions/.test(request.url())) lists.push(new URL(request.url()).search);
  });
  const { scopes } = await serve(page, [], ANSWER, "/keyboard/questions-harness.html?view=1");
  await expect(page.getByRole("status")).toContainText("Asking in the view Questions on 2 items");
  await expect.poll(() => lists).toEqual(["?view_id=v-q"]);
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who wrote about the plant?");
  await page.keyboard.press("Control+Enter");
  await expect(page.getByText("Dana Mercer wrote about it [1].")).toBeVisible();
  expect((scopes[0] as { view_id?: string }).view_id).toBe("v-q");

  const leave = page.getByRole("button", { name: "Ask about the whole case instead" });
  await leave.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Asking in the view")).toHaveCount(0);
  await expect.poll(() => lists.at(-1)).toBe("");
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("And the whole case?");
  await page.keyboard.press("Control+Enter");
  await expect.poll(() => scopes.length).toBe(2);
  expect((scopes[1] as { view_id?: string }).view_id).toBeUndefined();
  registerCovered(REGISTRY, "ask-in-a-view-then-about-the-whole-case-by-keyboard");
});

test("what to read from is chosen by arrow keys, the Conduit says what will be read, and the question sends the choice (ADR-098 Amendment 7)", async ({ page }) => {
  const { scopes, willReads } = await serve(page);
  const selected = page.getByRole("radio", { name: "Selected items" });
  const everything = page.getByRole("radio", { name: "Everything on the graph" });
  await expect(selected).toBeChecked(); // the harness has Dana selected
  await expect(page.getByText("About: Mercer, Dana")).toBeVisible();
  await expect(page.getByText("Will read: 1 document, 2 items and 1 link")).toBeVisible();
  await expect(page.getByText("Will be answered by This deployment's own model (qwen2.5:7b-instruct)")).toBeVisible();
  await expect(page.getByRole("radio", { name: "Whole case" })).toBeEnabled(); // ADR-098 Amendment 9
  await selected.focus();
  await page.keyboard.press("ArrowDown");
  await expect(everything).toBeChecked();
  await expect(everything).toBeFocused();
  await expect(page.getByText("About: everything on the graph")).toBeVisible();
  await expect.poll(() => willReads.at(-1)?.read_from).toBe("graph");
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who wrote about the plant?");
  await page.keyboard.press("Control+Enter");
  await expect.poll(() => scopes.length).toBe(1);
  // The choice is closed while the question is asked: wait for the answer before moving it again.
  await expect(page.getByText("Dana Mercer wrote about it [1].")).toBeVisible();
  expect((scopes[0] as { read_from?: string; selected_node_ids?: string[] }).read_from).toBe("graph");
  expect((scopes[0] as { selected_node_ids?: string[] }).selected_node_ids).toEqual([]);
  await everything.focus();
  await page.keyboard.press("ArrowUp");
  await expect(selected).toBeChecked();
  await expect.poll(() => willReads.at(-1)?.read_from).toBe("selection");
  // Asked again with Selected items: the question sends the choice and what is selected.
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("And about Dana?");
  await page.keyboard.press("Control+Enter");
  await expect.poll(() => scopes.length).toBe(2);
  expect(scopes[1]).toMatchObject({ read_from: "selection", selected_node_ids: ["n-dana"], selected_link_ids: [] });
  registerCovered(REGISTRY, "choose-what-to-read-from-by-keyboard");
});

/** An answer read from the whole case (ADR-098 Amendment 9), citing a source found by search. */
const FROM_THE_CASE = {
  ...ANSWER,
  id: "q-case",
  answer: "n2 and n3 are the one person [S-1].",
  citations: [],
  candidates: [],
  read: { read_from: "case", documents: 0, documents_without_text: 0, items: 1, links: 0, events: 0, selected: 0,
          first_selected: null, found: 2, passages: 1, limited_reason: null, counts_exact: true, more: false },
  search_citations: [
    { number: 1, label: "[S-1]", name: "N2", type: "Person", why: "Name is 'n2'", node_ids: ["n2", "n3"] },
  ],
};  // prettier-ignore

test("Whole case is chosen by arrow keys, its search is asked with the question's words, and an [S-n] selects its records on the real canvas (ADR-098 Amendment 9)", async ({ page }) => {
  // ADR-129 Amendment 5, against the real canvas: a source found by search selects its records as a
  // graph fact does.
  const { scopes, willReads } = await serve(page, [], FROM_THE_CASE, "/keyboard/harness.html?questions=1");
  const everything = page.getByRole("radio", { name: "Everything on the graph" });
  const whole = page.getByRole("radio", { name: "Whole case" });
  await expect(everything).toBeChecked(); // nothing is selected on the harness canvas
  await everything.focus();
  await page.keyboard.press("ArrowDown");
  await expect(whole).toBeChecked();
  await expect(whole).toBeFocused();
  await expect(page.getByText("Whole case finds things by their names and words, not by what they mean.")).toBeVisible();
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who is n2?");
  await expect.poll(() => willReads.at(-1)).toMatchObject({ read_from: "case", question: "Who is n2?" });
  await expect(page.getByText("Will read: 2 matches found in the case: 1 document by the passage found and 1 other record")).toBeVisible();
  await page.keyboard.press("Control+Enter");
  await expect.poll(() => scopes.length).toBe(1);
  expect(scopes[0]).toMatchObject({ question: "Who is n2?", read_from: "case", selected_node_ids: [] });

  const state = () => page.evaluate(() => ({ nodes: window.__KEYBOARD__!.selection, edge: window.__KEYBOARD__!.selectedEdge }));
  await page.getByLabel("Your question").focus();
  await tabToLabel(page, "Select [S-1], N2, on the canvas");
  await page.keyboard.press("Enter");
  await expect.poll(state).toEqual({ nodes: ["n2", "n3"], edge: null });
  registerCovered(REGISTRY, "select-a-search-source-from-an-answer-by-keyboard");
});

test("every registered questions action has its own proving test case above", () => {
  assertAllCovered("QUESTIONS_ACTIONS", QUESTIONS_ACTIONS);
});
