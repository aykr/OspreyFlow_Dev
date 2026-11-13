import type { ReactNode } from "react";
import { useLayoutEffect, useRef, useState } from "react";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/** An overlay: shadow, no hairline (`spec/02_GLASS_FRONTEND.md` §8). Used
 * for the Inspector and named-step history panel. */
/** Where a drawer starts: under the workspace's top bar (`shell/TopBar.tsx`), and so under the GOV.UK
 * header above it, never over the navigation they carry (ADR-145 Amendment 14 decision 2, the owner's "the
 * Cases panel covers the top navigation"). `null` where there is no top bar: the stylesheet's top, 0. */
function underTheTopBar(): number | null {
  const bar = document.querySelector(".top-bar");
  if (!bar) return null;
  return Math.max(0, Math.round(bar.getBoundingClientRect().bottom));
}

export function Drawer({ open, onClose, title, children }: DrawerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState<number | null>(null);
  // The latest `onClose`, read when Escape is pressed. A parent may pass a new one on every
  // render; keyed on it, the effect below re-ran on each keystroke in a field inside the drawer and
  // took focus back to the drawer (9 October 2026, *Record an assessment*).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // A layout effect, so Escape is heard from the moment it can be seen (as `Popover`).
  useLayoutEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    ref.current?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  // Measured before the first paint, and again whenever the bar or the window changes size (the bar
  // wraps on a narrow window, ADR-115 Amendment 3) or the page scrolls (the GOV.UK footer is below).
  useLayoutEffect(() => {
    if (!open) return;
    const fit = () => setTop(underTheTopBar());
    fit();
    const bar = document.querySelector(".top-bar");
    // jsdom has no ResizeObserver.
    const observer = bar && typeof ResizeObserver !== "undefined" ? new ResizeObserver(fit) : null;
    if (bar) observer?.observe(bar);
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
      aria-modal="true"
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
