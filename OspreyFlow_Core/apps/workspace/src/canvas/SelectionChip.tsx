// While anything is selected, a chip in the canvas corner says how many, with Clear (ADR-093 step 3),
// so the selection is never invisible however small its nodes are drawn.
export interface SelectionChipProps {
  count: number;
  onClear: () => void;
}

export function SelectionChip({ count, onClear }: SelectionChipProps) {
  if (count === 0) return null;
  return (
    <div
      role="status"
      style={{
        position: "absolute",
        left: "var(--sp-8)",
        bottom: "var(--sp-8)",
        zIndex: 5,
        display: "flex",
        alignItems: "center",
        gap: "var(--sp-8)",
        padding: "var(--sp-4) var(--sp-8)",
        background: "var(--surface-raised)",
        border: "1px solid var(--border)",
        borderRadius: "var(--sp-4)",
        color: "var(--text-primary)",
        fontSize: "var(--fs-13)",
      }}
    >
      <span>{count.toLocaleString("en-GB")} selected</span>
      <button type="button" className="btn" aria-label="Clear the selection" onClick={onClear}>
        Clear
      </button>
    </div>
  );
}
