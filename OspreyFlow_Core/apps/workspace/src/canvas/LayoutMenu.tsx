import { LAYOUT_MODES, type LayoutMode } from "./layoutModes";

/** What the Clustered bubbles layout puts in one bubble. */
export type BubbleKey = "type" | "community";

const BUBBLE_KEYS: { key: BubbleKey; label: string }[] = [
  { key: "type", label: "Entity type" },
  { key: "community", label: "Community" },
];

export interface LayoutMenuProps {
  mode: LayoutMode;
  onChange: (mode: LayoutMode) => void;
  /** For Clustered bubbles: what a bubble holds. Offered only while that layout is chosen. */
  bubbleKey?: BubbleKey;
  onBubbleKeyChange?: (key: BubbleKey) => void;
  /** Arrange again with the current layout: re-centres a radial layout on the node now selected. */
  onArrange: () => void;
}

/** Chooses how the working set is arranged. Choosing arranges at once; the layout then also
 * applies to nodes added later, until another is chosen. */
export function LayoutMenu({ mode, onChange, bubbleKey = "type", onBubbleKeyChange, onArrange }: LayoutMenuProps) {
  return (
    // Placed in the canvas toolbar's Layout group by `GlassCanvas` (ADR-097 step 2).
    <span className="canvas-toolbar__status">
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
      {mode === "bubbles" && onBubbleKeyChange && (
        <select
          aria-label="Bubbles by"
          value={bubbleKey}
          onChange={(e) => onBubbleKeyChange(e.target.value as BubbleKey)}
        >
          {BUBBLE_KEYS.map((entry) => (
            <option key={entry.key} value={entry.key}>
              {entry.label}
            </option>
          ))}
        </select>
      )}
      <button type="button" className="radial-menu__item" title="Arrange again with this layout" onClick={onArrange}>
        Arrange
      </button>
    </span>
  );
}
