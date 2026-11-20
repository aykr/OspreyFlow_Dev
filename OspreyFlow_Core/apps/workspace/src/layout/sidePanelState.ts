// The hooks over the right panel's mode (ADR-115 E4) and over whether the viewport is wide enough to dock it. The mode,
// its setters and `isWide` are plain TypeScript in `packages/glass-shared` (`layout/sidePanelState.ts`, since ADR-152
// decision 6), so a page that is not React shares them.
import { useSyncExternalStore } from "react";

import {
  currentSidePanelMode as current,
  isWide,
  sidePanelListeners as listeners,
  type SidePanelMode,
} from "@ospreyflow/glass-shared";

export function useSidePanelMode(initial: SidePanelMode = "normal"): SidePanelMode {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current(initial),
  );
}

/** Whether the viewport is wide enough to dock the panel, following resizes. */
export function useWide(): boolean {
  return useSyncExternalStore(
    (listener) => {
      window.addEventListener("resize", listener);
      return () => window.removeEventListener("resize", listener);
    },
    isWide,
  );
}
