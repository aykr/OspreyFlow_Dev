// The drawn-boundary spatial filter — `spec/02_GLASS_FRONTEND.md` §3.5's
// "a drawn or selected boundary is a spatial filter like any other",
// Only the *drawn* half:
// rendering a real Boundary-Line-derived boundary as a selectable overlay
// needs a polygon-geometry storage capability that does not exist in
// `AnalyticsPort`/`GeometryRecord` yet (this checkpoint's own doc note) —
// deferred, not built here.
//
// **A bounded click-to-place-vertex flow, not a general polygon editor**
// — the same proportionate scope `site/SiteCalibrationWizard.tsx`'s own
// docstring claims for itself: no drag-to-reposition a vertex, no undo,
// no rubber-banding while the mouse moves between clicks. A real
// polygon-drawing library (`terra-draw` or similar) would supply that
// missing editing scaffolding; nothing in this repo has it today, and
// this component does not pretend to.
//
// **Scoped to the current working set.** The polygon test runs against
// `nodeCoordinates` — every working-set `Location` node's already-resolved
// coordinate (`map/geometries.ts`'s `resolveNodeCoordinates`, the same
// resolution `MapView`'s own `nodeCoordinates` prop already uses) — not
// every `Location` in the investigation. `00_ARCHITECTURE.md`'s own
// stated preference is a server-side spatial predicate for a
// investigation whose `Location` population is bigger than the working
// set; that is real, separate, deferred work, named here rather than
// silently promised.
import { useEffect, useRef, useState } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";

import type { CrossFilterStore } from "../crossfilter/store";
import { Button } from "../design/primitives/Button";
import { onNextMapClick } from "../site/siteLayer";
import { removeBoundaryDrawLayer, setBoundaryDrawLayer, type LngLat } from "./boundaryLayer";
import { pointInPolygon } from "./geometry";

export interface BoundaryFilterToolProps {
  map: MapLibreMap | null;
  crossFilterStore: CrossFilterStore;
  /** Every working-set node this tool can actually test — `App.tsx`'s own
   * `nodeCoordinates` state, the same map `MapView`'s own rendering
   * already reads. */
  nodeCoordinates: ReadonlyMap<string, { lat: number; lng: number }>;
  /** Called only when the filter is applied — never read reactively, the
   * same "call only when something changes" shape `Timeline.tsx`'s own
   * `getNodeIds` prop already uses. */
  getNodeIds: () => readonly string[];
  onClose: () => void;
}

export function BoundaryFilterTool({
  map,
  crossFilterStore,
  nodeCoordinates,
  getNodeIds,
  onClose,
}: BoundaryFilterToolProps) {
  const [points, setPoints] = useState<LngLat[]>([]);
  const cleanupRef = useRef<(() => void) | null>(null);

  // Draws the live preview and arms the next click in one place — every
  // placed point both updates the on-map preview and re-registers
  // `onNextMapClick` (a one-shot listener by design, so it needs
  // re-arming after each click, not just once at mount).
  useEffect(() => {
    if (!map) return;
    setBoundaryDrawLayer(map, points);
    cleanupRef.current = onNextMapClick(map, (lngLat) => {
      setPoints((prev) => [...prev, lngLat]);
    });
    return () => cleanupRef.current?.();
  }, [map, points]);

  useEffect(() => {
    if (!map) return;
    return () => removeBoundaryDrawLayer(map);
  }, [map]);

  function applyFilter() {
    const polygon = points.map((p) => ({ x: p.lng, y: p.lat }));
    const allNodeIds = getNodeIds();
    const inside = allNodeIds.filter((nodeId) => {
      const coord = nodeCoordinates.get(nodeId);
      return coord != null && pointInPolygon({ x: coord.lng, y: coord.lat }, polygon);
    });
    crossFilterStore.store.getState().setSelectedNodeIds(inside.length > 0 ? inside : null);
    void crossFilterStore.refresh(allNodeIds);
    onClose();
  }

  return (
    <div
      style={{
        position: "absolute",
        bottom: "var(--sp-8)",
        left: "var(--sp-8)",
        display: "flex",
        alignItems: "center",
        gap: "var(--sp-8)",
        background: "var(--surface-panel)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--r-panel)",
        padding: "var(--sp-8)",
        fontSize: "var(--fs-13)",
        color: "var(--text-secondary)",
      }}
    >
      <span>
        {points.length === 0
          ? "Click the map to start drawing a boundary."
          : `${points.length} point${points.length === 1 ? "" : "s"} placed.`}
      </span>
      <Button disabled={points.length < 3} onClick={applyFilter}>
        Close boundary
      </Button>
      <Button onClick={onClose}>Cancel</Button>
    </div>
  );
}
