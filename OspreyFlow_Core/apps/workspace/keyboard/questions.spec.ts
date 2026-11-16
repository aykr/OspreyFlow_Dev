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

test("Ask & Chat's page is left by its visible Back to Graph, its first control, reached by keyboard", async ({ page }) => {
  // The owner, 9 October 2026: "how do I close the questions panel?" — Escape alone said nothing. ADR-145 Amendment 18:
  // the page's way out is Back to ‹view›, reached by Shift+Tab from the heading. Amendment 20: the page is the drawer
  // expanded (`?form=page` opens it there, as the results' Ask line does).
  await serve(page, [ANSWER], ANSWER, "/keyboard/questions-harness.html?form=page");
  const askPage = page.getByRole("region", { name: "Ask & Chat" });
  await askPage.getByRole("heading", { name: "Ask & Chat" }).focus();
  await page.keyboard.press("Shift+Tab");
  await expect(askPage.getByRole("button", { name: "Back to Graph" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__QUESTIONS__?.closed ?? 0)).toBe(1);
  await expect(askPage).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "Ask & Chat" })).toHaveCount(0);
  registerCovered(REGISTRY, "back-from-ask-and-chat-by-keyboard");
});

test("Expand and Show as a drawer keep the question typed, the engine chosen and the scroll position, by keyboard", async ({ page }) => {
  // ADR-145 Amendment 20 decision 2 (rule 13): the drawer and the page are one panel in two shapes, never mounted
  // again, so what the analyst had in hand goes with it both ways. Forty earlier questions, so both shapes scroll.
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
  const history = Array.from({ length: 40 }, (_, i) => ({
    ...ANSWER,
    id: `q-${i + 1}`,
    question: `Earlier question ${i + 1}?`,
    candidates: [],
    citations: [],
    created_at: `2026-10-07T10:${String(i).padStart(2, "0")}:00Z`,
  }));
  await serve(page, history);
  const drawer = page.getByRole("dialog", { name: "Ask & Chat" });
  const askPage = page.getByRole("region", { name: "Ask & Chat" });
  await expect(drawer).toBeVisible();
  const choice = drawer.getByRole("combobox", { name: "Model engine" });
  await expect(choice).toHaveValue("gemini");
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who paid Kestrel?");
  await page.keyboard.press("Shift+Tab");
  await expect(choice).toBeFocused();
  await page.keyboard.type("This");
  await expect(choice).toHaveValue("local");
  // Scrolled to the middle of the history (a setup, not an action of the analyst's: no mouse).
  const middle = page.getByText("Earlier question 20?", { exact: true });
  await middle.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await expect(middle).toBeInViewport();
  await expect(page.getByText("Earlier question 1?", { exact: true })).not.toBeInViewport();
  const expand = drawer.getByRole("button", { name: "Expand Ask & Chat to the full page" });
  await expand.focus();
  await page.keyboard.press("Enter");
  await expect(askPage).toBeVisible();
  await expect(askPage.getByLabel("Your question")).toHaveValue("Who paid Kestrel?");
  await expect(askPage.getByRole("combobox", { name: "Model engine" })).toHaveValue("local");
  await expect(middle).toBeInViewport();
  await expect(page.getByText("Earlier question 1?", { exact: true })).not.toBeInViewport();
  await askPage.getByRole("button", { name: "Show as a drawer" }).focus();
  await page.keyboard.press("Enter");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByLabel("Your question")).toHaveValue("Who paid Kestrel?");
  await expect(drawer.getByRole("combobox", { name: "Model engine" })).toHaveValue("local");
  await expect(middle).toBeInViewport();
  await expect(page.getByText("Earlier question 1?", { exact: true })).not.toBeInViewport();
  registerCovered(REGISTRY, "expand-and-show-as-a-drawer-keep-the-question-by-keyboard");
});

