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

function mount(onDelta = vi.fn(), onOpenDocument = vi.fn()) {
  render(
    <QuestionsPanel apiBaseUrl="http://api" bearerToken="t" investigationId="b1" onDelta={onDelta} onOpenDocument={onOpenDocument} />,
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
    expect(screen.getByText(/1 proposal was left out/)).toBeTruthy();
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
    expect(JSON.parse(String(posted.init!.body))).toEqual({ question: "Who wrote about the plant?" });
  });

  it("says in words why documents too long to read at once were refused, and keeps the question", async () => {
    serve({
      "GET /questions": () => json(200, []),
      "POST /questions": () => json(413, { error: "documents_too_large", would_be: 120000, limit: 80000 }),
    });
    mount();
    await screen.findByText("No questions asked in this case yet.");
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Anything?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "These documents come to 120,000 characters, more than the model can read at once (80,000). " +
        "Remove some from the view and ask again.",
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
