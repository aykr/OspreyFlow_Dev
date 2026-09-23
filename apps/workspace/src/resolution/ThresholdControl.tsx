// The resolution-threshold control — `08_ACCEPTANCE_SCENARIOS.md` B9: "a global,
// session-level control... move the resolution threshold from Strict to Balanced."
//
// A native `<input type="range">` (via the `Slider` primitive), not a canvas action — it lives
// outside `GlassCanvas`'s own keydown trap and needs no `keyboard.spec.ts` case of its own
// (`CLAUDE.md` rule 13's own "or its equivalent for a new surface": a native range input is
// keyboard-operable by browser default, with no custom key handling whose correctness a scripted
// walkthrough would need to prove — unlike the canvas's own hand-rolled `onKeyDown`).
import { useEffect, useState } from "react";
import type { StoreApi } from "zustand/vanilla";

import { Slider } from "../design/primitives/Slider";
import type { WorkingSetStoreState } from "../workingset/store";

// `services/resolve/projection.py`'s three named constants, checked directly rather than assumed
// — B9's own wording names exactly these three, not a continuous scale, so the slider exposes
// exactly three stops and nothing between them.
const DETENTS = [
  { label: "Strict", value: 0.99 },
  { label: "Balanced", value: 0.95 },
  { label: "Broad", value: 0.8 },
] as const;

function detentIndexFor(value: number): number {
  return DETENTS.findIndex((d) => d.value === value);
}

export interface ResolutionThresholdControlProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  store: StoreApi<WorkingSetStoreState>;
  /** Bubbles the change summary up to the App-level Toast slot — `merged`/`split`/`affected` are
   * `DeltaReproject`'s own counts, the same ones the picture (cluster co-location/border, in
   * `GlassCanvas`) is driven from, so the number and the picture agree by construction: both read
   * off the one delta this control's own `PUT` response returns. */
  onChangeSummary?: (message: string) => void;
}

export function ResolutionThresholdControl({
  apiBaseUrl,
  bearerToken,
  investigationId,
  store,
  onChangeSummary,
}: ResolutionThresholdControlProps) {
  const [threshold, setThreshold] = useState<number | null>(null);
  // The thumb's own live position while dragging, committed only on release (`Slider`'s
  // `onCommit`) — `PUT .../resolution/threshold` re-projects the whole working set, up to the
  // 50k cap, so firing it on every intermediate `onChange` value during a drag would mean one
  // reprojection per pixel of drag rather than one per gesture.
  const [pendingIndex, setPendingIndex] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetch(`${apiBaseUrl}/v1/investigations/${investigationId}/resolution/threshold`, {
      headers: { Authorization: `Bearer ${bearerToken}` },
    })
      .then((r) => r.json())
      .then((body: { threshold: number }) => {
        if (!cancelled) setThreshold(body.threshold);
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);

  if (threshold === null) return null;

  const currentIndex = detentIndexFor(threshold);
  // A session already sitting at a value none of the three constants name (reachable only by
  // calling the endpoint directly, bypassing this control) shows as "Custom" rather than snapping
  // its label to the nearest detent — the thumb still needs *some* position, so it defaults to the
  // middle stop, but moving it at all always commits one of the three exact named constants, never
  // an interpolated value.
  const sliderIndex = pendingIndex ?? (currentIndex === -1 ? 1 : currentIndex);
  const currentDetent = DETENTS[currentIndex];
  const label = currentDetent ? currentDetent.label : `Custom (${threshold.toFixed(2)})`;

  async function commit(index: number): Promise<void> {
    setPendingIndex(null);
    const detent = DETENTS[index];
    if (!detent) return;
    const response = await fetch(
      `${apiBaseUrl}/v1/investigations/${investigationId}/resolution/threshold`,
      {
        method: "PUT",
        headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ threshold: detent.value }),
      },
    );
    if (!response.ok) return; // surfaces via a future notice/Toast at the App layer, same as GlassCanvas's own fetches
    const delta = await response.json();
    store.getState().applyDelta(delta);
    setThreshold(detent.value);
    onChangeSummary?.(
      `Resolution threshold: ${detent.label} — ${delta.merged} merged, ${delta.split} split, ${delta.affected} affected`,
    );
  }

  return (
    <div className="resolution-threshold-control">
      <span className="resolution-threshold-control__label">{label}</span>
      <Slider
        min={0}
        max={DETENTS.length - 1}
        step={1}
        value={sliderIndex}
        onChange={setPendingIndex}
        onCommit={(index) => void commit(index)}
        aria-label="Resolution threshold"
      />
    </div>
  );
}
