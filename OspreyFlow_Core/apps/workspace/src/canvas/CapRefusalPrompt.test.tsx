// @vitest-environment jsdom
//
// The canvas's refusal of an expansion the working set's cap refused (rule 2; spec/00 §4's choices). What would fail
// if each part were wrong: a figure other than the Conduit's own; a choice of type handing over its label, not its
// type; the batch slot (ADR-151, case-b's) drawn without its handler, under another name, or not calling it.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { LimitExceeded } from "../workingset/models";
import { CapRefusalPrompt } from "./CapRefusalPrompt";

afterEach(cleanup);

const REFUSED: LimitExceeded = { error: "limit_exceeded", cap_kind: "nodes", cap: 50_000, would_be: 50_812, options: ["save_as_view", "filter", "promote_to_batch"] };
const TYPES = [{ name: "ASSOCIATE_OF", label: "Associate of" }, { name: "PRESENT_AT", label: "Present at" }];

function draw(over: Partial<Parameters<typeof CapRefusalPrompt>[0]> = {}) {
  const props = {
    x: 10,
    y: 10,
    refused: REFUSED,
    options: [{ edgeType: "PRESENT_AT", wouldAdd: 12 }, { edgeType: "ASSOCIATE_OF", wouldAdd: 1_204 }],
    subject: "Ann Bell",
    edgeTypes: TYPES,
    onChooseType: vi.fn(),
    onSaveSmallerView: vi.fn(),
    onCancel: vi.fn(),
    ...over,
  };
  render(<CapRefusalPrompt {...props} />);
  return props;
}

test("says the cap's own figure and that nothing has been added", () => {
  draw();
  const refusal = screen.getByRole("alertdialog", { name: "Too large to expand" });
  expect(refusal.textContent).toContain("Too many for the canvas: 50,812 nodes against a limit of 50,000.");
  expect(refusal.textContent).toContain("Nothing has been added.");
  expect(refusal.textContent).toContain("Expanding Ann Bell was refused.");
});

test("each relationship is named by its label with what it would add, and hands over its type", () => {
  const props = draw();
  fireEvent.click(screen.getByRole("button", { name: "Associate of (1,204)" }));
  expect(props.onChooseType).toHaveBeenCalledWith("ASSOCIATE_OF");
});

test("with no relationship to offer (a typed expansion refused), no narrowing is offered, the save still is", () => {
  draw({ options: [] });
  expect(screen.queryByText("Expand by one relationship instead:")).toBeNull();
  expect(screen.getByRole("button", { name: "Save a smaller view…" })).toBeTruthy();
});

test("the batch choice (ADR-151) is drawn only with its handler, named exactly Run as a batch job, and calls it", () => {
  draw();
  expect(screen.queryByRole("button", { name: "Run as a batch job" })).toBeNull();
  cleanup();
  const onRunAsBatch = vi.fn();
  draw({ onRunAsBatch });
  fireEvent.click(screen.getByRole("button", { name: "Run as a batch job" }));
  expect(onRunAsBatch).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/Or run the whole expansion on the server as a batch job/)).toBeTruthy();
});
