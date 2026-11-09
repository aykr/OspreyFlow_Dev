// The map's contrast floor, in each theme (`spec/00_ARCHITECTURE.md` §1.2.1's Verify: "renders a
// fixture graph over it and compares against a stored reference for contrast floor compliance";
// P4: the light and GOV.UK themes beside the dark one).
//
// Not a live MapLibre instance (no tiles in a test, rule 9): a static drawing of the colours the map
// really uses, each read from its own call site, never copied: the basemap's from the bundled style
// itself (`buildBundledDarkStyle`, its land, water, lines and place labels, built for this page's
// theme), the graph and trail drawn over it from `overlayColours` (what `MapView.tsx` passes sigma
// and MapLibre), and the analyst's controls (`MapControls.tsx`) as they are drawn over the map. A
// change to any of them that drops a pair under its floor fails `contrast.spec.ts`, which reads
// `window.__CONTRAST__`, and moves the picture it compares against.
//
// `?theme=light` draws the light theme; `?brand=govuk` the GOV.UK brand, which is light
// (`brandHarness.ts`). Nothing else: the dark theme is the default.
import { createRoot } from "react-dom/client";
import type { BackgroundLayerSpecification, FillLayerSpecification, LineLayerSpecification, SymbolLayerSpecification } from "maplibre-gl";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { activePalette } from "../src/color/palette";
import { contrastRatio as contrast } from "../src/map/contrast";
import { BasemapSwitch, PlaceSearch } from "../src/map/MapControls";
import { overlayColours } from "../src/map/overlayColours";
import { buildBundledDarkStyle } from "../src/map/style";
import { applyTheme } from "../src/theme/theme";
import type { PublicMapProvider } from "../../../packages/schemas/generated";
import { applyHarnessBrand } from "../keyboard/brandHarness";

declare global {
  interface Window {
    __CONTRAST__?: { pair: string; ratio: number; floor: number }[];
  }
}

const PROVIDER = {
  id: "osm-local",
  label: "OpenStreetMap",
  kind: "vector",
  style: "bundled:osprey-dark",
  attribution: "© OpenStreetMap contributors",
  licence_id: "ODbL-1.0",
  licence_note: null,
  client_scope: "open",
  source: "/v1/map/local-source/osm-local",
} as PublicMapProvider;
const HOSTED = { ...PROVIDER, id: "hosted", label: "Hosted streets", client_scope: "per-deployment", source: null } as PublicMapProvider;

function layer<T>(id: string, layers: readonly { id: string }[]): T {
  const found = layers.find((l) => l.id === id);
  if (!found) throw new Error(`the bundled style has no ${id} layer`);
  return found as T;
}

function Showcase() {
  const palette = activePalette();
  const style = buildBundledDarkStyle(PROVIDER, "", { labels: true, palette });
  const land = layer<BackgroundLayerSpecification>("background", style.layers).paint!["background-color"] as string;
  const water = layer<FillLayerSpecification>("water", style.layers).paint!["fill-color"] as string;
  const roads = layer<LineLayerSpecification>("transportation", style.layers).paint!["line-color"] as string;
  const placeLabel = layer<SymbolLayerSpecification>("place-label", style.layers).paint!["text-color"] as string;
  const overlay = overlayColours(palette);

  const nodes = [
    { x: 18, y: 22, label: "Yard 3" },
    { x: 46, y: 50, label: "Wing B" },
    { x: 70, y: 28, label: "Gate lodge" },
  ];
  return (
    <div style={{ width: "100vw", height: "100vh", position: "relative", background: land, overflow: "hidden" }}>
      <div style={{ position: "absolute", right: 0, top: 0, width: "34%", height: "100%", background: water }} />
      <div style={{ position: "absolute", left: 0, top: "64%", width: "66%", height: 2, background: roads }} />
      <span style={{ position: "absolute", left: "34%", top: "70%", color: placeLabel, fontSize: 13 }}>Cranford</span>
      <span style={{ position: "absolute", left: "72%", top: "70%", color: placeLabel, fontSize: 13 }}>Thames</span>
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <line x1="18" y1="22" x2="46" y2="50" stroke={overlay.link} strokeWidth="0.3" />
        <polyline points="50,85 60,80 72,82 84,74" fill="none" stroke={overlay.trail} strokeWidth="0.4" />
      </svg>
      <div style={{ position: "absolute", left: "calc(84% - 6px)", top: "calc(74% - 6px)", width: 12, height: 12, borderRadius: "50%", background: overlay.trailPoint }} />
      {nodes.map((n) => (
        <div key={n.label} style={{ position: "absolute", left: `${n.x}%`, top: `${n.y}%`, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
          <div style={{ width: 12, height: 12, borderRadius: "50%", background: overlay.marker }} />
          <span style={{ color: overlay.label, fontSize: 12 }}>{n.label}</span>
        </div>
      ))}
      <div className="map-controls">
        <BasemapSwitch providers={[PROVIDER, HOSTED]} chosen="osm-local" onChoose={() => undefined} />
        <PlaceSearch search={async () => ({ places: [], more: false })} onGo={() => undefined} />
      </div>
    </div>
  );
}

function measure(): void {
  const palette = activePalette();
  const style = buildBundledDarkStyle(PROVIDER, "", { labels: true, palette });
  const land = layer<BackgroundLayerSpecification>("background", style.layers).paint!["background-color"] as string;
  const water = layer<FillLayerSpecification>("water", style.layers).paint!["fill-color"] as string;
  const placeLabel = layer<SymbolLayerSpecification>("place-label", style.layers).paint!["text-color"] as string;
  const overlay = overlayColours(palette);
  // WCAG 1.4.3 (text, 4.5:1) and 1.4.11 (a graphic's parts needed to understand it, 3:1), over the
  // land and over the water, where either may be drawn.
  const pairs: { pair: string; ratio: number; floor: number }[] = [];
  for (const [ground, colour] of [["land", land], ["water", water]] as const) {
    pairs.push({ pair: `place label on ${ground}`, ratio: contrast(placeLabel, colour), floor: 4.5 });
    pairs.push({ pair: `node label on ${ground}`, ratio: contrast(overlay.label, colour), floor: 4.5 });
    pairs.push({ pair: `marker on ${ground}`, ratio: contrast(overlay.marker, colour), floor: 3 });
    pairs.push({ pair: `link on ${ground}`, ratio: contrast(overlay.link, colour), floor: 3 });
    pairs.push({ pair: `trail on ${ground}`, ratio: contrast(overlay.trail, colour), floor: 3 });
    pairs.push({ pair: `trail point on ${ground}`, ratio: contrast(overlay.trailPoint, colour), floor: 3 });
  }
  // The controls, as the page's own CSS draws them in this theme and brand.
  const panel = getComputedStyle(document.querySelector(".map-controls")!).backgroundColor;
  for (const [name, selector] of [
    ["the switch's legend", ".map-controls__legend"],
    ["a basemap's name", ".map-controls__choice"],
    ["the search's note", ".map-controls__note"],
  ] as const) {
    const text = getComputedStyle(document.querySelector(selector)!).color;
    pairs.push({ pair: `${name} on the controls' panel`, ratio: contrast(text, panel), floor: 4.5 });
  }
  window.__CONTRAST__ = pairs;
}

const params = new URLSearchParams(window.location.search);
void applyHarnessBrand().then(() => {
  if (params.get("theme") === "light") applyTheme("light");
  const container = document.getElementById("root");
  if (!container) throw new Error("#root not found");
  createRoot(container).render(<Showcase />);
  requestAnimationFrame(() => requestAnimationFrame(measure));
});
