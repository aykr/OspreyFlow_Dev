export interface RangeSliderProps {
  low: number;
  high: number;
  min: number;
  max: number;
  onChange: (low: number, high: number) => void;
  "aria-label": string;
}

/** Two overlapping native range inputs — keyboard-operable per-handle
 * (Tab moves focus between the two), simpler and more accessible than a
 * from-scratch pointer-drag implementation for the same two-handle
 * result. Used by the strength/degree filters (`docs/02_GLASS_FRONTEND.md`
 * §2's workspace layout). */
export function RangeSlider({ low, high, min, max, onChange, ...aria }: RangeSliderProps) {
  const percent = (v: number) => ((v - min) / (max - min)) * 100;
  return (
    <div className="range-slider">
      <div className="range-slider__track" />
      <div
        className="range-slider__fill"
        style={{ left: `${percent(low)}%`, width: `${percent(high) - percent(low)}%` }}
      />
      <input
        type="range"
        min={min}
        max={max}
        value={low}
        onChange={(e) => onChange(Math.min(Number(e.target.value), high), high)}
        aria-label={`${aria["aria-label"]} minimum`}
        style={{ position: "absolute", width: "100%", background: "transparent" }}
      />
      <input
        type="range"
        min={min}
        max={max}
        value={high}
        onChange={(e) => onChange(low, Math.max(Number(e.target.value), low))}
        aria-label={`${aria["aria-label"]} maximum`}
        style={{ position: "absolute", width: "100%", background: "transparent" }}
      />
    </div>
  );
}