test("a [G-n] chosen on Ask & Chat's page leaves it, selects what it stands for on the real canvas, and focus is on the canvas", async ({ page }) => {
  // ADR-145 Amendment 18 decision 5 (rule 13), against the real canvas and App's own hook (harness.html?questions=page).
  await serve(page, [], GRAPH_FACTS, "/keyboard/harness.html?questions=page");
  const askPage = page.getByRole("region", { name: "Ask & Chat" });
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who is connected to n0?");
  await page.keyboard.press("Control+Enter");
  await expect(page.getByRole("button", { name: "Show on the graph: graph fact 1, [G-1]" })).toHaveCount(2);
  await page.getByLabel("Your question").focus();
  await tabToLabel(page, "Show on the graph: graph fact 1, [G-1]");
  await page.keyboard.press("Enter");
  await expect(askPage).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__!.selectedEdge)).toBe("e0");
  await expect(page.getByRole("application", { name: "Network canvas" })).toBeFocused();
  registerCovered(REGISTRY, "select-a-graph-fact-from-the-ask-page-by-keyboard");
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
  await expect(page.getByRole("button", { name: "Show on the graph: graph fact 1, [G-1]" })).toHaveCount(2);
  expect(scopes).toEqual([{ question: "Who is connected to n0?", selected_node_ids: [], selected_link_ids: [], read_from: "graph" }]);
  const state = () => page.evaluate(() => ({ nodes: window.__KEYBOARD__!.selection, edge: window.__KEYBOARD__!.selectedEdge }));
  await page.getByLabel("Your question").focus();

  await tabToLabel(page, "Show on the graph: graph fact 1, [G-1]");
  await page.keyboard.press("Enter");
  await expect.poll(state).toEqual({ nodes: [], edge: "e0" });

  await tabToLabel(page, "Show on the graph: graph fact 2, [G-2]");
  await page.keyboard.press("Enter");
  await expect.poll(state).toEqual({ nodes: ["n2", "n3"], edge: null });

  await tabToLabel(page, "Show on the graph: graph fact 3, [G-3]");
  await page.keyboard.press("Enter");
  await expect.poll(state).toEqual({ nodes: ["n1", "n2", "n3"], edge: null });

  await tabToLabel(page, "Show on the graph: graph fact 4, [G-4]");
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
  await expect(page.getByText("Answered by this deployment's own model (qwen2.5:7b-instruct)", { exact: true })).toBeVisible();
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
  await expect(page.getByRole("button", { name: "Show on the graph: N2, [S-1]" })).toBeVisible();
  await page.getByLabel("Your question").focus();
  await tabToLabel(page, "Show on the graph: N2, [S-1]");
  await page.keyboard.press("Enter");
  await expect.poll(state).toEqual({ nodes: ["n2", "n3"], edge: null });
  registerCovered(REGISTRY, "select-a-search-source-from-an-answer-by-keyboard");
});

