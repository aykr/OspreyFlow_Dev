// The Map editor's keyboard bind (spec 09 §4, "select both, Enter"; ADR-140 Amendment 8): a column
// chosen in the Source fields pane stays chosen until it is bound or let go, and every binding in
// the inspector then offers "Bind <column> here", which Enter (or a click) presses. Dragging the
// column onto the binding does the same through the same `setFieldAt(0, …)`. The chosen column is
// shared through this context so the inspector's many bindings need no new prop each.
import { createContext, useContext } from "react";

export interface ChosenColumn {
  column: string | null;
  /** Let the column go, after a bind or on its own button. */
  clear: () => void;
}

export const ChosenColumnContext = createContext<ChosenColumn>({ column: null, clear: () => undefined });

export function useChosenColumn(): ChosenColumn {
  return useContext(ChosenColumnContext);
}
