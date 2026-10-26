// @vitest-environment jsdom
//
// Rule 13: the binding editor's kind select and literal input had no name, so a keyboard test could
// not choose a literal binding on purpose. Each control is findable by the name a person would give
// it, and each does what its name says.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FieldBinding } from "../../../../../packages/schemas/generated";
import { FieldBindingEditor } from "./FieldBindingEditor";

afterEach(cleanup);

function mount(binding: FieldBinding) {
  const onChange = vi.fn();
  render(
    <FieldBindingEditor
      binding={binding}
      sourceFieldNames={["started", "ended"]}
      transforms={[
        { name: "msisdn", arity: 1 },
        { name: "datetime", arity: 1 },
      ]}
      onChange={onChange}
    />,
  );
  return onChange;
}

describe("FieldBindingEditor: its controls are named", () => {
  it("names the kind, and choosing 'Literal' makes an empty literal binding", () => {
    const onChange = mount({ field: "started" });
    expect((screen.getByLabelText("Binding kind") as HTMLSelectElement).value).toBe("field");
    fireEvent.change(screen.getByLabelText("Binding kind"), { target: { value: "literal" } });
    expect(onChange).toHaveBeenLastCalledWith({ literal: "" });
  });

  it("names the literal's input, which sets the literal", () => {
    const onChange = mount({ literal: "" });
    fireEvent.change(screen.getByLabelText("Literal value"), { target: { value: "phone" } });
    expect(onChange).toHaveBeenLastCalledWith({ literal: "phone" });
  });

  it("names the source column and the transform of a field binding", () => {
    const onChange = mount({ field: "started" });
    expect((screen.getByLabelText("Source column") as HTMLSelectElement).value).toBe("started");
    fireEvent.change(screen.getByLabelText("Transform"), { target: { value: "msisdn" } });
    expect(onChange).toHaveBeenLastCalledWith({ field: "started", transform: "msisdn" });
  });
});
