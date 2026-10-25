import { useEffect, useRef, useState } from "react";
import { useStore } from "zustand/react";
import type { StoreApi } from "zustand/vanilla";

import type { WorkingSetDelta } from "./models";
import type { WorkingSetStoreState } from "./store";
import { ViewOverCapDialog } from "./ViewOverCapDialog";

export interface ViewOverCapGateProps {
  store: StoreApi<WorkingSetStoreState>;
  /** "Try again": a resync with no last sequence, on the live delta client. */
  requestResync: (lastAcknowledgedSeq: null) => void;
  /** The ontology's entity types, never the case's contents. */
  entityTypes: readonly string[];
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** A filtered branch was made: open it, as a branch is opened. */
  onBranchOpened: (id: string, name: string) => void;
  fetcher?: typeof fetch;
}

/**
 * The one place the over-cap dialog is shown, put away and brought back (ADR-124 decision 2,
 * Amendment 9), joined to the working-set store. `App.tsx` and the keyboard harness both render
 * this, so what `keyboard/view-over-cap.spec.ts` exercises is what the Glass runs. While the store
 * holds the reader's own figure the dialog shows; Escape puts it away behind a button, which takes
 * focus and brings it back; a new figure shows it again; the next snapshot, or a change of case,
 * clears it (`store.ts`). It renders in every view of the open case: the over-cap state is the
 * case's, not the graph's.
 */
export function ViewOverCapGate({
  store,
  requestResync,
  entityTypes,
  apiBaseUrl,
  bearerToken,
  investigationId,
  onBranchOpened,
  fetcher,
}: ViewOverCapGateProps) {
  const viewOverCap = useStore(store, (s) => s.viewOverCap);
  const [dismissed, setDismissed] = useState(false);
  const reopenRef = useRef<HTMLButtonElement>(null);
  useEffect(() => setDismissed(false), [viewOverCap]);
  useEffect(() => {
    if (dismissed) reopenRef.current?.focus();
  }, [dismissed]);

  if (viewOverCap === null) return null;
  if (dismissed) {
    return (
      <button
        type="button"
        className="btn view-over-cap__reopen"
        ref={reopenRef}
        onClick={() => setDismissed(false)}
      >
        Your view of this case is too large. Choose what to do
      </button>
    );
  }
  return (
    <ViewOverCapDialog
      wouldBe={viewOverCap}
      entityTypes={entityTypes}
      apiBaseUrl={apiBaseUrl}
      bearerToken={bearerToken}
      investigationId={investigationId}
      onTryAgain={() => requestResync(null)}
      onBranchOpened={onBranchOpened}
      onClose={() => setDismissed(true)}
      fetcher={fetcher}
    />
  );
}

/**
 * Applies a snapshot that did not arrive on the socket (a restore's HTTP answer). The store clears
 * the over-cap state on any snapshot, but the server's socket is still stuck from the
 * `view_over_cap` it sent: so when this clears one, the live client is asked to resync with no
 * last sequence, which counts the view again and either frees the socket or shows the dialog.
 */
export function applyRestoredSnapshot(
  store: StoreApi<WorkingSetStoreState>,
  requestResync: (lastAcknowledgedSeq: null) => void,
  snapshot: WorkingSetDelta,
): void {
  const wasOverCap = store.getState().viewOverCap !== null;
  store.getState().applyDelta(snapshot);
  if (wasOverCap) requestResync(null);
}
