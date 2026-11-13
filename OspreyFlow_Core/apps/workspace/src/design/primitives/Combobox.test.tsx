// @vitest-environment jsdom
// The Combobox's Enter (ADR-145 Amendment 15 Part A): with `onSubmit`, Enter on typed words submits them unless the
// person has moved to an option with the arrow keys; without it, Enter chooses the first option, as before. What
// would fail if it were wrong: the top bar's Enter choosing the first suggestion instead of opening the results page.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { Combobox } from "./Combobox";

afterEach(cleanup);

const OPTIONS = [
  { value: "p1", label: "Person: Kestrel" },
  { value: "p2", label: "Person: Kestrel Ann" },
];

function draw(onSubmit?: (q: string) => void) {
  const onChange = vi.fn();
  render(<Combobox aria-label="Search" options={OPTIONS} value="" onChange={onChange} onQueryChange={() => undefined} onSubmit={onSubmit} />);
  const box = screen.getByRole("combobox", { name: "Search" });
  fireEvent.change(box, { target: { value: "Kestrel" } });
  return { box, onChange };
}

test("with onSubmit, Enter on the typed words submits them while the options show, choosing none", () => {
  const onSubmit = vi.fn();
  const { box, onChange } = draw(onSubmit);
  expect(screen.getAllByRole("option")).toHaveLength(2);
  expect(box.getAttribute("aria-activedescendant")).toBeNull();
  fireEvent.keyDown(box, { key: "Enter" });
  expect(onSubmit).toHaveBeenCalledWith("Kestrel");
  expect(onChange).not.toHaveBeenCalled();
});

test("with onSubmit, an option moved to with the arrow keys is chosen by Enter", () => {
  const onSubmit = vi.fn();
  const { box, onChange } = draw(onSubmit);
  fireEvent.keyDown(box, { key: "ArrowDown" });
  fireEvent.keyDown(box, { key: "Enter" });
  expect(onChange).toHaveBeenCalledWith("p1");
  expect(onSubmit).not.toHaveBeenCalled();
});

test("without onSubmit, Enter chooses the first option, as before", () => {
  const { box, onChange } = draw();
  fireEvent.keyDown(box, { key: "Enter" });
  expect(onChange).toHaveBeenCalledWith("p1");
});
