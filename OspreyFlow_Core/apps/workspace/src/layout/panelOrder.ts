// The hook over the order of the right-hand column's panels (ADR-085). The order, and what keeps it (this browser's
// storage only, never sent, not part of the case), are plain TypeScript in `packages/glass-shared`
// (`layout/panelOrder.ts`, since ADR-152 decision 6), so a page that is not React reads and sets it too.
import { useSyncExternalStore } from "react";

import { getSidePanelOrder, onSidePanelOrderChange, type SidePanelOrder } from "@ospreyflow/glass-shared";

/** The order, re-rendering the caller when it changes. */
export function useSidePanelOrder(): SidePanelOrder {
  return useSyncExternalStore(onSidePanelOrderChange, getSidePanelOrder, getSidePanelOrder);
}
