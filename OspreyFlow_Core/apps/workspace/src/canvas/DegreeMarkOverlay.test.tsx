// @vitest-environment jsdom
// ADR-116 decision 4: a route put on the canvas marks each of its nodes with its degree from From.
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DegreeMarkOverlay } from "./DegreeMarkOverlay";

afterEach(cleanup);

function fakeSigma() {
  const listeners = new Set<() => void>();
  return {
    on: (_: string, fn: () => void) => listeners.add(fn),
    removeListener: (_: string, fn: () => void) => listeners.delete(fn),
    redraw: () => act(() => listeners.forEach((fn) => fn())),
  };
}

const at = (id: string) => ({ a: { x: 100, y: 50 }, b: { x: 200, y: 50 }, c: { x: 300, y: 50 } })[id] ?? null;

describe("DegreeMarkOverlay", () => {
  it("marks From, and each other node with its degrees from From, beside the node", () => {
    render(
      <DegreeMarkOverlay sigmaRef={{ current: fakeSigma() as never }} degrees={new Map([["a", 0], ["b", 1], ["c", 2]])} positionOf={at} />,
    );
    expect(screen.getByLabelText("From").textContent).toBe("From");
    expect(screen.getByLabelText("1 degree from From").textContent).toBe("1°");
    const two = screen.getByLabelText("2 degrees from From");
    expect(two.textContent).toBe("2°");
    // Below and to the left, clear of a judgement count, which sits above and to the right.
    expect(parseFloat(two.style.left)).toBeLessThan(300);
    expect(parseFloat(two.style.top)).toBeGreaterThan(50);
    expect((two.parentElement as HTMLElement).style.pointerEvents).toBe("none");
  });

  it("marks nothing for a node not drawn", () => {
    render(<DegreeMarkOverlay sigmaRef={{ current: fakeSigma() as never }} degrees={new Map([["gone", 1]])} positionOf={at} />);
    expect(screen.queryByLabelText("1 degree from From")).toBeNull();
  });
});
