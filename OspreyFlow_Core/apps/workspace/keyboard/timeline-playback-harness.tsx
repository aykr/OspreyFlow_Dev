// Timeline playback / cross-case-overlay keyboard harness — a new surface needing its own
// equivalent for a new surface": Stage 4f's own two new interactive controls (Play/Pause, the
// cross-case-overlay investigation input) are the seventh keyboard-driven surface
// (`keyboard/actionRegistry.ts`'s own `TIMELINE_PLAYBACK_ACTIONS` docstring has the full
// reasoning), so they get their own harness rather than folding into `keyboard.spec.ts`'s own
// canvas-focused suite.
//
// Mounts `Timeline` with the overlay id held one level up, exactly the way `App.tsx` itself does
// (the box for the id is behind the timeline's own `Overlay another case` button, since the
// declutter change of 3 October 2026), so a keyboard walkthrough proving "press the button, type an
// id, the second track loads" reaches what a real analyst would reach.
//
// A brush window is pre-seeded on the cross-filter store at mount — Play/Pause only render with an
// active window (`Timeline.tsx`'s own `{activeWindow && (...)}` guard), and setting one via the
// UI's own text inputs is already proven, unrelated ground (`keyboard.spec.ts` does not cover the
// timeline at all; this harness's own job is the two *new* controls, not re-proving the brush
// inputs are native and Tab-reachable, which needs no case per this file's own registry docstring).
//
// `POST /v1/analytics/histogram` is intercepted by `timeline-playback.spec.ts` via `page.route` —
// the same "real network call, mocked at the transport, not the component" shape every other
// keyboard spec in this directory already uses.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { createCrossFilterStore } from "../src/crossfilter/store";
import { Timeline } from "../src/timeline/Timeline";

declare global {
  interface Window {
    __TIMELINE_PLAYBACK_HARNESS__?: { fraction: number; window?: { validFrom: string; validTo: string | null } | null };
  }
}

window.__TIMELINE_PLAYBACK_HARNESS__ = { fraction: 0 };

const crossFilterStore = createCrossFilterStore(
  "http://keyboard-test.invalid",
  "unused",
  "inv-1",
);
// `?nowindow` starts with no window, for `timeline-brush.spec.ts`, which sets one by dragging.
if (!new URLSearchParams(window.location.search).has("nowindow")) {
  crossFilterStore.store.getState().setWindow({
    validFrom: "2026-01-01T00:00:00Z",
    validTo: "2026-01-05T00:00:00Z",
  });
}
crossFilterStore.store.subscribe((state) => {
  window.__TIMELINE_PLAYBACK_HARNESS__!.window = state.window;
});

function Harness() {
  const [crossCaseScope, setCrossCaseScope] = useState("");
  return (
    <div style={{ width: 700, height: 300 }}>
      <div style={{ height: 252 }}>
        <Timeline
          apiBaseUrl="http://keyboard-test.invalid"
          bearerToken="unused"
          investigationScope="inv-1"
          crossFilterStore={crossFilterStore}
          getNodeIds={() => []}
          crossCaseInvestigationScope={crossCaseScope || undefined}
          onCrossCaseScopeChange={setCrossCaseScope}
          onPlaybackFractionChange={(fraction) => {
            window.__TIMELINE_PLAYBACK_HARNESS__!.fraction = fraction;
          }}
        />
      </div>
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<Harness />);
