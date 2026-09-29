// The cross-filter store — `spec/02_GLASS_FRONTEND.md` §2 rule 3
// ("Everything cross-filters... A brush on the timeline dims the graph") and
// rule 2 ("Filters dim, they do not remove"), `08_ACCEPTANCE_SCENARIOS.md` A3.
//
// Mirrors `workingset/store.ts`'s vanilla-store split deliberately: this
// module holds only the filter *inputs* (`window`, `selectedNodeIds`) and
// their *derived* dimming result as plain reactive state, never the working
// set's own graphology instance — `GlassCanvas.tsx` reads `dimmedNodeIds`
// from here to feed its own `refreshNodeVisualState`, the same way it reads
// `filteredCount` from the working-set store, rather than this module
// reaching into the graph itself.
//
// **The dimming mechanism reuses existing `AnalyticsPort` machinery rather
// than needing a new one.** `source_id`/`target_id` are already whitelisted
// top-level fields for `CATEGORICAL` bucketing
// (`analytics_duckdb/adapter.py`'s `_categorical_histogram`) — a
// `cross_filter` call with one dimension per field returns exactly the set
// of node ids with at least one event matching the current filter, in the
// same round trip the timeline/histogram panels' own dimensions could ride
// alongside (they don't yet — see this module's own scope note below).
import { createStore, type StoreApi } from "zustand/vanilla";

import type { EventFilter } from "../../../../packages/schemas/generated";
import { fetchCrossFilter } from "../analytics/api";

export interface TimeWindow {
  validFrom: string;
  validTo: string | null;
}

export interface CrossFilterStoreState {
  /** Set by the timeline's brush (`08_ACCEPTANCE_SCENARIOS.md` A5) —
   * `null` means no temporal restriction. */
  window: TimeWindow | null;
  /** Set by a canvas selection, a histogram bar click, or a map cell
   * selection (A3's own "select the hotspot cells") — `null` means no
   * node restriction. */
  selectedNodeIds: string[] | null;
  /** Every currently-known node id that does *not* survive the active
   * filter — empty whenever no filter is active, per rule 2: nothing is
   * ever removed, only dimmed, and dimming only exists once a filter is
   * actually set. */
  dimmedNodeIds: ReadonlySet<string>;
  /** For `StatusBar`'s `dimmedCount` prop (`spec/02_GLASS_FRONTEND.md`
   * §2 rule 4 — "the status bar never lies"). */
  dimmedCount: number;
  setWindow: (window: TimeWindow | null) => void;
  setSelectedNodeIds: (nodeIds: string[] | null) => void;
  clearFilter: () => void;
}

/** The `EventFilter` the current filter inputs describe — exported so the
 * timeline and histogram panels can build the *same* filter for their own
 * `histogram`/`geo_bins` calls without duplicating this logic, and so their
 * results stay in lockstep with the canvas's own dimming, per A3. */
export function buildEventFilter(
  investigationScope: string,
  window: TimeWindow | null,
  selectedNodeIds: string[] | null,
): EventFilter {
  return {
    investigation_scope: investigationScope,
    window: window ? { valid_from: window.validFrom, valid_to: window.validTo } : null,
    node_ids: selectedNodeIds ?? [],
    edge_types: [],
  };
}

export interface CrossFilterStore {
  store: StoreApi<CrossFilterStoreState>;
  /** Recomputes `dimmedNodeIds` against the current filter inputs and the
   * working set's current node membership — call after `setWindow`/
   * `setSelectedNodeIds`/`clearFilter`, and again whenever the working
   * set's own membership changes (a node added after the last refresh has
   * no dimming state yet otherwise). Takes the id list rather than a
   * graph reference: this store has no graphology dependency, matching
   * `workingset/store.ts`'s own separation. */
  refresh: (allNodeIds: readonly string[]) => Promise<void>;
}

export function createCrossFilterStore(
  apiBaseUrl: string,
  bearerToken: string,
  investigationScope: string,
): CrossFilterStore {
  const store = createStore<CrossFilterStoreState>((set) => ({
    window: null,
    selectedNodeIds: null,
    dimmedNodeIds: new Set(),
    dimmedCount: 0,
    setWindow: (window) => set({ window }),
    setSelectedNodeIds: (selectedNodeIds) => set({ selectedNodeIds }),
    clearFilter: () =>
      set({ window: null, selectedNodeIds: null, dimmedNodeIds: new Set(), dimmedCount: 0 }),
  }));

  async function refresh(allNodeIds: readonly string[]): Promise<void> {
    const state = store.getState();
    if (state.window === null && state.selectedNodeIds === null) {
      store.setState({ dimmedNodeIds: new Set(), dimmedCount: 0 });
      return;
    }
    const filter = buildEventFilter(investigationScope, state.window, state.selectedNodeIds);
    const result = await fetchCrossFilter(apiBaseUrl, bearerToken, {
      filter,
      dimensions: [
        { name: "source_id", bucketing: "categorical", field: "source_id" },
        { name: "target_id", bucketing: "categorical", field: "target_id" },
      ],
    });
    const surviving = new Set<string>();
    for (const bucket of result.source_id?.buckets ?? []) {
      if (bucket.label) surviving.add(bucket.label);
    }
    for (const bucket of result.target_id?.buckets ?? []) {
      if (bucket.label) surviving.add(bucket.label);
    }
    const dimmed = new Set(allNodeIds.filter((id) => !surviving.has(id)));
    store.setState({ dimmedNodeIds: dimmed, dimmedCount: dimmed.size });
  }

  return { store, refresh };
}
