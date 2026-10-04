// A sash is the draggable edge between two regions (ADR-086), as in VS Code: a thin strip the
// pointer can drag, and a separator the keyboard can reach and move with the arrow keys. `Home`
// and a double-click reset it. It owns no size itself: it reports the size the region should
// take and the owner stores and applies it.
import { useRef, type KeyboardEvent, type PointerEvent } from "react";

import { clamp } from "./layoutSizes";

export const SASH_STEP = 16;
export const SASH_LARGE_STEP = 64;
export const SASH_THICKNESS = 6;

export interface SashProps {
  /** What the sash resizes, in words: "Resize the side panel". */
  label: string;
  /** A vertical sash sits between things side by side and resizes a width; a horizontal one sits
   * between things stacked and resizes a height. */
  orientation: "vertical" | "horizontal";
  value: number;
  min: number;
  max: number;
  /** `1` when the region grows as the pointer moves right or down (a region above or to the left
   * of the sash); `-1` when it grows as the pointer moves left or up. */
  direction: 1 | -1;
  onChange: (next: number) => void;
  onReset: () => void;
}

export function Sash({ label, orientation, value, min, max, direction, onChange, onReset }: SashProps) {
  const drag = useRef<{ pointerId: number; start: number; from: number } | null>(null);
  const vertical = orientation === "vertical";
  const axis = (e: { clientX: number; clientY: number }) => (vertical ? e.clientX : e.clientY);

  const move = (delta: number) => onChange(clamp(value + delta * direction, min, max));

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? SASH_LARGE_STEP : SASH_STEP;
    const forward = vertical ? "ArrowRight" : "ArrowDown";
    const back = vertical ? "ArrowLeft" : "ArrowUp";
    if (e.key === forward) {
      e.preventDefault();
      move(step);
    } else if (e.key === back) {
      e.preventDefault();
      move(-step);
    } else if (e.key === "Home") {
      e.preventDefault();
      onReset();
    } else if (e.key === "Enter" || e.key === "Escape") {
      e.currentTarget.blur();
    }
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    // Only the primary button starts a drag; a test double with no button counts as primary.
    if (e.button !== undefined && e.button !== 0) return;
    drag.current = { pointerId: e.pointerId, start: axis(e), from: value };
    e.currentTarget.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.pointerId !== e.pointerId) return;
    onChange(clamp(d.from + (axis(e) - d.start) * direction, min, max));
  };
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId !== e.pointerId) return;
    drag.current = null;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  };

  return (
    <div
      role="separator"
      aria-label={label}
      aria-orientation={orientation}
      aria-valuenow={Math.round(value)}
      aria-valuemin={Math.round(min)}
      aria-valuemax={Math.round(max)}
      tabIndex={0}
      data-sash={orientation}
      className="sash"
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={onReset}
      style={{
        flexShrink: 0,
        cursor: vertical ? "col-resize" : "row-resize",
        width: vertical ? SASH_THICKNESS : undefined,
        height: vertical ? undefined : SASH_THICKNESS,
        alignSelf: "stretch",
        touchAction: "none",
      }}
    />
  );
}
