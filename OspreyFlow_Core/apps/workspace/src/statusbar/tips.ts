// The workspace's tips (ADR-115 E4; the reference's status bar). Each names only what the Glass does:
// Enter expands (spec 02), F fits, Esc clears the selection.
export const WORKSPACE_TIPS = [
  "Press / to search entities, identifiers and documents.",
  "Select a node and press Enter to expand it by one hop. The count is shown before anything is drawn.",
  "Shift-click to add to the selection. Esc clears it.",
  "Brush the timeline to dim everything outside the window. Nothing is removed from the canvas.",
  "Dashed links were inferred by the model. Solid links come from a source record.",
  "Branch a selection to work on it in a new case without changing this one.",
] as const;
