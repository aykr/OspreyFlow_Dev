// @vitest-environment jsdom
// v0.6.0 #5: what an answer's items can be put to, under the answer. That the items reach the real canvas, selected,
// is `keyboard/questions.spec.ts`'s; the read by id and its access step, `test_add_by_ids.py`'s.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnswerActions, answerIds, answerViewName } from "./AnswerActions";
import type { QuestionAnswer } from "./questionsApi";

afterEach(() => cleanup());

const entry = (over: Partial<QuestionAnswer> = {}): QuestionAnswer =>
  ({
    id: "q1", author: "a", question: "Who knows n2?", answer: "", citations: [], candidates: [], unplaced: 0,
    created_at: "2026-11-15T10:00:00Z",
    graph_citations: [
      { number: 1, label: "[G-1]", node_ids: ["n2", "n3"], link_ids: ["e2"] },
      { number: 2, label: "[G-2]", node_ids: ["n3", "n9"], link_ids: [] },
    ],
    search_citations: [{ number: 1, label: "[S-1]", name: "N4", type: "Person", why: "", node_ids: ["n4", "n2"] }],
    ...over,
  }) as QuestionAnswer; // prettier-ignore

describe("an answer's items", () => {
  it("are every id its markers stand for, each once, facts first then sources", () => {
    expect(answerIds(entry())).toEqual({ nodeIds: ["n2", "n3", "n9", "n4"], linkIds: ["e2"] });
  });

  it("name the saved view after the question, cut at a word when long", () => {
    expect(answerViewName("Who knows n2?")).toBe("Answer: Who knows n2?");
    const long = answerViewName("Which of the accounts paid ".repeat(5));
    expect(long.length).toBeLessThanOrEqual("Answer: ".length + 73);
    expect(long.endsWith("…")).toBe(true);
    expect(answerViewName("   ")).toBe("Answer from Ask & Chat");
  });
});

describe("the actions under an answer", () => {
  it("offer nothing for an answer whose markers stand for nothing", () => {
    render(<AnswerActions entry={entry({ graph_citations: [], search_citations: [] })} onShowAll={() => {}} onSaveAsView={async () => null} />);
    expect(screen.queryByRole("group", { name: "This answer's items" })).toBeNull();
  });

  it("Show all on graph hands over every item", () => {
    const shown = vi.fn();
    render(<AnswerActions entry={entry()} onShowAll={shown} />);
    fireEvent.click(screen.getByRole("button", { name: "Show all on graph" }));
    expect(shown).toHaveBeenCalledWith({ nodeIds: ["n2", "n3", "n9", "n4"], linkIds: ["e2"] });
    expect(screen.queryByRole("button", { name: "Save as a view" })).toBeNull();
  });

  it("Save as a view saves the nodes under the name given, and stays open with the refusal when refused", async () => {
    const save = vi.fn(async () => "The view is full.");
    render(<AnswerActions entry={entry()} onSaveAsView={save} />);
    const button = screen.getByRole("button", { name: "Save as a view" });
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    const name = screen.getByLabelText("View name") as HTMLInputElement;
    expect(name.value).toBe("Answer: Who knows n2?");
    fireEvent.submit(name.closest("form")!);
    await vi.waitFor(() => expect(save).toHaveBeenCalledWith({ nodeIds: ["n2", "n3", "n9", "n4"], linkIds: ["e2"] }, "Answer: Who knows n2?"));
    await screen.findByText("The view is full.");
    expect(screen.getByLabelText("View name")).toBeTruthy();
  });

  it("offers no Save as a view for an answer that stands for links alone", () => {
    render(
      <AnswerActions
        entry={entry({ graph_citations: [{ number: 1, label: "[G-1]", node_ids: [], link_ids: ["e1"] }], search_citations: [] })}
        onShowAll={() => {}}
        onSaveAsView={async () => null}
      />,
    );
    expect(screen.getByRole("button", { name: "Show all on graph" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save as a view" })).toBeNull();
  });
});
