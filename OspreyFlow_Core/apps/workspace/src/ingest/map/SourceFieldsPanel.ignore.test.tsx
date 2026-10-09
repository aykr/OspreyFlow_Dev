// @vitest-environment jsdom
//
// 9 October 2026, the data engineer's journey: a note typed beside an unmapped field ("Carrier's
// row counter, not evidence") was not in the published recipe. The Ignore button ignored the field
// with no note; only Enter in the note box kept it. Spec 09 §4: an unmapped field is marked ignored
// with a note, and the recipe carries the note (§6's example).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { SourceFieldsPanel } from "./SourceFieldsPanel";

afterEach(cleanup);

function mount(onIgnoreField: (field: string, note: string | null) => void) {
  render(
    <SourceFieldsPanel
      columns={[]}
      sampleRow={null}
      boundFieldNames={new Set()}
      unmappedFieldNames={["seq"]}
      ignoredNotes={new Map()}
      onRowChange={() => undefined}
      onIgnoreField={onIgnoreField}
      onUnignoreField={() => undefined}
    />,
  );
}

it("keeps the note typed beside the field when Ignore is pressed", () => {
  const onIgnore = vi.fn();
  mount(onIgnore);
  fireEvent.change(screen.getByPlaceholderText("note (optional)"), {
    target: { value: "Carrier's row counter, not evidence" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ignore" }));
  expect(onIgnore).toHaveBeenCalledWith("seq", "Carrier's row counter, not evidence");
});

it("ignores with no note when none was typed", () => {
  const onIgnore = vi.fn();
  mount(onIgnore);
  fireEvent.click(screen.getByRole("button", { name: "Ignore" }));
  expect(onIgnore).toHaveBeenCalledWith("seq", null);
});
