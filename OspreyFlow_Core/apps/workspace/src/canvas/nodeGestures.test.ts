// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import {
  expandOnDoubleClick,
  menuRequestForRightClick,
  previewCountFrom,
} from "./nodeGestures";

/** Seen 3 October 2026: the browser's own right-click menu opened on top of the Glass menu; a
 * left click seemed to do nothing; a failed count preview sat as `(…)` for ever. */

function mouse(x: number, y: number): MouseEvent {
  return new MouseEvent("contextmenu", {
    clientX: x,
    clientY: y,
    cancelable: true,
  });
}

describe("right-click on a node", () => {
  it("stops the browser's own menu appearing", () => {
    const original = mouse(10, 20);
    menuRequestForRightClick(original, "n1");
    expect(original.defaultPrevented).toBe(true);
  });

  it("opens the list layout at the click, because radial cannot fit long labels", () => {
    expect(menuRequestForRightClick(mouse(10, 20), "n1")).toEqual({
      x: 10,
      y: 20,
      nodeId: "n1",
      layout: "list",
    });
  });
});

describe("double-click on a node", () => {
  it("expands its neighbours and stops the canvas zooming instead", () => {
    const original = new MouseEvent("dblclick", {
      clientX: 5,
      clientY: 6,
      cancelable: true,
    });
    const preventSigmaDefault = vi.fn();
    const expand = vi.fn();
    expandOnDoubleClick({ original, preventSigmaDefault }, "n1", expand);
    expect(preventSigmaDefault).toHaveBeenCalledOnce();
    expect(expand).toHaveBeenCalledWith("n1", 5, 6);
  });
});

describe("a count preview", () => {
  it("is the number the expansion would add", () => {
    expect(previewCountFrom({ ok: true, candidateNodeCount: 12 }, 4)).toBe(8);
  });

  it("is never negative", () => {
    expect(previewCountFrom({ ok: true, candidateNodeCount: 2 }, 4)).toBe(0);
  });

  it("is 'unavailable' when the server refused or the call failed", () => {
    expect(previewCountFrom({ ok: false }, 4)).toBe("unavailable");
  });
});
