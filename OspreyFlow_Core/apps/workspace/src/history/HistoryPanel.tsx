import { useEffect, useState } from "react";

import type { HistoryStepSummary, WorkingSetDelta } from "../workingset/models";
import { Drawer } from "../design/primitives/Drawer";
import { Table } from "../design/primitives/Table";

export interface HistoryPanelProps {
  open: boolean;
  onClose: () => void;
  investigationId: string;
  apiBaseUrl: string;
  bearerToken: string;
  onRestored: (snapshot: WorkingSetDelta) => void;
}

/** `spec/03_CONDUIT_MIDDLEWARE.md` §3.1's two routes, the client half —
 * "the history panel is a list of named steps, not a stack of arrows"
 * (`spec/02_GLASS_FRONTEND.md` §3.1). Restore applies through the same
 * `applyDelta` path a live snapshot does — there is no separate
 * client-side reconciliation for it. */
export function HistoryPanel({
  open,
  onClose,
  investigationId,
  apiBaseUrl,
  bearerToken,
  onRestored,
}: HistoryPanelProps) {
  const [steps, setSteps] = useState<HistoryStepSummary[]>([]);

  useEffect(() => {
    if (!open) return;
    void fetch(`${apiBaseUrl}/v1/investigations/${investigationId}/history`, {
      headers: { Authorization: `Bearer ${bearerToken}` },
    })
      // A refusal is an empty history: the error body set as the steps once threw on render.
      .then((r) => (r.ok ? (r.json() as Promise<unknown>) : []))
      .then((body) => setSteps(Array.isArray(body) ? (body as HistoryStepSummary[]) : []))
      .catch(() => setSteps([]));
  }, [open, investigationId, apiBaseUrl, bearerToken]);

  async function restore(stepId: string): Promise<void> {
    const response = await fetch(
      `${apiBaseUrl}/v1/investigations/${investigationId}/history/${stepId}`,
      { method: "POST", headers: { Authorization: `Bearer ${bearerToken}` } },
    );
    if (!response.ok) return;
    const snapshot = (await response.json()) as WorkingSetDelta;
    onRestored(snapshot);
    onClose();
  }

  return (
    <Drawer open={open} onClose={onClose} title="History">
      <Table
        columns={[
          { key: "label", header: "Step", render: (s: HistoryStepSummary) => s.label },
          {
            key: "counts",
            header: "Nodes / edges",
            render: (s: HistoryStepSummary) => `${s.node_count} / ${s.edge_count}`,
          },
          {
            key: "restore",
            header: "",
            render: (s: HistoryStepSummary) => (
              <button type="button" className="btn" onClick={() => void restore(s.id)}>
                Restore
              </button>
            ),
          },
        ]}
        rows={steps}
        getRowId={(s) => s.id}
      />
    </Drawer>
  );
}
