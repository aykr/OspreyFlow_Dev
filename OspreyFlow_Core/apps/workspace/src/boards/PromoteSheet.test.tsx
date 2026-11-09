// @vitest-environment jsdom
// ADR-143 decision 8 (L3.4): the *Promote…* sheet. What would fail if each part were wrong: an item
// failing a check tickable, or its reason not said; a promotion sent with what was not ticked; what
// was left out not listed afterwards (rule 2); a board that promotes into nothing offering Promote;
// Escape not closing the sheet; the policy's words wrong (Promote against Send for review).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PromoteSheet } from "./PromoteSheet";
import type { PromotionSheet } from "./promotionsApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SHEET = (over: Partial<PromotionSheet> = {}): PromotionSheet => ({
  board_id: "b1", dataset_id: "src", dataset_name: "Prison intel", highest_marking: "OFFICIAL-SENSITIVE",
  policy: "author_promotes", checks: [{ name: "marking", passed: false, words: "Every marking within Prison intel's highest allowed: 1 above it" }],
  warnings: ["Tall looks like a loaded item and has no decision yet: decide Same or Not the same on the board first, or promote it as a separate item."],
  recorded_as: "One load into Prison intel.",
  items: [
    { item_id: "i1", element_id: "n1", kind: "node", type: "Person", label: "Tall", marking: "OFFICIAL", problems: [] },
    { item_id: "i2", element_id: "n2", kind: "node", type: "Person", label: "Secret one", marking: "SECRET",
      problems: ["Marked SECRET, above Prison intel's highest allowed marking, OFFICIAL-SENSITIVE."] },
    { item_id: "i3", element_id: "e1", kind: "link", type: "ASSOCIATE_OF", label: "seen together", marking: "OFFICIAL",
      follows: true, source: "n1", target: "n2", problems: [] },
  ],
  ...over,
});  // prettier-ignore

function serve(sheet: PromotionSheet) {
  const sent: unknown[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      sent.push(JSON.parse(String(init.body)));
      return new Response(
        JSON.stringify({
          id: "p1", load_id: "promotion-1", trigger: "analyst_promotion", dataset_id: "src", dataset_name: "Prison intel",
          case_id: "k", case_name: "k", proposed_by: "alice", proposed_by_name: "alice", proposed_at: "2026-11-09T09:00:00Z",
          status: sheet.policy === "author_promotes" ? "committed" : "awaiting_review", nodes: 1, links: 0,
          left_out: [{ item_id: "i3", label: "seen together", why: "One of its ends will not be in the dataset: it stays behind." }],
        }),
        { status: 201 },
      );  // prettier-ignore
    }
    return new Response(JSON.stringify(sheet), { status: 200 });
  });
  return sent;
}

function open(onClose = () => undefined) {
  render(<PromoteSheet apiBaseUrl="http://api" bearerToken="t" caseId="k" boardId="b1" govuk={false} onClose={onClose} onPromoted={() => undefined} />);
}

describe("PromoteSheet", () => {
  it("ticks what may go, says why the rest cannot, and lists what was left out", async () => {
    const sent = serve(SHEET());
    open();
    const blocked = (await screen.findByLabelText(/Item: Secret one/)) as HTMLInputElement;
    expect(blocked.disabled).toBe(true);
    expect(screen.getByText(/Cannot go: Marked SECRET/)).toBeTruthy();
    expect((screen.getByLabelText(/Item: Tall/) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText(/looks like a loaded item/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/Link: seen together/));
    fireEvent.click(screen.getByRole("button", { name: "Promote" }));
    await waitFor(() => expect(sent).toEqual([{ item_ids: ["i1"] }]));
    expect(await screen.findByText("Left out, and why")).toBeTruthy();
    expect(screen.getByText(/it stays behind/)).toBeTruthy();
  });

  it("says Send for review under a second person's policy", async () => {
    serve(SHEET({ policy: "second_person_reviews" }));
    open();
    expect(await screen.findByRole("button", { name: "Send for review" })).toBeTruthy();
  });

  it("offers no promotion from a board that promotes into nothing, and says why", async () => {
    serve(SHEET({ items: [], refused: "This drawing is its own dataset: what is drawn here is already its data." }));
    open();
    expect(await screen.findByText(/This drawing is its own dataset/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Promote" })).toBeNull();
  });

  it("closes on Escape", async () => {
    serve(SHEET());
    const onClose = vi.fn();
    open(onClose);
    const dialog = await screen.findByRole("dialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
