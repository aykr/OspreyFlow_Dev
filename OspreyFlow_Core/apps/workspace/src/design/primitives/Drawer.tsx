import type { ReactNode } from "react";
import { useEffect, useRef } from "react";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/** An overlay: shadow, no hairline (`spec/02_GLASS_FRONTEND.md` §8). Used
 * for the Inspector and named-step history panel. */
export function Drawer({ open, onClose, title, children }: DrawerProps) {
  const ref = useRef<HTMLDivElement>(null);
  // The latest `onClose`, read when Escape is pressed. A parent may pass a new one on every
  // render; keyed on it, the effect below re-ran on each keystroke in a field inside the drawer and
  // took focus back to the drawer (9 October 2026, *Record an assessment*).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    ref.current?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
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
