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

/** The switch, a segment of the canvas toolbar's Show group (ADR-097 step 2). */
export function CommunitiesToggle({ on, onToggle }: Pick<CommunitiesControlsProps, "on" | "onToggle">) {
  return (
    <button
      type="button"
      className="radial-menu__item"
      aria-pressed={on}
      title="Group closely linked nodes, and fold a group into one node"
      onClick={onToggle}
    >
      Communities
    </button>
  );
}

/** What the grouping found, and folding or opening every group at once: shown while it is on. */
export function CommunitiesStatus({
  on,
  groupCount,
  foldedCount,
  onCollapseAll,
  onExpandAll,
}: Omit<CommunitiesControlsProps, "onToggle">) {
  if (!on) return null;
  if (groupCount === 0) return <span className="canvas-toolbar__note">No groups found among these nodes</span>;
  return (
    <span className="canvas-toolbar__status">
      <span className="canvas-toolbar__note">
        {`${groupCount} ${groupCount === 1 ? "group" : "groups"}, ${foldedCount} folded`}
      </span>
      <button type="button" className="radial-menu__item" disabled={foldedCount >= groupCount} onClick={onCollapseAll}>
        Collapse all
      </button>
      <button type="button" className="radial-menu__item" disabled={foldedCount === 0} onClick={onExpandAll}>
        Expand all
      </button>
    </span>
  );
}

/** Both together, as one control. */
export function CommunitiesControls(props: CommunitiesControlsProps) {
  return (
    <span className="canvas-toolbar__status">
      <CommunitiesToggle on={props.on} onToggle={props.onToggle} />
      <CommunitiesStatus {...props} />
    </span>
  );
}
