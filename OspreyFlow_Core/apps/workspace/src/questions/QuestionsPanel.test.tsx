// @vitest-environment jsdom
// ADR-098 decision 4: the case's questions to the model. The panel shows what the Conduit returns
// and nothing more; a refusal is said in words; an accepted proposal's change reaches the view.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QuestionsPanel, WHOLE_CASE_LINE } from "./QuestionsPanel";
import type { QuestionAnswer, WillRead } from "./questionsApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ANSWERED: QuestionAnswer = {
  id: "q1",
  author: "analyst-1",
  question: "Who wrote about the plant?",
  answer: "Dana Mercer wrote about it [1].",
  citations: [{ document_id: "email:ev-1", title: "Dabhol" }],
  candidates: [
    {
      id: "c1",
      document_id: "email:ev-1",
      entity_type: "Person",
      properties: { name: "Dana Mercer" },
      confidence: 0.8,
      status: "pending",
      model: "qwen",
    },
  ],
  unplaced: 1,
  created_at: "2026-10-07T10:00:00Z",
};

const WITH_FACTS: QuestionAnswer = {
  ...ANSWERED,
  id: "q2",
  answer: "Rohan is tied to Dana [G-1]; Dana called Callum [G-2].",
  graph_citations: [
    { number: 1, label: "[G-1]", node_ids: ["n-rohan", "n-dana"], link_ids: ["l-assoc"] },
    { number: 2, label: "[G-2]", node_ids: ["n-dana", "n-callum"], link_ids: ["l-called"] },
  ],
  unplaced: 0,
};

/** A summary's *Whole case* fields, under another choice (ADR-098 Amendment 9). */
const NOT_CASE = { found: 0, passages: 0, limited_reason: null, counts_exact: true, more: false };

/** What the Conduit says will be read (ADR-098 Amendment 7): served to every test that does not
 * serve its own. */
const WILL: WillRead = {
  read: { read_from: "graph", documents: 2, documents_without_text: 0, items: 5, links: 4, events: 0, selected: 0, first_selected: null, ...NOT_CASE },
  engine: "local",
  engine_label: "This deployment's own model",
  model: "qwen2.5:7b-instruct",
  unusable: [],
  refused: null,
};  // prettier-ignore

function serve(given: Record<string, (init?: RequestInit) => Response>) {
  const routes: Record<string, (init?: RequestInit) => Response> = {
    "POST /questions/will-read": () => json(200, WILL),
    ...given,
  };
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      const key = `${init?.method ?? "GET"} ${url.replace("http://api/v1/investigations/b1", "")}`;
      const handler = routes[key];
      if (!handler) throw new Error(`unexpected ${key}`);
      return handler(init);
    }),
  );
  return calls;
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

function mount(
  onDelta = vi.fn(),
  onOpenDocument = vi.fn(),
  extra: Partial<React.ComponentProps<typeof QuestionsPanel>> = {},
) {
  render(
    <QuestionsPanel
      apiBaseUrl="http://api"
      bearerToken="t"
      investigationId="b1"
      onDelta={onDelta}
      onOpenDocument={onOpenDocument}
      {...extra}
    />,
  );
  return { onDelta, onOpenDocument };
}

