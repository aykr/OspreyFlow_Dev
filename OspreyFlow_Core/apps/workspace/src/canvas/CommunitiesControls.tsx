// The Communities control (ADR-066): switches the grouping of the nodes now in view on and off, and
// folds or opens every group at once. Everything it drives is a way of looking at the view; nothing
// is stored and nothing is sent to the server.

export interface CommunitiesControlsProps {
  on: boolean;
  groupCount: number;
  foldedCount: number;
  onToggle: () => void;
  onCollapseAll: () => void;
  onExpandAll: () => void;
}

export function CommunitiesControls({
  on,
  groupCount,
  foldedCount,
  onToggle,
  onCollapseAll,
  onExpandAll,
}: CommunitiesControlsProps) {
  return (
    <div
      style={{
        position: "absolute",
        top: 44,
        left: 48,
        zIndex: 10,
        display: "flex",
        gap: "var(--sp-4)",
        alignItems: "center",
      }}
    >
      <button
        type="button"
        className="radial-menu__item"
        aria-pressed={on}
        title="Group closely linked nodes, and fold a group into one node"
        onClick={onToggle}
      >
        Communities
      </button>
      {on && groupCount === 0 ? (
        <span style={{ color: "var(--text-secondary)" }}>No groups found among these nodes</span>
      ) : null}
      {on && groupCount > 0 ? (
        <>
          <span style={{ color: "var(--text-secondary)" }}>
            {`${groupCount} ${groupCount === 1 ? "group" : "groups"}, ${foldedCount} folded`}
          </span>
          <button
            type="button"
            className="radial-menu__item"
            disabled={foldedCount >= groupCount}
            onClick={onCollapseAll}
          >
            Collapse all
          </button>
          <button
            type="button"
            className="radial-menu__item"
            disabled={foldedCount === 0}
            onClick={onExpandAll}
          >
            Expand all
          </button>
        </>
      ) : null}
    </div>
  );
}