// v0.6.0 #3: the history is an accordion. Each earlier question is its line, a button (aria-expanded); a closed
// answer's markers and proposals are never reached by Tab; Enter on the line opens it, and its markers are then reached.
test("an earlier answer is opened from its question's line by keyboard, its markers reached only then", async ({ page }) => {
  await page.goto("/keyboard/questions-harness.html?history=1");
  const older = page.getByRole("button", { name: /^Who is tied to Dana\?/ });
  const proposals = page.getByRole("button", { name: /^Who wrote about the plant\?/ });
  await expect(older).toHaveAttribute("aria-expanded", "false");
  await expect(proposals).toHaveAttribute("aria-expanded", "false");
  await expect(proposals).toContainText("2 proposals to decide");
  await expect(page.getByRole("button", { name: /^Who called Callum\?/ })).toHaveAttribute("aria-expanded", "true");
  // Every stop Tab makes through the panel, from its start: none is a closed answer's marker or proposal.
  // From Ask & Chat's heading, its start (the drawer's, by default: ADR-145 Amendment 20).
  await page.getByRole("heading", { name: "Ask & Chat" }).focus();
  const stops: string[] = [];
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    stops.push(await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      return el ? el.getAttribute("aria-label") ?? el.textContent ?? "" : "";
    }));
  }
  expect(stops.filter((s) => /SHAH, Rohan|^Accept |^Reject /.test(s))).toEqual([]);
  expect(stops.some((s) => s.includes("MERCER, Dana – called – PRICE, Callum"))).toBe(true); // the newest's, open
  // Enter on the earlier question's line opens it; its markers are then reached by Tab, after the line.
  await older.focus();
  await page.keyboard.press("Enter");
  await expect(older).toHaveAttribute("aria-expanded", "true");
  await tabToLabel(page, "Show on the graph: SHAH, Rohan – associated with – MERCER, Dana, [G-1]");
  // And Enter closes it again.
  await older.focus();
  await page.keyboard.press("Enter");
  await expect(older).toHaveAttribute("aria-expanded", "false");
  registerCovered(REGISTRY, "open-an-earlier-answer-by-keyboard");
});

// v0.6.0 #5: *Show all on graph* and *Save as a view* under an answer, by keyboard, against the real canvas
// (harness.html?questions=1, wired as `App.tsx` wires them through `questions/showAnswer.ts`).
/** An answer whose markers stand for n2 and n3 (on the canvas), n9 (not yet) and one the reader may not see. */
const SHOW_ALL = {
  ...ANSWER,
  id: "q-all",
  question: "Who is near n2?",
  answer: "n2 knows n3 [G-1], and n9 is near [G-2].",
  citations: [],
  candidates: [],
  graph_citations: [
    { number: 1, label: "[G-1]", about: "n2 and n3", node_ids: ["n2", "n3"], link_ids: ["e2"] },
    { number: 2, label: "[G-2]", about: "n9", node_ids: ["n9", "hidden-1"], link_ids: [] },
  ],
};
const N9 = {
  id: "n9", type: "Person", properties: { family_name: "n9" },
  provenance: { state: "asserted", sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }], first_seen: "2026-01-01T00:00:00Z" },
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
  audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
}; // prettier-ignore

async function askForAll(page: Page, addAnswer: (route: import("@playwright/test").Route) => Promise<void>, at = "/keyboard/harness.html?questions=1") {
  const added: unknown[] = [];
  await page.route("**/v1/investigations/*/working-set/add-by-ids", async (route) => {
    added.push(route.request().postDataJSON());
    await addAnswer(route);
  });
  await serve(page, [], SHOW_ALL, at);
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who is near n2?");
  await page.keyboard.press("Control+Enter");
  await expect(page.getByRole("button", { name: "Show all on graph", exact: true })).toBeVisible();
  return added;
}

test("Show all on graph under an answer puts every item it stands for on the real canvas and selects them, by keyboard, saying how many could not be shown", async ({ page }) => {
  const added = await askForAll(page, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ outcome: { delta: { seq: 9, op: "add", nodes: [N9], edges: [] }, links_among: "not_asked" }, not_shown: 1 }),
    }),
  );
  const state = () => page.evaluate(() => ({ nodes: window.__KEYBOARD__!.selection, said: window.__KEYBOARD__!.said ?? null }));
  const show = page.getByRole("button", { name: "Show all on graph", exact: true });
  await show.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => added).toEqual([{ node_ids: ["n2", "n3", "n9", "hidden-1"], link_ids: ["e2"] }]);
  // Every item of the answer on the canvas is selected together: the two already there and n9 just added; the one
  // the reader may not see is counted, never named.
  await expect.poll(async () => (await state()).nodes.slice().sort()).toEqual(["n2", "n3", "n9"]);
  expect((await state()).said).toBe("1 of this answer's items could not be shown.");
  registerCovered(REGISTRY, "show-all-of-an-answers-items-on-the-graph-by-keyboard");
});

