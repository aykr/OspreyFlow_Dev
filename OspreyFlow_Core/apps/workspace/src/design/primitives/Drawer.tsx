import type { ReactNode } from "react";
import { useLayoutEffect, useRef, useState } from "react";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Where focus goes on closing when what opened the drawer is gone or held no focus (a menu's item that closed
   * with its menu): the caller names the control to return to. */
  returnFocusTo?: () => HTMLElement | null;
}

/** The chrome a drawer opens under: the workspace's top bar (`shell/TopBar.tsx`), so the GOV.UK header above it
 * too, and the context row under it (`shell/ContextBanner.tsx`, its case switcher and cross-link at its right
 * end), in either brand. */
const CHROME_ABOVE = ".top-bar, .context-banner, .context-banner--govuk";

/** Where a drawer starts: under the chrome above the workspace, never over the navigation it carries (ADR-145
 * Amendment 14 decision 2, the owner's "the Cases panel covers the top navigation"); never above the window.
 * `null` where there is no such chrome: the stylesheet's top, 0. */
function underTheChrome(): number | null {
  const chrome = [...document.querySelectorAll(CHROME_ABOVE)];
  if (chrome.length === 0) return null;
  return Math.max(0, ...chrome.map((el) => Math.round(el.getBoundingClientRect().bottom)));
}

/** An overlay: shadow, no hairline (`spec/02_GLASS_FRONTEND.md` §8). Used
 * for the Inspector and named-step history panel. Not modal (ADR-145 Amendment 14 decision 2): it neither
 * traps focus nor makes the page behind it inert, and the navigation beside it stays usable. */
export function Drawer({ open, onClose, title, children, returnFocusTo }: DrawerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState<number | null>(null);
  // The latest `onClose`, read when Escape is pressed. A parent may pass a new one on every
  // render; keyed on it, the effect below re-ran on each keystroke in a field inside the drawer and
  // took focus back to the drawer (9 October 2026, *Record an assessment*).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const returnRef = useRef(returnFocusTo);
  returnRef.current = returnFocusTo;

  // A layout effect, so Escape is heard from the moment it can be seen (as `Popover`).
  useLayoutEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    // Closing returns focus to whatever opened it (the owner's navigation decision, ADR-145 Amendment 15): its rail
    // opener, or *Views in this case*. Not when focus has already gone somewhere else the person chose.
    const opener = document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null;
    const drawer = ref.current;
    drawer?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      const now = document.activeElement;
      const lost = now === null || now === document.body || (drawer !== null && drawer.contains(now));
      if (!lost) return;
      const back = opener?.isConnected ? opener : (returnRef.current?.() ?? null);
      back?.focus();
    };
  }, [open]);

  // Measured before the first paint, and again whenever the chrome or the window changes size (the bar
  // wraps on a narrow window, ADR-115 Amendment 3) or the page scrolls (the GOV.UK footer is below).
  useLayoutEffect(() => {
    if (!open) return;
    const fit = () => setTop(underTheChrome());
    fit();
    // jsdom has no ResizeObserver.
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(fit) : null;
    for (const el of document.querySelectorAll(CHROME_ABOVE)) observer?.observe(el);
    window.addEventListener("resize", fit);
    window.addEventListener("scroll", fit, { passive: true });
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", fit);
      window.removeEventListener("scroll", fit);
    };
  }, [open]);

  if (!open) return null;
  return (
    <div
      className="drawer"
      role="dialog"
      aria-label={title}
      tabIndex={-1}
      ref={ref}
      style={top === null ? undefined : { top }}
    >
      {/* A visible way out beside Escape (the owner, 9 October 2026: "how do I close the
          questions panel?"). */}
      <div className="panel__title drawer__title">
        {title}
        <button type="button" className="btn btn--quiet" aria-label={`Close ${title}`} onClick={onClose}>
          Close
        </button>
      </div>
      <div className="panel__body">{children}</div>
    </div>
  );
}
