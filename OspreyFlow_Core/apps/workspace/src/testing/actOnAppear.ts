import type { ReactNode } from "react";
import { createRoot } from "react-dom/client";

/** Renders `element` as a page does after a fetch answers — outside `act`, which would run its
 * effects at once — and calls `onAppear` the moment `selector` is in the page, before React's
 * passive effects have run, as a fast keyboard user or a browser test acts on what it can see.
 * Then lets the effects run and calls `afterwards` before unmounting. A passive effect that adds a
 * listener misses what `onAppear` does; one that moves focus takes it from where `onAppear` put it
 * (CI keyboard walkthroughs, 20 October 2026). */
export async function actOnAppear(
  element: ReactNode,
  selector: string,
  onAppear: (host: HTMLElement) => void,
  afterwards: () => void = () => undefined,
): Promise<void> {
  const flag = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const previous = flag.IS_REACT_ACT_ENVIRONMENT;
  flag.IS_REACT_ACT_ENVIRONMENT = false;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const appeared = new Promise<void>((resolve) => {
    new MutationObserver((_, observer) => {
      if (host.querySelector(selector) === null) return;
      observer.disconnect();
      onAppear(host);
      resolve();
    }).observe(host, { childList: true, subtree: true });
  });
  try {
    root.render(element);
    await appeared;
    await new Promise((resolve) => setTimeout(resolve, 50));
    afterwards();
  } finally {
    root.unmount();
    host.remove();
    flag.IS_REACT_ACT_ENVIRONMENT = previous;
  }
}

/** Presses Escape the moment `selector` is in the page (see `actOnAppear`). */
export function pressEscapeOnAppear(element: ReactNode, selector: string): Promise<void> {
  return actOnAppear(element, selector, () =>
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })),
  );
}