test("Show all on graph on Ask & Chat's page leaves it, selects the answer's items on the real canvas, and focus is on the canvas", async ({ page }) => {
  // ADR-145 Amendment 18 (rule 13), against the real canvas and App's own hook (harness.html?questions=page).
  const added = await askForAll(
    page,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ outcome: { delta: { seq: 9, op: "add", nodes: [N9], edges: [] }, links_among: "not_asked" }, not_shown: 1 }),
      }),
    "/keyboard/harness.html?questions=page",
  );
  // Reached by Tab from the question, as a person would (rule 13), not focused by the test.
  await page.getByLabel("Your question").focus();
  await tabToText(page, "Show all on graph");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Ask & Chat" })).toHaveCount(0);
  await expect.poll(() => added).toEqual([{ node_ids: ["n2", "n3", "n9", "hidden-1"], link_ids: ["e2"] }]);
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__!.selection.slice().sort())).toEqual(["n2", "n3", "n9"]);
  await expect(page.getByRole("application", { name: "Network canvas" })).toBeFocused();
  registerCovered(REGISTRY, "show-all-from-the-ask-page-by-keyboard");
});

// The orchestrator's ruling R1 (ADR-145 Amendment 20, rule 13), on the real canvas and App's own hook
// (harness.html?questions=drawer): in the drawer a marker brings its fact into view and focus to the canvas, and the
// drawer stays beside it, as before Amendment 18 (ADR-129 decision 1); Escape from the canvas then closes the drawer,
// focus left on the canvas, as a drawer's Escape does.
test("a [G-n] chosen in Ask & Chat's drawer selects on the real canvas, the drawer kept, focus on the canvas; Escape there closes it", async ({ page }) => {
  await serve(page, [], GRAPH_FACTS, "/keyboard/harness.html?questions=drawer");
  const drawer = page.getByRole("dialog", { name: "Ask & Chat" });
  await expect(drawer).toBeVisible();
  await page.getByLabel("Your question").focus();
  await page.keyboard.type("Who is connected to n0?");
  await page.keyboard.press("Control+Enter");
  await expect(page.getByRole("button", { name: "Show on the graph: graph fact 1, [G-1]" })).toHaveCount(2);
  await page.getByLabel("Your question").focus();
  await tabToLabel(page, "Show on the graph: graph fact 1, [G-1]");
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__!.selectedEdge)).toBe("e0");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await expect(canvas).toBeFocused();
  await expect(drawer).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(canvas).toBeFocused();
  registerCovered(REGISTRY, "select-a-graph-fact-from-the-ask-drawer-by-keyboard");
});

test("Show all on graph in Ask & Chat's drawer selects the answer's items on the real canvas, the drawer kept, focus on the canvas", async ({ page }) => {
  const added = await askForAll(
    page,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ outcome: { delta: { seq: 9, op: "add", nodes: [N9], edges: [] }, links_among: "not_asked" }, not_shown: 1 }),
      }),
    "/keyboard/harness.html?questions=drawer",
  );
  await page.getByLabel("Your question").focus();
  await tabToText(page, "Show all on graph");
  await page.keyboard.press("Enter");
  await expect.poll(() => added).toEqual([{ node_ids: ["n2", "n3", "n9", "hidden-1"], link_ids: ["e2"] }]);
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__!.selection.slice().sort())).toEqual(["n2", "n3", "n9"]);
  await expect(page.getByRole("application", { name: "Network canvas" })).toBeFocused();
  await expect(page.getByRole("dialog", { name: "Ask & Chat" })).toBeVisible();
  registerCovered(REGISTRY, "show-all-from-the-ask-drawer-by-keyboard");
});

/** Tab until the focused control's own text is `text` (a button named by its words, not an aria-label). */
async function tabToText(page: Page, text: string, max = 40) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    if ((await page.evaluate(() => document.activeElement?.textContent?.trim() ?? "")) === text) return;
  }
  throw new Error(`Tab never reached ${text}`);
}

