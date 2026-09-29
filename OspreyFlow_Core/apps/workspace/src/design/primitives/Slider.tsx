import type { SyntheticEvent } from "react";

export interface SliderProps {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  /**
   * Fires once when a drag gesture ends (native `mouseup`/`touchend`/`keyup`), never mid-drag.
   * `onChange` alone fires on every value change during a drag — a caller that wants to commit
   * only on release (Phase 6a Stage 2's own resolution-threshold control, so it doesn't call an
   * endpoint that re-projects the whole working set on every intermediate value) needs this.
   * Optional and backward-compatible: omitting it leaves every existing caller unchanged.
   */
  onCommit?: (value: number) => void;
  "aria-label": string;
}

export function Slider({ value, min, max, step = 1, onChange, onCommit, ...aria }: SliderProps) {
  const commit = (e: SyntheticEvent<HTMLInputElement>) => {
    onCommit?.(Number(e.currentTarget.value));
  };
  return (
    <input
      type="range"
      className="slider"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      onMouseUp={commit}
      onTouchEnd={commit}
      onKeyUp={commit}
      aria-label={aria["aria-label"]}
    />
  );
}
