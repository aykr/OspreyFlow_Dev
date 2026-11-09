// The canvas's alert badge (ADR-146 decision 9): a small mark on an item with an open alert, so the
// Glass shows alerts where people already look. Drawn from the case's queue as the Conduit gives it
// to this reader (an alert whose evidence they may not see is not in it, rule 3), so a badge marks
// only what they could open anyway; a reader refused the queue's rows sees no badge. The canvas mounts
// `AlertBadgeOverlay` (case lane's `GlassCanvas.tsx`, `process/lanes/rules-b/canvas-badge.patch`).
import { useEffect, useState, type RefObject } from "react";
import type Sigma from "sigma";

import type { QueuedAlert } from "../../../../packages/schemas/generated";
import { NodeBadgeOverlay, type NodeBadge } from "../canvas/JudgementBadgeOverlay";
import type { WorkingSetEdgeAttributes, WorkingSetNodeAttributes } from "../workingset/store";
import { fetchNewestAlerts, type ReportsApi } from "./api";

const STILL_OPEN = new Set(["open", "claimed", "closing"]);

/** Each item an open alert concerns, with how many open alerts concern it. */
export function alertBadges(rows: readonly QueuedAlert[]): Map<string, NodeBadge> {
  const counts = new Map<string, number>();
  for (const { alert } of rows) {
    if (!STILL_OPEN.has(alert.status ?? "open")) continue;
    for (const id of new Set(alert.referent_node_ids ?? [])) counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  return new Map(
    [...counts].map(([id, n]) => [id, { text: n === 1 ? "!" : `!${n}`, label: n === 1 ? "1 open alert" : `${n} open alerts` }]),
  );
}

/** The badges for the open case, read when it opens and whenever `readAgain` changes. */
export function useAlertBadges(api: ReportsApi | null, readAgain = 0): Map<string, NodeBadge> {
  const [badges, setBadges] = useState<Map<string, NodeBadge>>(new Map());
  useEffect(() => {
    if (!api) return;
    let live = true;
    fetchNewestAlerts(api, Number.MAX_SAFE_INTEGER)
      .then((rows) => live && setBadges(rows ? alertBadges(rows) : new Map()))
      .catch(() => live && setBadges(new Map()));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api?.apiBaseUrl, api?.bearerToken, api?.investigationId, readAgain]);
  return badges;
}

export function AlertBadgeOverlay(props: {
  sigmaRef: RefObject<Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | null>;
  badges: ReadonlyMap<string, NodeBadge>;
  positionOf: (nodeId: string) => { x: number; y: number } | null;
}) {
  // Below and to the left of the node, where the judgements' badge (above right) and a route's degree
  // mark do not sit.
  return <NodeBadgeOverlay {...props} offset={{ x: -18, y: 6 }} />;
}
