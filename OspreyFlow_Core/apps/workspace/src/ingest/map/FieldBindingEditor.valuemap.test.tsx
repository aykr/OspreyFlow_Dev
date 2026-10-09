// @vitest-environment jsdom
//
// The value map's rows are editing state, not the canonical Record — a Record
// cannot hold two rows with the same key, so holding rows in it made a second
// `+ mapping` click a no-op while an empty row existed, and a source value
// typed to match another row's silently swallowed a row (found 9 October 2026,
// "Map's + mapping adds a row only when the last is filled").
import { useState } from "react";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import type { FieldBinding } from "../../../../../packages/schemas/generated";
import { FieldBindingEditor } from "./FieldBindingEditor";

afterEach(cleanup);

/** The editor as MapScreen mounts it: the binding lives in the parent's state. */
function Harness({ initial }: { initial: FieldBinding }) {
  const [binding, setBinding] = useState<FieldBinding>(initial);
  return (
    <FieldBindingEditor
      binding={binding}
      sourceFieldNames={["status"]}
      transforms={[]}
      onChange={setBinding}
    />
  );
}

it("+ mapping adds a new empty row even while the last row is still empty", () => {
  render(<Harness initial={{ field: "status", map: {} }} />);
  const add = screen.getByRole("button", { name: "+ mapping" });
  fireEvent.click(add);
  fireEvent.click(add);
  expect(screen.getAllByPlaceholderText("source value")).toHaveLength(2);
});

it("a source value typed to match another row's does not swallow a row", () => {
  render(<Harness initial={{ field: "status", map: { A: "Active", B: "Blocked" } }} />);
  const rows = screen.getAllByPlaceholderText("source value");
  expect(rows).toHaveLength(2);
  fireEvent.change(rows[1] as HTMLElement, { target: { value: "A" } });
  expect(screen.getAllByPlaceholderText("source value")).toHaveLength(2);
});

it("filled rows still publish to the binding's map", () => {
  render(<Harness initial={{ field: "status", map: {} }} />);
  fireEvent.click(screen.getByRole("button", { name: "+ mapping" }));
  fireEvent.change(screen.getByPlaceholderText("source value"), { target: { value: "A" } });
  fireEvent.change(screen.getByPlaceholderText("mapped value"), { target: { value: "Active" } });
  expect((screen.getByPlaceholderText("source value") as HTMLInputElement).value).toBe("A");
  expect((screen.getByPlaceholderText("mapped value") as HTMLInputElement).value).toBe("Active");
});

it("removing a row removes that row alone", () => {
  render(<Harness initial={{ field: "status", map: { A: "Active", B: "Blocked" } }} />);
  const removes = screen.getAllByRole("button", { name: "Remove mapping" });
  fireEvent.click(removes[0] as HTMLElement);
  const rows = screen.getAllByPlaceholderText("source value") as HTMLInputElement[];
  expect(rows.map((r) => r.value)).toEqual(["B"]);
});
