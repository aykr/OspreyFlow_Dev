// Map contrast-floor showcase — `spec/00_ARCHITECTURE.md` §1.2.1's
// Verify: "renders a fixture graph over it and compares against a stored
// reference for contrast floor compliance." Not a live MapLibre/Sigma
// instance (the tier-1 PMTiles file doesn't exist yet, an already-
// documented gap — `map/style.ts`'s own module docstring) — a static
// render of the exact same colour constants `buildBundledDarkStyle`
// (basemap chrome) and `color/nodeVisual.ts` (fixture graph nodes) use,
// so a colour-token change that would break real contrast shows up here
// too, without needing a real running map to prove it.
//
// **Dark theme only.** The light MapLibre style is a stated follow-up,
// not yet built (`map/style.ts`'s own docstring) — there is no light-
// theme basemap chrome to render, so unlike `a11y/a11y.spec.ts`'s own
// dark+light loop, this showcase and `contrast.spec.ts` cover dark only,
// named as a gap rather than silently skipped.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import {
  CHANNEL_HEX,
  SURFACE_APP_DARK_HEX,
  SURFACE_RAISED_DARK_HEX,
  TEXT_PRIMARY_DARK_HEX,
} from "../src/color/tokens";

const FIXTURE_NODES = [
  { x: 15, y: 20, channel: CHANNEL_HEX.indigo, label: "Person" },
  { x: 45, y: 55, channel: CHANNEL_HEX.ochre, label: "Location" },
  { x: 70, y: 30, channel: CHANNEL_HEX.azure, label: "Organisation" },
  { x: 30, y: 75, channel: CHANNEL_HEX.cyan, label: "Endpoint" },
];

function Showcase() {
  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: SURFACE_APP_DARK_HEX,
        position: "relative",
      }}
    >
      {/* The basemap's own "landcover" fill, at the same opacity
          `buildBundledDarkStyle`'s layer declares. */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: SURFACE_RAISED_DARK_HEX,
          opacity: 0.5,
        }}
      />
      {FIXTURE_NODES.map((node) => (
        <div
          key={node.label}
          style={{
            position: "absolute",
            left: `${node.x}%`,
            top: `${node.y}%`,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "var(--sp-4)",
          }}
        >
          <div
            style={{
              width: 16,
              height: 16,
              borderRadius: "50%",
              background: node.channel,
            }}
          />
          <span style={{ color: TEXT_PRIMARY_DARK_HEX, fontSize: "var(--fs-11)" }}>
            {node.label}
          </span>
        </div>
      ))}
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Showcase />);
