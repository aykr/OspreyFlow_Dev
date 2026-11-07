// @vitest-environment jsdom
// Spec 09 §4's keyboard bind (ADR-140 Amendment 8): with a column chosen in the Source fields pane,
// a binding offers "Bind <column> here", which binds it exactly as a drop would and lets it go.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FieldBinding } from "../../../../../packages/schemas/generated";
import { ChosenColumnContext } from "./chosenColumn";
import { FieldBindingEditor } from "./FieldBindingEditor";

afterEach(cleanup);

function mount(binding: FieldBinding, column: string | null) {
  const onChange = vi.fn();
  const clear = vi.fn();
  render(
    <ChosenColumnContext.Provider value={{ column, clear }}>
      <FieldBindingEditor binding={binding} sourceFieldNames={["caller", "called"]} transforms={[]} onChange={onChange} target="name" />
    </ChosenColumnContext.Provider>,
  );
  return { onChange, clear };
}

describe("the keyboard bind", () => {
  it("binds the chosen column to this binding and lets the column go", () => {
    const { onChange, clear } = mount({ field: "caller" }, "called");
    fireEvent.click(screen.getByRole("button", { name: "Bind called here: name" }));
    expect(onChange).toHaveBeenCalledWith({ field: "called", fields: undefined });
    expect(clear).toHaveBeenCalled();
  });

  it("offers nothing with no column chosen, or on a literal", () => {
    mount({ field: "caller" }, null);
    expect(screen.queryByRole("button", { name: /^Bind / })).toBeNull();
    cleanup();
    mount({ literal: "x" }, "called");
    expect(screen.queryByRole("button", { name: /^Bind / })).toBeNull();
  });
});
