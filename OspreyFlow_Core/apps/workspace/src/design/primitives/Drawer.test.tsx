// @vitest-environment jsdom
//
// A drawer takes focus once, when it opens (spec 02 §6). Seen 9 October 2026 in *Record an
// assessment*: after two characters the statement lost focus to the drawer, and the rest of what
// was typed went nowhere. The drawer refocused itself whenever its `onClose` changed, and its
// parent passes a new one on every render, which each keystroke causes.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it } from "vitest";

import { Drawer } from "./Drawer";

afterEach(cleanup);

function Form() {
  const [text, setText] = useState("");
  return (
    <Drawer open onClose={() => undefined} title="Record an assessment">
      <input aria-label="Statement" value={text} onChange={(e) => setText(e.target.value)} />
    </Drawer>
  );
}

it("keeps focus in a field while its parent re-renders on each keystroke", () => {
  render(<Form />);
  const field = screen.getByLabelText("Statement") as HTMLInputElement;
  act(() => field.focus());
  for (const typed of ["O", "OK", "OKA", "OKAF"]) {
    fireEvent.change(field, { target: { value: typed } });
    expect(document.activeElement).toBe(field);
  }
  expect(field.value).toBe("OKAF");
});

it("still takes focus when it opens", () => {
  render(<Form />);
  expect(document.activeElement?.getAttribute("role")).toBe("dialog");
});

// The owner, 9 October 2026, on the Questions drawer: "how do I close the questions panel?" —
// Escape worked but nothing visible said so.
it("offers a visible Close button that closes it", () => {
  let closed = 0;
  render(
    <Drawer open onClose={() => closed++} title="Questions">
      <p>body</p>
    </Drawer>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Close Questions" }));
  expect(closed).toBe(1);
});
