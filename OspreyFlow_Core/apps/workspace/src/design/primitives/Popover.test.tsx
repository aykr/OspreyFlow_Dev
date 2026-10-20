// @vitest-environment jsdom
//
// A popover takes focus once, when it opens. Seen 20 October 2026 (the owner): after a document was
// opened, the canvas's Layout menu closed itself the moment it was pressed. A notice built on
// `Popover` was still on the canvas, and `Popover` refocused its first button whenever its
// `onClose` changed; its parent passes a new one on every render, and pressing the menu re-renders
// the canvas. `Drawer` had the same fault, fixed 9 October (`Drawer.test.tsx`).
import { act, cleanup, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it } from "vitest";

import { pressEscapeOnAppear } from "../../testing/actOnAppear";
import { Popover } from "./Popover";

afterEach(cleanup);

function CanvasWithNotice() {
  const [, redraw] = useState(0);
  return (
    <>
      <select aria-label="Layout" onFocus={() => redraw((n) => n + 1)}>
        <option>Organic</option>
      </select>
      <button type="button" onClick={() => redraw((n) => n + 1)}>
        Redraw
      </button>
      <Popover x={10} y={10} onClose={() => undefined}>
        <button type="button" aria-label="Close">
          ×
        </button>
      </Popover>
    </>
  );
}

it("leaves focus where it is when its parent re-renders, as a control elsewhere takes it", () => {
  render(<CanvasWithNotice />);
  const layout = screen.getByLabelText("Layout");
  act(() => layout.focus());
  expect(document.activeElement).toBe(layout);
  act(() => screen.getByText("Redraw").click());
  act(() => layout.focus());
  expect(document.activeElement).toBe(layout);
});

it("still takes focus once, to its first button, when it opens", () => {
  render(<CanvasWithNotice />);
  expect(document.activeElement).toBe(screen.getByLabelText("Close"));
});

// Escape is heard from the moment the popover can be seen. Seen 20 October 2026 on CI: walkthroughs
// that wait for an overlay and press Escape failed now and then, a different one each run, the
// overlay still open. The listener was added in a passive effect, which React runs after the page
// is painted, so on a slow machine an Escape pressed as the overlay appeared was lost.
it("closes on an Escape pressed as soon as it is in the page", async () => {
  let closed = 0;
  await pressEscapeOnAppear(
    <Popover x={10} y={10} onClose={() => (closed += 1)}>
      <button type="button">×</button>
    </Popover>,
    "[role='dialog']",
  );
  expect(closed).toBe(1);
});
