// @vitest-environment jsdom
// ADR-098 decision 4: the case's questions to the model. The panel shows what the Conduit returns
// and nothing more; a refusal is said in words; an accepted proposal's change reaches the view.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QuestionsPanel } from "./QuestionsPanel";
import type { QuestionAnswer } from "./questionsApi";

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

function serve(routes: Record<string, (init?: RequestInit) => Response>) {
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
    const posted = calls.find((c) => c.init?.method === "POST")!;
    expect(JSON.parse(String(posted.init!.body))).toEqual({
      question: "Who wrote about the plant?",
      selected_node_ids: [],
      selected_link_ids: [],
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
    const posted = calls.find((c) => c.init?.method === "POST")!;
    expect(JSON.parse(String(posted.init!.body))).toEqual({
      question: "Who?",
      selected_node_ids: ["n-dana"],
      selected_link_ids: ["l-called"],
      window: { valid_from: "2026-01-01T00:00:00Z", valid_to: null },
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
          options: ["narrow_selection", "narrow_timeline_window", "branch"],
        }),
    });
    mount();
    await screen.findByText("No questions asked in this case yet.");
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Anything?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "This question comes to 120,000 characters, more than the model can read at once (80,000): " +
        "the documents are 70,000 and the graph facts 50,000. Nothing was sent. " +
        "Narrow the selection, narrow the timeline window, or branch the case, then ask again.",
    );
    expect((screen.getByLabelText("Your question") as HTMLTextAreaElement).value).toBe("Anything?");
  });

  it("says when the case holds no document the analyst can see", async () => {
    serve({
      "GET /questions": () => json(200, []),
      "POST /questions": () => json(422, { error: "no_documents" }),
    });
    mount();
    await screen.findByText("No questions asked in this case yet.");
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Anything?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/no document you can see/);
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
});
