// The strict-policy run's test page (slice GG5a), bundled by `mapServer.ts`'s own esbuild call. Never a product module: it is
// not in `apps/pages/modules/`, so `apps/pages/scripts/assets.mjs` never sees it and its drawing allowlist stays empty (ADR-152 decision 9).
//
// It does what a map page does and nothing more: names MapLibre's worker on the page's own origin before any map is made, as
// `apps/workspace/src/map/maplibreWorker.ts` does (`setWorkerUrl`, once); registers the `pmtiles://` protocol, as the
// workspace's Map view does; and makes one map with the product's option (`attributionControl: false`, `MapView.tsx`), plus
// `fadeDuration: 0` so the picture is read without waiting on fades. It has no `transformRequest` (the workspace's adds a
// bearer token to Conduit reads, which changes headers, not addresses or fetch kinds).
// The worker's and style's addresses come from the server, in `<meta>` tags, so a planted case changes the page's data and
// never its code.
import { Map as MapLibreMap, addProtocol, getVersion, setWorkerUrl } from "maplibre-gl";
import { Protocol } from "pmtiles";

interface MapState {
  version: string;
  loaded: boolean;
  idle: boolean;
  errors: string[];
}

declare global {
  interface Window {
    __MAP__?: MapLibreMap;
    __MAP_STATE__?: MapState;
  }
}

function meta(name: string): string {
  const value = document.querySelector(`meta[name="${name}"]`)?.getAttribute("content");
  if (!value) throw new Error(`the test page has no ${name}`);
  return value;
}

const state: MapState = { version: getVersion(), loaded: false, idle: false, errors: [] };
window.__MAP_STATE__ = state;

setWorkerUrl(meta("map-worker"));
const protocol = new Protocol();
addProtocol("pmtiles", protocol.tile);

const map = new MapLibreMap({ container: "map", style: meta("map-style"), attributionControl: false, fadeDuration: 0 });
window.__MAP__ = map;
map.on("load", () => {
  state.loaded = true;
});
map.on("idle", () => {
  state.idle = true;
});
map.on("error", (event: { error?: { message?: string } }) => {
  state.errors.push(String(event.error?.message ?? event.error ?? "unknown map error"));
});
