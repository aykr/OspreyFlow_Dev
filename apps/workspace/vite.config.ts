import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `06_DECISIONS.md` ADR-050 — "the VITE_DEV_BEARER_TOKEN path survives only for `npm run dev`. A
// production build with it set fails the build." `mode` is `"production"` for a plain `vite build`
// and `"development"` for `vite dev`/`vite serve`; Vite does not otherwise gate `command` against
// this env var, so the fence has to be written here rather than left to `App.tsx`'s own runtime
// check, which a bundled production build would still ship (just unused) rather than refuse to
// produce at all. `CLAUDE.md` rule 15's planted violation is the real shape a regression would
// take: the variable present at `vite build` — an environment variable, not a source edit — which
// is exactly what `tests/harness/test_workspace_bundle.py` plants.
export default defineConfig(({ command }) => {
  if (command === "build" && process.env.VITE_DEV_BEARER_TOKEN) {
    throw new Error(
      "VITE_DEV_BEARER_TOKEN is set for a production build. That token path is a `npm run dev` " +
        "convenience only (06_DECISIONS.md ADR-050) — a rendered deployment must never carry it. " +
        "Unset it before building.",
    );
  }
  return {
    plugins: [react()],
    server: { port: 5173 },
  };
});
