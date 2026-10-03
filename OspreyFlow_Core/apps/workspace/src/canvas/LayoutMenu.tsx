import { LAYOUT_MODES, type LayoutMode } from "./layoutModes";

export interface LayoutMenuProps {
  mode: LayoutMode;
  onChange: (mode: LayoutMode) => void;
  /** Arrange again with the current layout: re-centres a radial layout on the node now selected. */
  onArrange: () => void;
}

/** Chooses how the working set is arranged. Choosing arranges at once; the layout then also
 * applies to nodes added later, until another is chosen. */
export function LayoutMenu({ mode, onChange, onArrange }: LayoutMenuProps) {
  return (
    <div
      style={{
        position: "absolute",
        top: 8,
        left: 48,
        zIndex: 10,
        display: "flex",
        gap: "var(--sp-4)",
      }}
    >
      <select
        aria-label="Layout"
        value={mode}
        onChange={(e) => onChange(e.target.value as LayoutMode)}
      >
        {LAYOUT_MODES.map((entry) => (
          <option key={entry.mode} value={entry.mode}>
            {entry.label}
          </option>
        ))}
      </select>
      <button type="button" className="radial-menu__item" onClick={onArrange}>
        Arrange again
      </button>
    </div>
  );
}
