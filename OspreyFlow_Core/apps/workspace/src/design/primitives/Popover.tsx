import { useLayoutEffect, useRef, type CSSProperties, type ReactNode } from "react";

export interface PopoverProps {
  x: number;
  y: number;
  /** Phase 6a Stage 4: found while building the keyboard-action registry, against a real
   * browser, not assumed from reading `GlassCanvas.tsx`'s own `onKeyDown` — every caller of
   * `Popover` reaches it exclusively via a keyboard-opened flow (a right-click also focuses the
   * triggering node first) with no automatic focus of anything inside it, so a keyboard-only
   * analyst who opened one had no way to close it at all: the container's own `onKeyDown`
   * unconditionally lost focus to `<body>` the moment the opening control (a radial-menu item)
   * unmounted, and a handler on a div that no longer has focus never runs. `RadialMenu` already
   * solved exactly this for itself; `Popover` now does the same, once, for every overlay built on
   * it rather than each one re-solving it. */
  onClose: () => void;
  children: ReactNode;
}

/** A positioned overlay anchored at a page coordinate — the base every
 * DOM-anchored overlay in the Glass builds on (edge inspection, hover
 * cards): `spec/02_GLASS_FRONTEND.md` §1.1: "Labels, hover cards and
 * context menus are DOM overlays positioned from Sigma's camera... The
 * rich parts stay in HTML where they are easy." */
export function Popover({ x, y, onClose, children }: PopoverProps) {
  const ref = useRef<HTMLDivElement>(null);
  // The latest `onClose`, read when Escape is pressed. A parent passes a new one on every render;
  // keyed on it, the effect below re-ran on each render and took focus to the popover's first
  // button, so a notice left on the canvas closed the Layout menu the moment it was pressed
  // (20 October 2026; `Drawer` had the same fault, fixed 9 October).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // A layout effect, so Escape is heard from the moment the popover can be seen: a passive effect
  // runs after the page is painted, and on a slow machine an Escape pressed as the popover appeared
  // was lost (keyboard walkthroughs on CI, a different one each run; 20 October 2026).
  useLayoutEffect(() => {
    // The same shape as `RadialMenu`'s own mount effect: focus something inside once, when it
    // opens, rather than leaving focus to fall through to `<body>` (and independent of it — closing
    // on Escape does not depend on that focus still being here, since a `document`-level listener
    // hears the keypress regardless of what currently has focus inside this popover).
    ref.current?.querySelector<HTMLElement>("button, [tabindex]")?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const style: CSSProperties = { position: "fixed", left: x, top: y, zIndex: 30 };
  return (
    <div className="popover" style={style} role="dialog" ref={ref}>
      {children}
    </div>
  );
}
