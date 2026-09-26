import { defineConfig } from "@playwright/test";

// **The live tier for the Glass** — specs here drive a real Vite-served Glass against a real
// Conduit, a real ArcadeDB/DuckDB and real seeded fixtures, which is exactly what
// `apps/workspace/map-verify/`, `a11y/`, `keyboard/` and `perf/` all deliberately do not do:
// each of those runs against a static showcase page or a mocked API, so none of them can prove
// anything about a running deployment.
//
// That distinction is the reason this directory exists. Round 12's brief asked for the Glass's
// Map view to be proven to render tiles from a real PMTiles build "by the existing `make
// glass-map-verify` target against the real stack" — but `glass-map-verify` is a
// `toHaveScreenshot()` comparison against `map-verify/showcase.tsx`, a static page with no
// Conduit, no PMTiles and no MapLibre tile fetch in it at all. It could not have proven this
// whatever it was pointed at; a new live spec was needed, not a re-run of that one.
//
// **Opt-in, and skipped by default** (`OSPREY_TEST_LIVE_GLASS=1`), the same gate
// `tests/harness/test_six_screen_live_exit.py` and `test_sustained_load.py` already use: these
// need a stack somebody brought up by hand (`docs/DEMO_GUIDE.md` §3) and cannot run in CI.
// The three environment variables below are that stack's own coordinates and have no defaults —
// a spec here that silently ran against the wrong Conduit would be worse than one that did not
// run, so `live.ts` fails loudly when any is missing.
export default defineConfig({
  testDir: ".",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  // One worker: every spec here drives the same single seeded investigation on the same single
  // Conduit, and two of them moving the resolution threshold at once would each see the other's
  // writes. Serial is correctness here, not caution.
  workers: 1,
  fullyParallel: false,
  // **Port 5173, and it has to be 5173** — not an arbitrary free port like the other Playwright
  // projects here use. The Conduit's own CORS allowlist is `CORS_ALLOWED_ORIGINS`, defaulting to
  // `http://localhost:5173` (`services/api/app.py`), so a Glass served from any other port has
  // every request refused at the browser's preflight: the Conduit answers `OPTIONS` with 400 and
  // the app sits on "Loading…" forever, with nothing in its own logs that names CORS as the
  // cause. Found exactly that way, running this spec on 5186 first.
  //
  // Using the demo's own port is the better answer regardless of the bug: `DEMO_GUIDE.md` §3.6
  // tells a presenter to open `localhost:5173`, and these specs exist to assert what that
  // presenter will see, so they should be driving that same URL rather than a parallel one.
  webServer: {
    command: "npx vite --port 5173 --strictPort",
    port: 5173,
    reuseExistingServer: !process.env.CI,
    cwd: "..",
    env: {
      VITE_API_BASE_URL: process.env.OSPREY_LIVE_API_BASE_URL ?? "",
      VITE_DEV_BEARER_TOKEN: process.env.OSPREY_LIVE_BEARER_TOKEN ?? "",
    },
  },
  use: {
    baseURL: "http://localhost:5173",
    // `localhost`, never `127.0.0.1` — `DEMO_GUIDE.md` §3's own opening note records that the
    // Vite dev server on the machine this was rehearsed on resolved `localhost` to `::1` only,
    // so `127.0.0.1:5186` did not connect at all. The same note applies to a spec.
    trace: "retain-on-failure",
  },
});
