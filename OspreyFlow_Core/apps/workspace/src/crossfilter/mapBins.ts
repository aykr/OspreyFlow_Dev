// The map's bins follow the cross-filter's inputs — the window, the node selection and, from
// ADR-130 decision 2, the weekly view's chosen cells — as `02_GLASS_FRONTEND.md` §3.4 has the map
// restrict to the brush. Lifted out of `App.tsx` so the keyboard harness proves the very wiring the
// Glass runs, not a copy of it.
import type { StoreApi } from "zustand/vanilla";

import type { GeoBin } from "../../../../packages/schemas/generated";
import { fetchGeoBins } from "../analytics/api";
import { buildEventFilter, type CrossFilterStoreState } from "./store";

/** Reads the bins now and again whenever a filter input they depend on changes; returns the
 * unsubscribe. */
export function followCrossFilterWithMapBins(
  store: StoreApi<CrossFilterStoreState>,
  apiBaseUrl: string,
  bearerToken: string,
  scope: string,
  precision: number,
  onBins: (bins: GeoBin[]) => void,
): () => void {
  // An older answer arriving after a newer one is dropped.
  let latest = 0;
  async function refresh(state: CrossFilterStoreState) {
    latest += 1;
    const mine = latest;
    const filter = buildEventFilter(scope, state.window, state.selectedNodeIds, state.cells);
    const bins = await fetchGeoBins(apiBaseUrl, bearerToken, { filter, precision });
    if (mine === latest) onBins(bins);
  }
  let lastWindow = store.getState().window;
  let lastSelected = store.getState().selectedNodeIds;
  let lastCells = store.getState().cells;
  void refresh(store.getState());
  return store.subscribe((state) => {
    if (
      state.window === lastWindow &&
      state.selectedNodeIds === lastSelected &&
      state.cells === lastCells
    )
      return;
    lastWindow = state.window;
    lastSelected = state.selectedNodeIds;
    lastCells = state.cells;
    void refresh(state);
  });
}
