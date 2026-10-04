// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { Sash } from "./Sash";

// ADR-086. A sash is the draggable edge between two regions, as in VS Code: a separator the
// keyboard can reach, moved by the arrow keys, reset by Home or a double-click.

afterEach(cleanup);

// jsdom has no PointerEvent, so the testing library would fire a bare Event with no coordinates;
// a MouseEvent carries `clientX`/`clientY`, which is all the sash reads from it.
beforeAll(() => {
  if (typeof window.PointerEvent === "undefined") {
    (window as unknown as { PointerEvent: typeof MouseEvent }).PointerEvent = MouseEvent;
  }
});

function mount(over: Partial<Parameters<typeof Sash>[0]> = {}) {
  const onChange = vi.fn();
  const onReset = vi.fn();
  const utils = render(
    <Sash
      label="Resize the side panel"
      orientation="vertical"
      value={320}
      min={240}
      max={800}
      direction={-1}
      onChange={onChange}
      onReset={onReset}
      {...over}
    />,
  );
  const sash = utils.getByRole("separator", { name: "Resize the side panel" });
  return { ...utils, sash, onChange, onReset };
}

describe("Sash", () => {
  it("is a focusable separator that says its orientation and its value", () => {
    const { sash } = mount();
    expect(sash.getAttribute("tabindex")).toBe("0");
    expect(sash.getAttribute("aria-orientation")).toBe("vertical");
    expect(sash.getAttribute("aria-valuenow")).toBe("320");
    expect(sash.getAttribute("aria-valuemin")).toBe("240");
    expect(sash.getAttribute("aria-valuemax")).toBe("800");
  });

  it("moves by a step with the arrow keys, in the direction the sash grows", () => {
    // direction -1: the region grows as the pointer moves towards the start (left or up).
    const { sash, onChange } = mount();
    fireEvent.keyDown(sash, { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith(336);
    fireEvent.keyDown(sash, { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith(304);
  });

  it("moves by a larger step with Shift held", () => {
    const { sash, onChange } = mount();
    fireEvent.keyDown(sash, { key: "ArrowLeft", shiftKey: true });
    expect(onChange).toHaveBeenLastCalledWith(384);
  });

  it("uses Up and Down for a horizontal sash", () => {
    const { sash, onChange } = mount({ orientation: "horizontal", direction: 1, label: "Resize the side panel" });
    fireEvent.keyDown(sash, { key: "ArrowDown" });
    expect(onChange).toHaveBeenLastCalledWith(336);
    fireEvent.keyDown(sash, { key: "ArrowUp" });
    expect(onChange).toHaveBeenLastCalledWith(304);
  });

  it("never asks for a value outside its bounds", () => {
    const { sash, onChange } = mount({ value: 250 });
    fireEvent.keyDown(sash, { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith(240);
    cleanup();
    const second = mount({ value: 790 });
    fireEvent.keyDown(second.sash, { key: "ArrowLeft" });
    expect(second.onChange).toHaveBeenLastCalledWith(800);
  });

  it("resets with Home and with a double-click", () => {
    const { sash, onReset } = mount();
    fireEvent.keyDown(sash, { key: "Home" });
    expect(onReset).toHaveBeenCalledTimes(1);
    fireEvent.doubleClick(sash);
    expect(onReset).toHaveBeenCalledTimes(2);
  });

  it("follows the pointer while it is held down, and stops when it is let go", () => {
    const { sash, onChange } = mount();
    fireEvent.pointerDown(sash, { clientX: 500, clientY: 10, pointerId: 1, button: 0 });
    fireEvent.pointerMove(sash, { clientX: 460, clientY: 10, pointerId: 1 });
    expect(onChange).toHaveBeenLastCalledWith(360); // 40px towards the start, direction -1
    fireEvent.pointerMove(sash, { clientX: 540, clientY: 10, pointerId: 1 });
    expect(onChange).toHaveBeenLastCalledWith(280);
    fireEvent.pointerUp(sash, { pointerId: 1 });
    fireEvent.pointerMove(sash, { clientX: 100, clientY: 10, pointerId: 1 });
    expect(onChange).toHaveBeenCalledTimes(2);
  });
});