test("Show all on graph on Ask & Chat's page past the cap leaves the page, adds nothing, and its words say where Save as a view is (rule 2)", async ({ page }) => {
  await askForAll(
    page,
    (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ error: "limit_exceeded", cap_kind: "nodes", cap: 50000, would_be: 50003, options: [] }),
      }),
    "/keyboard/harness.html?questions=page",
  );
  await page.getByLabel("Your question").focus();
  await tabToText(page, "Show all on graph");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Ask & Chat" })).toHaveCount(0);
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__!.said ?? ""))
    .toBe("Too many for the canvas: 50,003 nodes against a limit of 50,000. Nothing was added; Save as a view, under the answer in Ask & Chat, keeps them all.");
  // The canvas focused selects its first node, as any arrival there does; nothing of the answer is selected.
  expect(await page.evaluate(() => window.__KEYBOARD__!.selection.slice())).toEqual(["n0"]);
});

test("Show all on graph past the working set's cap adds nothing and says the cap's own figures (rule 2)", async ({ page }) => {
  await askForAll(page, (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ error: "limit_exceeded", cap_kind: "nodes", cap: 50000, would_be: 50003, options: [] }),
    }),
  );
  const before = await page.evaluate(() => window.__KEYBOARD__!.selection.slice());
  await page.getByRole("button", { name: "Show all on graph", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__!.said ?? ""))
    .toBe("Too many for the canvas: 50,003 nodes against a limit of 50,000. Nothing was added; Save as a view, under the answer in Ask & Chat, keeps them all.");
  expect(await page.evaluate(() => window.__KEYBOARD__!.selection.slice())).toEqual(before);
});

test("Save as a view under an answer saves its items as a saved view, by keyboard", async ({ page }) => {
  const saves: unknown[] = [];
  await page.route("**/v1/investigations/*/views", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    saves.push(route.request().postDataJSON());
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "v-a", case_id: "keyboard-fixture", name: "Answer: Who is near n2?", created_by: "analyst-1", created_at: "2026-11-15T10:00:00Z", shared: false, chosen: 4 }),
    });
  });
  await askForAll(page, (route) => route.fulfill({ status: 500, body: "{}" }));
  const save = page.getByRole("button", { name: "Save as a view", exact: true });
  await save.focus();
  await page.keyboard.press("Enter");
  await expect(save).toHaveAttribute("aria-expanded", "true");
  const name = page.getByLabel("View name");
  await expect(name).toBeFocused();
  await expect(name).toHaveValue("Answer: Who is near n2?");
  await page.keyboard.press("Enter");
  await expect.poll(() => saves.length).toBe(1);
  expect(saves[0]).toMatchObject({ name: "Answer: Who is near n2?", node_ids: ["n2", "n3", "n9", "hidden-1"] });
  await expect(name).toHaveCount(0);
  registerCovered(REGISTRY, "save-an-answers-items-as-a-view-by-keyboard");
});

test("the page the axe scan reads draws an answer's actions and its open Save as a view form (v0.6.0 #5)", async ({ page }) => {
  // So `a11y/every-harness.spec.ts`'s questions-harness.html case=1&save=1 scans them, not a page without them.
  await page.goto("/keyboard/questions-harness.html?case=1&save=1");
  const actions = page.getByRole("group", { name: "This answer's items" });
  await expect(actions.getByRole("button", { name: "Show all on graph", exact: true })).toBeVisible();
  await expect(actions.getByRole("button", { name: "Save as a view", exact: true })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByLabel("View name")).toHaveValue("Answer: Who paid Kestrel?");
});

test("every registered questions action has its own proving test case above", () => {
  assertAllCovered("QUESTIONS_ACTIONS", QUESTIONS_ACTIONS);
});
