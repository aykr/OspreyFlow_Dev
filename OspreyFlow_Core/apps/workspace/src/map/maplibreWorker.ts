// Where MapLibre's worker is served from (ADR-014 Amendment 2).
//
// `maplibre-gl` 6.x runs its tile parsing in a module worker and, left alone, looks for
// `maplibre-gl-worker.mjs` beside the module that loads it. A Vite production build does not emit
// that file, so the default points at `/assets/maplibre-gl-worker.mjs`, which does not exist: the map
// mounts and draws nothing (MapLibre's v5-to-v6 migration guide: every bundler needs a one-time
// `setWorkerUrl`). The `?url` import makes Vite emit the file and give its address, so the Glass
// serves the worker itself, from its own origin (a strict policy needs `worker-src 'self'` and no
// `blob:`). `keyboard/map-tiles.spec.ts` shows it under a production bundle.
import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

let set = false;

/** Points MapLibre at the worker file the build emits. Once is enough; it must come before a map is made. */
export function selfHostMaplibreWorker(): void {
  if (set) return;
  setWorkerUrl(workerUrl);
  set = true;
}
