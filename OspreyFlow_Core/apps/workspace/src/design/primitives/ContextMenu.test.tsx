// @vitest-environment jsdom
//
// A context menu takes focus once, to its first item, when it opens; a parent re-rendering with a
// new `onClose` does not take it back (the fault `Popover` had, 20 October 2026).
import { act, cleanup, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it } from "vitest";

import { pressEscapeOnAppear } from "../../testing/actOnAppear";
import { ContextMenu } from "./ContextMenu";

afterEach(cleanup);

function Page() {
  const [, redraw] = useState(0);
  return (
    <>
      <input aria-label="Elsewhere" onFocus={() => redraw((n) => n + 1)} />
      <ContextMenu x={0} y={0} items={[{ id: "expand", label: "Expand", onSelect: () => undefined }]} onClose={() => undefined} />
    </>
  );
}

it("focuses its first item when it opens, and leaves focus alone when its parent re-renders", () => {
  render(<Page />);
  expect(document.activeElement?.textContent).toContain("Expand");
  const elsewhere = screen.getByLabelText("Elsewhere");
  act(() => elsewhere.focus());
  expect(document.activeElement).toBe(elsewhere);
});

// Escape is heard from the moment it can be seen: a listener added in a passive effect missed an
// Escape pressed as it appeared on a slow machine (`Popover`, CI keyboard walkthroughs, 20 October 2026).
it("closes on an Escape pressed as soon as it is in the page", async () => {
  let closed = 0;
  await pressEscapeOnAppear(
    <ContextMenu x={0} y={0} items={[{ id: "expand", label: "Expand", onSelect: () => undefined }]} onClose={() => (closed += 1)} />,
    "[role='menu']",
  );
  expect(closed).toBe(1);
});
