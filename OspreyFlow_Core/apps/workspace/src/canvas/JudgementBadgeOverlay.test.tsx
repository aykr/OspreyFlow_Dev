// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { JudgementBadgeOverlay } from "./JudgementBadgeOverlay";

afterEach(cleanup);

function fakeSigma() {
  const listeners = new Set<() => void>();
  const sigma = {
    on: (_: string, fn: () => void) => listeners.add(fn),
    removeListener: (_: string, fn: () => void) => listeners.delete(fn),
  };
  return { sigma, redraw: () => act(() => listeners.forEach((fn) => fn())) };
}

const at = (id: string) => (id === "n1" ? { x: 100, y: 50 } : id === "n2" ? { x: 300, y: 80 } : null);

describe("JudgementBadgeOverlay", () => {
  it("puts a small count beside each node that has judgements", () => {
    const { sigma } = fakeSigma();
    render(
      <JudgementBadgeOverlay
        sigmaRef={{ current: sigma as never }}
        counts={new Map([["n1", 2], ["n2", 1]])}
        positionOf={at}
      />,
    );
    const two = screen.getByLabelText("2 judgements");
    const one = screen.getByLabelText("1 judgement");
    expect(two.textContent).toBe("2");
    expect(one.textContent).toBe("1");
    // Beside the node, up and to the right of it, not on top of it.
    expect(parseFloat(two.style.left)).toBeGreaterThan(100);
    expect(parseFloat(two.style.top)).toBeLessThan(50);
  });

  it("draws nothing for a node that is not drawn (folded away, or not on the canvas)", () => {
    const { sigma } = fakeSigma();
    render(
      <JudgementBadgeOverlay
        sigmaRef={{ current: sigma as never }}
        counts={new Map([["gone", 3]])}
        positionOf={at}
      />,
    );
    expect(screen.queryByLabelText("3 judgements")).toBeNull();
  });

  it("is only a picture: it lets every click through to the canvas and takes no focus", () => {
    const { sigma } = fakeSigma();
    render(
      <JudgementBadgeOverlay sigmaRef={{ current: sigma as never }} counts={new Map([["n1", 1]])} positionOf={at} />,
    );
    const badge = screen.getByLabelText("1 judgement");
    expect((badge.parentElement as HTMLElement).style.pointerEvents).toBe("none");
    expect(badge.getAttribute("tabindex")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("follows the node when the canvas draws again", () => {
    const { sigma, redraw } = fakeSigma();
    let x = 100;
    render(
      <JudgementBadgeOverlay
        sigmaRef={{ current: sigma as never }}
        counts={new Map([["n1", 1]])}
        positionOf={() => ({ x, y: 50 })}
      />,
    );
    const before = parseFloat(screen.getByLabelText("1 judgement").style.left);
    x = 400;
    redraw();
    expect(parseFloat(screen.getByLabelText("1 judgement").style.left)).toBe(before + 300);
  });

  it("still appears when the canvas is only created after the overlay is mounted", async () => {
    const { sigma } = fakeSigma();
    const ref: { current: never | null } = { current: null };
    render(
      <JudgementBadgeOverlay sigmaRef={ref as never} counts={new Map([["n1", 2]])} positionOf={at} />,
    );
    expect(screen.queryByLabelText("2 judgements")).toBeNull();
    ref.current = sigma as never;
    await waitFor(() => expect(screen.getByLabelText("2 judgements")).toBeTruthy());
  });

  it("draws nothing when no node has a judgement", () => {
    const { sigma } = fakeSigma();
    const { container } = render(
      <JudgementBadgeOverlay sigmaRef={{ current: sigma as never }} counts={new Map()} positionOf={at} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
