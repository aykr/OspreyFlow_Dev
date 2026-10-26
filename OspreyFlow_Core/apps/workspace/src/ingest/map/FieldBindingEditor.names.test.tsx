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

function mount(binding: FieldBinding, allowOptional = false) {
  const onChange = vi.fn();
  render(
    <FieldBindingEditor
      allowOptional={allowOptional}
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

// --- ADR-127 Amendment 15: a property's binding may be optional --------------------------------

describe("FieldBindingEditor: optional", () => {
  const label = "Optional: leave the property out when its cell is empty";

  it("offers the choice only where a property is bound", () => {
    mount({ field: "started" });
    expect(screen.queryByLabelText(label)).toBeNull();
    cleanup();
    mount({ field: "started" }, true);
    expect((screen.getByLabelText(label) as HTMLInputElement).checked).toBe(false);
  });

  it("marks the binding optional, and takes the mark off by removing it, not by writing false", () => {
    const onChange = mount({ field: "aliases", transform: "split" }, true);
    fireEvent.click(screen.getByLabelText(label));
    expect(onChange).toHaveBeenLastCalledWith({ field: "aliases", transform: "split", optional: true });
    cleanup();
    const again = mount({ field: "aliases", transform: "split", optional: true }, true);
    expect((screen.getByLabelText(label) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByLabelText(label));
    expect(again).toHaveBeenLastCalledWith({ field: "aliases", transform: "split" });
  });

  it("keeps the mark when the transform or the column is changed", () => {
    const onChange = mount({ field: "started", optional: true }, true);
    fireEvent.change(screen.getByLabelText("Transform"), { target: { value: "msisdn" } });
    expect(onChange).toHaveBeenLastCalledWith({ field: "started", transform: "msisdn", optional: true });
    fireEvent.change(screen.getByLabelText("Source column"), { target: { value: "ended" } });
    expect(onChange).toHaveBeenLastCalledWith({ field: "ended", optional: true });
  });
});
