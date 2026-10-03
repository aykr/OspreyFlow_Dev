import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export interface DropdownPanelProps {
  /** What the button says. A ▾ is added. */
  label: ReactNode;
  /** The panel's own accessible name. */
  panelLabel: string;
  /** Full text for a label that may be cut short with an ellipsis. */
  title?: string;
  /** Extra class on the button. */
  buttonClassName?: string;
  /** Open towards the left instead of the right of the button (for a button at the right-hand edge). */
  alignRight?: boolean;
  /** The panel's content; given a function that closes the panel. */
  children: ReactNode | ((close: () => void) => ReactNode);
}

/** A button that opens a small panel beneath it (ADR-065). The panel is not in the page until
 * opened; it closes on Escape (focus returns to the button), on a click outside, and when
 * keyboard focus moves outside it, so it never traps a keyboard user. */
export function DropdownPanel({ label, panelLabel, title, alignRight = false, buttonClassName, children }: DropdownPanelProps) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as globalThis.Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const close = () => setOpen(false);

  return (
    <div
      className="menu"
      ref={wrapper}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation();
          setOpen(false);
          trigger.current?.focus();
        }
      }}
      onBlur={(event) => {
        const next = event.relatedTarget as globalThis.Node | null;
        if (open && next && wrapper.current && !wrapper.current.contains(next)) setOpen(false);
      }}
    >
      <button
        ref={trigger}
        type="button"
        className={buttonClassName ? `btn menu-button ${buttonClassName}` : "btn menu-button"}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        title={title}
        onClick={() => setOpen((was) => !was)}
      >
        <span className="menu-button__label">{label}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div
          id={panelId}
          role="group"
          aria-label={panelLabel}
          className={alignRight ? "menu-panel menu-panel--right" : "menu-panel"}
        >
          {typeof children === "function" ? children(close) : children}
        </div>
      )}
    </div>
  );
}