describe("QuestionsPanel", () => {
  it("shows the case's conversation: the answer, what it draws on, the proposals and those left out", async () => {
    serve({ "GET /questions": () => json(200, [ANSWERED]) });
    const { onOpenDocument } = mount();
    expect(await screen.findByText("Dana Mercer wrote about it [1].")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Dabhol" }));
    expect(onOpenDocument).toHaveBeenCalledWith("email:ev-1");
    expect(screen.getByRole("button", { name: "Accept Person · Dana Mercer" })).toBeTruthy();
    expect(screen.getByText(/1 item was left out/)).toBeTruthy();
  });

  it("asks, and adds the answer to the conversation", async () => {
    const calls = serve({
      "GET /questions": () => json(200, []),
      "POST /questions": () => json(200, ANSWERED),
    });
    mount();
    await screen.findByText("No questions asked in this case yet.");
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Who wrote about the plant?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Dana Mercer wrote about it [1].")).toBeTruthy();
    const posted = calls.find((c) => c.init?.method === "POST" && c.url.endsWith("/questions"))!;
    expect(JSON.parse(String(posted.init!.body))).toEqual({
      question: "Who wrote about the plant?",
      selected_node_ids: [],
      selected_link_ids: [],
      read_from: "graph",
    });
  });

  it("sends what is selected on the canvas and the timeline window, so the brief is those and one link around them", async () => {
    const calls = serve({
      "GET /questions": () => json(200, []),
      "POST /questions": () => json(200, ANSWERED),
    });
    mount(vi.fn(), vi.fn(), {
      selection: { nodeIds: ["n-dana"], linkIds: ["l-called"] },
      getTimelineWindow: () => ({ validFrom: "2026-01-01T00:00:00Z", validTo: null }),
    });
    await screen.findByText("No questions asked in this case yet.");
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Who?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Dana Mercer wrote about it [1].");
    const posted = calls.find((c) => c.init?.method === "POST" && c.url.endsWith("/questions"))!;
    expect(JSON.parse(String(posted.init!.body))).toEqual({
      question: "Who?",
      selected_node_ids: ["n-dana"],
      selected_link_ids: ["l-called"],
      window: { valid_from: "2026-01-01T00:00:00Z", valid_to: null },
      read_from: "selection",
    });
  });

  it("shows each [G-n] the payload holds as a button, once, and selecting one hands its ids to the canvas", async () => {
    serve({ "GET /questions": () => json(200, [WITH_FACTS]) });
    const onSelectFacts = vi.fn();
    mount(vi.fn(), vi.fn(), { onSelectFacts });
    fireEvent.click(await screen.findByRole("button", { name: "Select [G-2] on the canvas" }));
    expect(onSelectFacts).toHaveBeenCalledWith({
      number: 2,
      label: "[G-2]",
      node_ids: ["n-dana", "n-callum"],
      link_ids: ["l-called"],
    });
    expect(screen.getAllByRole("button", { name: /Select \[G-\d+\] on the canvas/ })).toHaveLength(2);
  });

  it("makes every occurrence of a repeated [G-n] a button, so no marker is left as literal text", async () => {
    serve({
      "GET /questions": () => json(200, [{ ...WITH_FACTS, answer: "Dana [G-1] knows Rohan [G-1], and called Callum [G-2]." }]),
    });
    const onSelectFacts = vi.fn();
    mount(vi.fn(), vi.fn(), { onSelectFacts });
    const buttons = await screen.findAllByRole("button", { name: "Select [G-1] on the canvas" });
    expect(buttons).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Select [G-2] on the canvas" })).toHaveLength(1);
    fireEvent.click(buttons[1]!);
    expect(onSelectFacts).toHaveBeenCalledWith(expect.objectContaining({ number: 1 }));
    // The words round them are still there, and no marker is left as plain text outside a button.
    const paragraph = buttons[0]!.parentElement!;
    expect(paragraph.textContent).toBe("Dana [G-1] knows Rohan [G-1], and called Callum [G-2].");
    const outside = Array.from(paragraph.children)
      .filter((child) => child.tagName !== "BUTTON")
      .map((child) => child.textContent)
      .join("");
    expect(outside).not.toMatch(/\[G-\d+\]/);
  });

  it("leaves a [G-n] the payload does not hold as plain words, not a button", async () => {
    serve({ "GET /questions": () => json(200, [{ ...WITH_FACTS, graph_citations: [] }]) });
    mount();
    expect(await screen.findByText(/\[G-1\]/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Select \[G-/ })).toBeNull();
  });

  it("says in words why a question too long to read at once was refused, with the three ways out, and keeps it", async () => {
    serve({
      "GET /questions": () => json(200, []),
      "POST /questions": () =>
        json(409, {
          error: "limit_exceeded",
          cap_kind: "characters",
          cap: 80000,
          would_be: 120000,
          documents_chars: 70000,
          evidence_brief_chars: 50000,
          options: ["narrow_selection", "narrow_timeline_window", "ask_in_a_view"],
        }),
    });
    mount();
    await screen.findByText("No questions asked in this case yet.");
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Anything?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "This question comes to 120,000 characters, more than the model can read at once (80,000): " +
        "the documents are 70,000 and the graph facts 50,000. Nothing was sent. " +
        "Narrow the selection, narrow the timeline window, or ask in a smaller view, then ask again.",
    );
    expect((screen.getByLabelText("Your question") as HTMLTextAreaElement).value).toBe("Anything?");
  });

  it("says in the Conduit's words when there is nothing to read (ADR-098 Amendment 7: never for want of documents)", async () => {
    const words = "The graph holds nothing to read. Add items to the canvas first.";
    serve({
      "GET /questions": () => json(200, []),
      "POST /questions/will-read": () => json(422, { error: "nothing_to_read", detail: words }),
      "POST /questions": () => json(422, { error: "nothing_to_read", detail: words }),
    });
    mount();
    await screen.findByText("No questions asked in this case yet.");
    expect(await screen.findByText(words)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Anything?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect((await screen.findByRole("alert")).textContent).toBe(words);
  });

  it("accepting a proposal applies its change to the view and marks it accepted", async () => {
    const delta = { seq: 3, op: "add", nodes: [], edges: [] };
    serve({
      "GET /questions": () => json(200, [ANSWERED]),
      "POST /questions/candidates/c1/accept": () => json(200, { node_id: "n9", delta }),
    });
    const { onDelta } = mount();
    fireEvent.click(await screen.findByRole("button", { name: "Accept Person · Dana Mercer" }));
    await waitFor(() => expect(onDelta).toHaveBeenCalledWith(delta));
    expect(await screen.findByText("Accepted")).toBeTruthy();
  });

  it("rejecting a proposal writes nothing to the view and marks it rejected", async () => {
    serve({
      "GET /questions": () => json(200, [ANSWERED]),
      "POST /questions/candidates/c1/reject": () => json(200, { rejected: true }),
    });
    const { onDelta } = mount();
    fireEvent.click(await screen.findByRole("button", { name: "Reject Person · Dana Mercer" }));
    expect(await screen.findByText("Rejected")).toBeTruthy();
    expect(onDelta).not.toHaveBeenCalled();
  });

  it("in a view (ADR-144 decision 4) lists, asks and decides through that view, and says so", async () => {
    const delta = { seq: 3, op: "add", nodes: [], edges: [] };
    const calls = serve({
      "GET /questions?view_id=v%201": () => json(200, [ANSWERED]),
      "POST /questions": () => json(200, { ...ANSWERED, id: "q2", question: "Who wrote these?" }),
      "POST /questions/candidates/c1/accept?view_id=v%201": () => json(200, { node_id: "n9", delta }),
    });
    const onLeaveView = vi.fn();
    mount(vi.fn(), vi.fn(), { view: { id: "v 1", name: "Questions on 2 items" }, onLeaveView });
    expect((await screen.findByRole("status")).textContent).toContain("Asking in the view Questions on 2 items");
    fireEvent.click(await screen.findByRole("button", { name: "Accept Person · Dana Mercer" }));
    await screen.findByText("Accepted");
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Who wrote these?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Who wrote these?", { selector: "p" });
    const asked = calls.find((c) => c.init?.method === "POST" && c.url.endsWith("/questions"));
    expect(JSON.parse(asked?.init?.body as string).view_id).toBe("v 1");
    fireEvent.click(screen.getByRole("button", { name: "Ask about the whole case instead" }));
    expect(onLeaveView).toHaveBeenCalled();
  });
});

// ADR-135 decision 5: Ask the case offers the engines the deployment offers for extraction, the
// role's default chosen; the request names the one chosen; each answer says which engine and model
// produced it; a refused engine is said in the Conduit's words.
const ENGINES = {
  engines: [
    { name: "local", label: "This deployment's own model", roles: ["extraction", "embedding"], default_for: ["embedding"] },
    { name: "gemini", label: "Gemini", roles: ["extraction"], default_for: ["extraction"] },
    { name: "openai", label: "OpenAI", roles: ["vision"], default_for: [] },
  ],
};
const ONLY_LOCAL = {
  engines: [{ name: "local", label: "This deployment's own model", roles: ["extraction"], default_for: ["extraction"] }],
};

describe("the engine choice (ADR-135)", () => {
  // ADR-136: the case's own engines route, so an engine its data may not reach comes back disabled.
  const engineRoute = (body: unknown) => ({ "GET /models/engines": () => json(200, body) });

  it("lists only the engines offered for extraction, with the default chosen", async () => {
    serve({ "GET /questions": () => json(200, []), ...engineRoute(ENGINES) });
    mount();
    const choice = (await screen.findByRole("combobox", { name: "Model engine" })) as HTMLSelectElement;
    expect(Array.from(choice.options).map((o) => [o.value, o.textContent])).toEqual([
      ["local", "This deployment's own model"],
      ["gemini", "Gemini (no contract)"],
    ]);
    expect(choice.value).toBe("gemini");
  });

  it("is not shown when only the local engine is offered, and the request names none", async () => {
    const calls = serve({
      "GET /questions": () => json(200, []),
      "POST /questions": () => json(200, ANSWERED),
      ...engineRoute(ONLY_LOCAL),
    });
    mount();
    await screen.findByText("No questions asked in this case yet.");
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/v1/investigations/b1/models/engines"))).toBe(true));
    expect(screen.queryByRole("combobox", { name: "Model engine" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Who?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Dana Mercer wrote about it [1].");
    const posted = calls.find((c) => c.init?.method === "POST" && c.url.endsWith("/questions"))!;
    expect(JSON.parse(String(posted.init!.body))).not.toHaveProperty("engine");
  });

  it("sends the engine chosen, and the answer says which engine and model answered", async () => {
    const calls = serve({
      "GET /questions": () => json(200, []),
      "POST /questions": () => json(200, { ...ANSWERED, engine: "local", model: "qwen2.5:7b-instruct" }),
      ...engineRoute(ENGINES),
    });
    mount();
    const choice = await screen.findByRole("combobox", { name: "Model engine" });
    fireEvent.change(choice, { target: { value: "local" } });
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Who?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Answered by This deployment's own model (qwen2.5:7b-instruct)")).toBeTruthy();
    const posted = calls.find((c) => c.init?.method === "POST" && c.url.endsWith("/questions"))!;
    expect(JSON.parse(String(posted.init!.body)).engine).toBe("local");
  });

  it("names a provider's engine by its label on an answer in the history, and says nothing for an older answer", async () => {
    serve({
      "GET /questions": () => json(200, [{ ...ANSWERED, engine: "gemini", model: "gemini/gemini-2.5-flash" }, { ...WITH_FACTS }]),
      ...engineRoute(ENGINES),
    });
    mount();
    expect(await screen.findByText("Answered by Gemini (gemini/gemini-2.5-flash)")).toBeTruthy();
    expect(screen.getAllByText(/^Answered by/)).toHaveLength(1);
  });

  it("shows a refused engine's words", async () => {
    serve({
      "GET /questions": () => json(200, []),
      "POST /questions": () =>
        json(422, { error: "engine_refused", detail: "Gemini has no key on this deployment, so it is not offered." }),
      ...engineRoute(ENGINES),
    });
    mount();
    await screen.findByRole("combobox", { name: "Model engine" });
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Who?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Gemini has no key on this deployment, so it is not offered.",
    );
  });
});


describe("an engine the case's data may not reach (ADR-136)", () => {
  const REASON =
    "Not available for this case: “Enron corpus” is set to egress none, never sent to a hosted engine such as Gemini.";
  const BLOCKED = {
    engines: [
      { name: "local", label: "This deployment's own model", roles: ["extraction"], default_for: [], available: true },
      { name: "gemini", label: "Gemini", roles: ["extraction"], default_for: ["extraction"], privacy_contract: false,
        available: false, reason: REASON },
      { name: "anthropic", label: "Claude", roles: ["extraction"], default_for: [], privacy_contract: true, available: true },
    ],
  };  // prettier-ignore

  it("asks the case's own engines, shows each one's contract mark, and disables one with the reason in words", async () => {
    const calls = serve({
      "GET /questions": () => json(200, []),
      "GET /models/engines": () => json(200, BLOCKED),
      // The reasons beneath the choice are the Conduit's for this question (`will-read`).
      "POST /questions/will-read": () => json(200, { ...WILL, unusable: [{ name: "gemini", label: "Gemini", reason: REASON }] }),
    });
    mount();
    const choice = (await screen.findByRole("combobox", { name: "Model engine" })) as HTMLSelectElement;
    expect(calls.some((c) => c.url === "http://api/v1/investigations/b1/models/engines")).toBe(true);
    expect(Array.from(choice.options).map((o) => [o.value, o.textContent, o.disabled])).toEqual([
      ["local", "This deployment's own model", false],
      ["gemini", "Gemini (no contract) — not available", true],
      ["anthropic", "Claude (under contract)", false],
    ]);
    expect(screen.getByText(`Gemini: ${REASON}`)).toBeTruthy();
  });

  it("never chooses a disabled default: the local engine is chosen and sent instead", async () => {
    const calls = serve({
      "GET /questions": () => json(200, []),
      "GET /models/engines": () => json(200, BLOCKED),
      "POST /questions": () => json(200, { ...ANSWERED, engine: "local", model: "qwen2.5:7b-instruct" }),
    });
    mount();
    const choice = (await screen.findByRole("combobox", { name: "Model engine" })) as HTMLSelectElement;
    expect(choice.value).toBe("local");
    fireEvent.change(choice, { target: { value: "gemini" } }); // a disabled option is not taken
    expect(choice.value).toBe("local");
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Who?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Dana Mercer wrote about it [1].");
    const posted = calls.find((c) => c.init?.method === "POST" && c.url.endsWith("/questions"))!;
    expect(JSON.parse(String(posted.init!.body)).engine).toBe("local");
  });
});

// ADR-098 Amendment 7, ADR-135 Amendment 12: what the question reads from, what it will read and
// which engine will answer, all from the Conduit before anything is sent.
describe("QuestionsPanel · read from, will read, the engine", () => {
  const selection = { nodeIds: ["n-tarbuck", "n-cole"], linkIds: [] };
  const SELECTED: WillRead = {
    ...WILL,
    read: { read_from: "selection", documents: 0, documents_without_text: 1, items: 2, links: 3, events: 4, selected: 2, first_selected: "Tarbuck, Kyle", ...NOT_CASE },
  };  // prettier-ignore
  const willBodies = (calls: { url: string; init?: RequestInit }[]) =>
    calls.filter((c) => c.url.endsWith("/will-read")).map((c) => JSON.parse(String(c.init!.body)) as Record<string, unknown>);

  it("defaults to Selected items when something is selected, and says what it is about and will read, from the Conduit", async () => {
    const calls = serve({ "GET /questions": () => json(200, []), "POST /questions/will-read": () => json(200, SELECTED) });
    mount(vi.fn(), vi.fn(), { selection });
    expect((screen.getByRole("radio", { name: "Selected items" }) as HTMLInputElement).checked).toBe(true);
    expect(await screen.findByText("About: Tarbuck, Kyle and 1 other")).toBeTruthy();
    expect(screen.getByText("Will read: 0 documents, 2 items, 3 links and 4 events (1 document has no text to read)")).toBeTruthy();
    expect(screen.getByText("No documents will be read: the answer will come from the links and events.")).toBeTruthy();
    expect(willBodies(calls)[0]).toEqual({ selected_node_ids: ["n-tarbuck", "n-cole"], selected_link_ids: [], read_from: "selection" });
  });

  it("never counts in the Glass: the figures are the Conduit's, even when the canvas holds more selected", async () => {
    const one: WillRead = { ...SELECTED, read: { ...SELECTED.read, selected: 1 } };
    serve({ "GET /questions": () => json(200, []), "POST /questions/will-read": () => json(200, one) });
    mount(vi.fn(), vi.fn(), { selection });
    expect(await screen.findByText("About: Tarbuck, Kyle")).toBeTruthy();
    expect(screen.queryByText(/and 1 other/)).toBeNull();
  });

  it("with nothing selected reads everything on the graph, and Selected items is not offered", async () => {
    serve({ "GET /questions": () => json(200, []) });
    mount();
    expect((screen.getByRole("radio", { name: "Everything on the graph" }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("radio", { name: /Selected items/ }) as HTMLInputElement).disabled).toBe(true);
    expect(await screen.findByText("About: everything on the graph")).toBeTruthy();
    expect(screen.getByText("Will read: 2 documents, 5 items and 4 links")).toBeTruthy();
  });

  it("offers Whole case, described in one line as finding things by names and words", () => {
    serve({ "GET /questions": () => json(200, []) });
    mount();
    const whole = screen.getByRole("radio", { name: "Whole case" }) as HTMLInputElement;
    expect(whole.disabled).toBe(false);
    expect(document.getElementById(whole.getAttribute("aria-describedby")!)!.textContent).toBe(WHOLE_CASE_LINE);
  });

  it("choosing Everything on the graph asks the Conduit again and sends that choice with the question", async () => {
    const calls = serve({
      "GET /questions": () => json(200, []),
      "POST /questions": () => json(200, ANSWERED),
    });
    mount(vi.fn(), vi.fn(), { selection });
    fireEvent.click(screen.getByRole("radio", { name: "Everything on the graph" }));
    await waitFor(() => expect(willBodies(calls).some((b) => b.read_from === "graph")).toBe(true));
    expect(willBodies(calls).find((b) => b.read_from === "graph")!.selected_node_ids).toEqual([]);
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Who?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Dana Mercer wrote about it [1].");
    const posted = calls.find((c) => c.init?.method === "POST" && c.url.endsWith("/questions"))!;
    expect(JSON.parse(String(posted.init!.body))).toMatchObject({ read_from: "graph", selected_node_ids: [] });
  });

  it("names the engine that will answer even when there is only one", async () => {
    serve({ "GET /questions": () => json(200, []), "GET /models/engines": () => json(200, { engines: [
      { name: "local", label: "This deployment's own model", roles: ["extraction"], default_for: ["extraction"] }] }) });  // prettier-ignore
    mount();
    expect(await screen.findByText("Will be answered by This deployment's own model (qwen2.5:7b-instruct)")).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: "Model engine" })).toBeNull();
  });

  it("lists the engines that cannot answer this question with their reasons, even with no choice to make", async () => {
    serve({
      "GET /questions": () => json(200, []),
      "POST /questions/will-read": () =>
        json(200, { ...WILL, unusable: [{ name: "eyes", label: "Eyes", reason: "Eyes has no model for questions on this deployment." }] }),
    });
    mount();
    expect(await screen.findByText("Eyes: Eyes has no model for questions on this deployment.")).toBeTruthy();
  });

  it("says the routing's refusal when no engine may answer", async () => {
    const refused = "The extraction model is Gemini, and it may not be sent; this deployment has no local extraction model to use instead.";
    serve({
      "GET /questions": () => json(200, []),
      "POST /questions/will-read": () => json(200, { ...WILL, engine: null, engine_label: null, model: null, refused }),
    });
    mount();
    expect(await screen.findByText(refused)).toBeTruthy();
    expect(screen.queryByText(/Will be answered by/)).toBeNull();
  });

  it("says the engine list failed, never that there is none", async () => {
    serve({ "GET /questions": () => json(200, []), "GET /models/engines": () => json(500, {}) });
    mount();
    expect(await screen.findByText(/The list of model engines could not be loaded/)).toBeTruthy();
    expect(screen.queryByText(/no engines?/i)).toBeNull();
  });

  it("asks again when the timeline window has moved by the time the question box is focused, as the question reads it", async () => {
    let current: { validFrom: string; validTo: string | null } | null = { validFrom: "2026-01-01T00:00:00Z", validTo: null };
    const calls = serve({ "GET /questions": () => json(200, []), "POST /questions": () => json(200, ANSWERED) });
    mount(vi.fn(), vi.fn(), { getTimelineWindow: () => current });
    await screen.findByText("About: everything on the graph");
    expect(willBodies(calls)).toHaveLength(1);
    expect(willBodies(calls)[0]!.window).toEqual({ valid_from: "2026-01-01T00:00:00Z", valid_to: null });
    current = { validFrom: "2026-06-01T00:00:00Z", validTo: null };
    fireEvent.focus(screen.getByLabelText("Your question"));
    await waitFor(() => expect(willBodies(calls)).toHaveLength(2));
    expect(willBodies(calls)[1]!.window).toEqual({ valid_from: "2026-06-01T00:00:00Z", valid_to: null });
    fireEvent.focus(screen.getByLabelText("Your question")); // unchanged: not asked again
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Who?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Dana Mercer wrote about it [1].");
    expect(willBodies(calls).filter((b) => (b.window as { valid_from: string }).valid_from === "2026-06-01T00:00:00Z").length).toBeGreaterThanOrEqual(1);
    const posted = calls.find((c) => c.init?.method === "POST" && c.url.endsWith("/questions"))!;
    expect(JSON.parse(String(posted.init!.body)).window).toEqual({ valid_from: "2026-06-01T00:00:00Z", valid_to: null });
  });

  it("asks nothing when the canvas's selection changes under Everything on the graph, since nothing it sends changes", async () => {
    const calls = serve({ "GET /questions": () => json(200, []) });
    const props = { apiBaseUrl: "http://api", bearerToken: "t", investigationId: "b1", onDelta: vi.fn() };
    const { rerender } = render(<QuestionsPanel {...props} selection={selection} />);
    fireEvent.click(screen.getByRole("radio", { name: "Everything on the graph" }));
    await screen.findByText("About: everything on the graph");
    const before = willBodies(calls).length;
    rerender(<QuestionsPanel {...props} selection={{ nodeIds: ["n-other"], linkIds: [] }} />);
    rerender(<QuestionsPanel {...props} selection={{ nodeIds: ["n-other", "n-more"], linkIds: [] }} />);
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(willBodies(calls).length).toBe(before);
  });

  it("keeps the case's own reasons beneath the engine choice while will read is refused", async () => {
    serve({
      "GET /questions": () => json(200, []),
      "GET /models/engines": () => json(200, { engines: [
        { name: "local", label: "This deployment's own model", roles: ["extraction"], default_for: ["extraction"] },
        { name: "gemini", label: "Gemini", roles: ["extraction"], default_for: [], privacy_contract: false, available: false, reason: "Not available for this case: kept in." },
      ] }),
      "POST /questions/will-read": () => json(422, { error: "nothing_to_read", detail: "The graph holds nothing to read. Add items to the canvas first." }),
    });  // prettier-ignore
    mount();
    expect(await screen.findByText("The graph holds nothing to read. Add items to the canvas first.")).toBeTruthy();
    expect(screen.getByText("Gemini: Not available for this case: kept in.")).toBeTruthy();
  });

  it("says the engine list failed when the answer holds no list, never that there is none", async () => {
    serve({ "GET /questions": () => json(200, []), "GET /models/engines": () => json(200, {}) });
    mount();
    expect(await screen.findByText(/The list of model engines could not be loaded/)).toBeTruthy();
  });

  it("says under each answer what it read, and that an answer with no document came from the links and events", async () => {
    serve({ "GET /questions": () => json(200, [
      { ...ANSWERED, read: WILL.read },
      { ...ANSWERED, id: "q9", read: SELECTED.read },
    ]) });  // prettier-ignore
    mount();
    expect(await screen.findByText("Read: 2 documents, 5 items and 4 links.")).toBeTruthy();
    expect(
      screen.getByText(
        "No documents were read: the answer comes from the links and events (read: 0 documents, 2 items, 3 links and 4 events (1 document has no text to read)).",
      ),
    ).toBeTruthy();
  });
});

// ADR-098 Amendment 9, ADR-129 Amendment 5: *Whole case*, through the case's search.
describe("QuestionsPanel · Whole case", () => {
  const CASE_READ = {
    read_from: "case" as const, documents: 1, documents_without_text: 0, items: 2, links: 0, events: 0,
    selected: 0, first_selected: null, found: 4, passages: 1, limited_reason: null, counts_exact: true, more: false,
  };  // prettier-ignore
  const CASE_WILL: WillRead = { ...WILL, read: CASE_READ };
  const SOURCED: QuestionAnswer = {
    ...ANSWERED,
    id: "q-case",
    answer: "Ann Kestrel was paid [S-1].",
    candidates: [],
    unplaced: 0,
    read: CASE_READ,
    search_citations: [
      { number: 1, label: "[S-1]", name: "KESTREL, Ann", type: "Person", why: "Name is 'Kestrel'", node_ids: ["n-k1", "n-k2"] },
      { number: 2, label: "[S-2]", name: "Kestrel invoice", type: "Document", why: "Mentions 'Kestrel'", node_ids: ["d-k"] },
    ],
  };  // prettier-ignore
  const willBodies = (calls: { url: string; init?: RequestInit }[]) =>
    calls.filter((c) => c.url.endsWith("/will-read")).map((c) => JSON.parse(String(c.init!.body)) as Record<string, unknown>);

  it("sends the question's words with will read, and says what the search found by how each is read", async () => {
    const calls = serve({ "GET /questions": () => json(200, []), "POST /questions/will-read": () => json(200, CASE_WILL) });
    mount();
    fireEvent.click(screen.getByRole("radio", { name: "Whole case" }));
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Who paid Kestrel?" } });
    await waitFor(() => expect(willBodies(calls).some((b) => b.question === "Who paid Kestrel?")).toBe(true));
    expect(willBodies(calls).find((b) => b.question)!).toMatchObject({ read_from: "case", selected_node_ids: [] });
    expect(await screen.findByText("About: the whole case, searched with your question's words")).toBeTruthy();
    expect(
      screen.getByText("Will read: 4 matches found in the case: 1 document whole, 1 document by the passage found and 2 other records"),
    ).toBeTruthy();
  });

  it("asks again as the question changes, since its words are what is searched", async () => {
    const calls = serve({ "GET /questions": () => json(200, []), "POST /questions/will-read": () => json(200, CASE_WILL) });
    mount();
    fireEvent.click(screen.getByRole("radio", { name: "Whole case" }));
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Kestrel" } });
    await waitFor(() => expect(willBodies(calls).some((b) => b.question === "Kestrel")).toBe(true));
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Kestrel invoice" } });
    await waitFor(() => expect(willBodies(calls).some((b) => b.question === "Kestrel invoice")).toBe(true));
  });

  it("says the search's fallback, counts that may be incomplete and a second page never read", async () => {
    const limited: WillRead = {
      ...CASE_WILL,
      read: { ...CASE_READ, limited_reason: "Results are limited: the search index cannot be reached.", counts_exact: false, more: true },
    };  // prettier-ignore
    serve({ "GET /questions": () => json(200, []), "POST /questions/will-read": () => json(200, limited) });
    mount();
    fireEvent.click(screen.getByRole("radio", { name: "Whole case" }));
    expect(await screen.findByText("Results are limited: the search index cannot be reached.")).toBeTruthy();
    expect(screen.getByText("The search's counts may be incomplete.")).toBeTruthy();
    expect(screen.getByText("Only the first 4 matches are read; there are more.")).toBeTruthy();
  });

  it("says in the Conduit's words why a question too long to search was refused", async () => {
    const words =
      "Whole case searches the case with your question's own words, which can be at most 200 characters; yours has 240. Shorten the question, or choose Selected items or Everything on the graph to ask it as it is.";
    serve({
      "GET /questions": () => json(200, []),
      "POST /questions/will-read": () => json(422, { error: "question_too_long_to_search", detail: words }),
    });
    mount();
    fireEvent.click(screen.getByRole("radio", { name: "Whole case" }));
    expect(await screen.findByText(words)).toBeTruthy();
  });

  it("shows each [S-n] as a button that selects its records, and lists every source with why it was found", async () => {
    serve({ "GET /questions": () => json(200, [SOURCED]) });
    const onSelectFacts = vi.fn();
    mount(vi.fn(), vi.fn(), { onSelectFacts });
    fireEvent.click(await screen.findByRole("button", { name: "Select [S-1], KESTREL, Ann, on the canvas" }));
    expect(onSelectFacts).toHaveBeenCalledWith({ number: 1, label: "[S-1]", node_ids: ["n-k1", "n-k2"], link_ids: [] });
    const sources = screen.getByRole("list", { name: "Sources found in the case" });
    expect(sources.textContent).toContain("Person · Name is 'Kestrel'");
    // An unmarked source is still reachable: its button is in the list.
    fireEvent.click(screen.getByRole("button", { name: "Select [S-2], Kestrel invoice, on the canvas" }));
    expect(onSelectFacts).toHaveBeenLastCalledWith({ number: 2, label: "[S-2]", node_ids: ["d-k"], link_ids: [] });
  });

  it("says under an answer read from the whole case what it read, and that the search finds by names and words", async () => {
    serve({ "GET /questions": () => json(200, [SOURCED]) });
    mount();
    expect(
      await screen.findByText(
        `Read from the whole case: 4 matches found in the case: 1 document whole, 1 document by the passage found and 2 other records. ${WHOLE_CASE_LINE}`,
      ),
    ).toBeTruthy();
  });
});
