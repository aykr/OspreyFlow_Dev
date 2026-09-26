import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `HARNESS_API_PORT` — `05_DEPLOYMENT.md` §2's own bootstrap command names port 7000 as this
// app's real default, kept as the default here too; overridable because `keyboard/playwright.
// config.ts` needs a different one. **Found needing this, not anticipated:** port 7000 is macOS's
// own AirPlay Receiver / ControlCenter service (registered as `afs3-fileserver`) on a real
// development machine — `reuseExistingServer` silently treated that already-listening port as
// this app's own server, and every proxied request got ControlCenter's own 403 refusal instead of
// a connection error, which is what first surfaced this. Only the keyboard suite's own scratch
// server needs to move; the real app keeps 7000.
const API_PORT = process.env.HARNESS_API_PORT ?? "7000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5190,
    proxy: {
      // `npm run dev`'s own convenience: `python -m harness` (no subcommand) serves both the API
      // and this app's own built `dist/` from one origin in a real deployment
      // (`harness/webapp.py`'s own `create_app`); during development the two run as separate
      // processes on separate ports, so requests to `/api` and `/admin` are proxied to the real
      // Python server rather than duplicated as a dev-only mock.
      "/api": `http://127.0.0.1:${API_PORT}`,
      "/admin": `http://127.0.0.1:${API_PORT}`,
    },
  },
});
