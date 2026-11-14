// @vitest-environment jsdom
//
// A popover takes focus once, when it opens. Seen 20 October 2026 (the owner): after a document was
// opened, the canvas's Layout menu closed itself the moment it was pressed. A notice built on
// `Popover` was still on the canvas, and `Popover` refocused its first button whenever its
// `onClose` changed; its parent passes a new one on every render, and pressing the menu re-renders
// the canvas. `Drawer` had the same fault, fixed 9 October (`Drawer.test.tsx`).
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
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

// The canvas's two expansion prompts (`LargeExpansionPrompt`, `CapRefusalPrompt`): a choice the canvas waits on,
// so the popover is the named alertdialog itself, modal, and Tab and Shift+Tab stay inside it. Without these
// props a popover is as it was (an unnamed dialog, Tab free), which the other overlays rely on.
it("as a modal prompt it is the named alertdialog, aria-modal, and Tab and Shift+Tab stay inside it", () => {
  render(
    <Popover x={0} y={0} onClose={() => undefined} role="alertdialog" label="Too large to expand" modal>
      <button type="button">First</button>
      <button type="button">Last</button>
    </Popover>,
  );
  const prompt = screen.getByRole("alertdialog", { name: "Too large to expand" });
  expect(prompt.getAttribute("aria-modal")).toBe("true");
  expect(screen.queryByRole("dialog")).toBeNull();
  const [first, last] = screen.getAllByRole("button");
  last!.focus();
  fireEvent.keyDown(last!, { key: "Tab" });
  expect(document.activeElement).toBe(first);
  fireEvent.keyDown(first!, { key: "Tab", shiftKey: true });
  expect(document.activeElement).toBe(last);
});

it("without them it is an unnamed dialog, and Tab is left to the page", () => {
  render(
    <Popover x={0} y={0} onClose={() => undefined}>
      <button type="button">Only</button>
    </Popover>,
  );
  const popover = screen.getByRole("dialog");
  expect(popover.getAttribute("aria-modal")).toBeNull();
  const only = screen.getByRole("button");
  only.focus();
  const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
  only.dispatchEvent(tab);
  expect(tab.defaultPrevented).toBe(false);
});
