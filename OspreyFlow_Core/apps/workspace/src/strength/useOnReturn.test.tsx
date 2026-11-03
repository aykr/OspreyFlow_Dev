// @vitest-environment jsdom
// Build order step 18c (the 3 November rehearsal's D9): after the case's Author switched the case to
// client parity in another window, the analyst's legend still read "Composition: standard" until it
// was reopened. The legend is read again whenever the analyst comes back to the window.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useOnReturn } from "./useOnReturn";

afterEach(cleanup);

function Probe({ onReturn }: { onReturn: () => void }) {
  useOnReturn(onReturn);
  return null;
}

function setHidden(hidden: boolean) {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => (hidden ? "hidden" : "visible") });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("useOnReturn", () => {
  it("calls back when the window is focused again or the tab shown again, not when it is hidden", () => {
    const onReturn = vi.fn();
    render(<Probe onReturn={onReturn} />);
    expect(onReturn).not.toHaveBeenCalled();
    window.dispatchEvent(new Event("focus"));
    expect(onReturn).toHaveBeenCalledTimes(1);
    setHidden(true);
    expect(onReturn).toHaveBeenCalledTimes(1);
    setHidden(false);
    expect(onReturn).toHaveBeenCalledTimes(2);
  });

  it("stops listening once unmounted", () => {
    const onReturn = vi.fn();
    const { unmount } = render(<Probe onReturn={onReturn} />);
    unmount();
    window.dispatchEvent(new Event("focus"));
    expect(onReturn).not.toHaveBeenCalled();
  });
});
