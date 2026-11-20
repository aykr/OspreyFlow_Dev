// The hook over the sizes an analyst drags the sashes to (ADR-086). The sizes themselves, and what keeps them (this
// browser's storage only, never sent, not part of the case), are plain TypeScript in `packages/glass-shared`
// (`layout/layoutSizes.ts`, since ADR-152 decision 6), so a page that is not React reads and sets them too.
import { useSyncExternalStore } from "react";

import { getLayoutSizes, onLayoutSizesChange, type LayoutSizes } from "@ospreyflow/glass-shared";

/** The sizes, re-rendering the caller when they change. */
export function useLayoutSizes(): LayoutSizes {
  return useSyncExternalStore(onLayoutSizesChange, getLayoutSizes, getLayoutSizes);
}
