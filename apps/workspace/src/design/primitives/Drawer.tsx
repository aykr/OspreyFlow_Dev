import type { ReactNode } from "react";
import { useEffect, useRef } from "react";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/** An overlay: shadow, no hairline (`docs/02_GLASS_FRONTEND.md` §8). Used
 * for the Inspector and named-step history panel. */
export function Drawer({ open, onClose, title, children }: DrawerProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    ref.current?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

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
      <div className="panel__title">{title}</div>
      <div className="panel__body">{children}</div>
    </div>
  );
}
