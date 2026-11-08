// Admin › Maps' keyboard and accessibility harness (ADR-147; `CLAUDE.md` rule 13). The Conduit is
// stood in for by an in-memory answerer that records every request (`window.mapsAsked`), so
// `admin-maps.spec.ts` proves each action reached its route, and the every-harness axe scan sees a
// populated screen. Synthetic (rule 9): no real key, no real provider, no tile fetched; every
// address is a `.test` name. `?open=add`, `?open=key` and `?open=area` draw the forms open;
// `?built=1` the basemap built, the glyphs installed and an area run.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import "../src/admin/admin.css";
import { Maps } from "../src/admin/sections/Maps";
import { applyHarnessBrand } from "./brandHarness";

await applyHarnessBrand();

const params = new URLSearchParams(location.search);
const built = Boolean(params.get("built"));
type Row = Record<string, unknown> & { provider: Record<string, unknown> & { id: string; label: string } };
const open = { id: "ODbL-1.0", redistributable: true, client_scope: "open", note: null };
const providers: Row[] = [
  { provider: { id: "osm-local", label: "OpenStreetMap", kind: "vector", source: "file:///data/tiles/built/rutland.pmtiles",
                proxy: "none", style: "bundled:osprey-dark", attribution: "© OpenStreetMap contributors", licence: open, variables: {} },
    tier: 1, key_state: "none", needs_key: false, key_set_at: null, key_set_by: null,
    state: built ? "Ready: a local file on this deployment." : "Its local file is not built yet.", ready: built },
  { provider: { id: "hosted", label: "Hosted tiles", kind: "raster", source: "https://tiles.example.test/{z}/{x}/{y}.png?key={credential}",
                proxy: "required", cache: { ttl_days: 30, prefetch_areas: [] }, attribution: "Example tiles",
                licence: { id: "example", redistributable: false, client_scope: "per-deployment", note: "Not to be passed on." }, variables: {} },
    tier: 3, key_state: "set", needs_key: true, key_set_at: "2026-11-08T09:00:00Z", key_set_by: "admin-1",
    state: "Ready: fetched through the Conduit and cached.", ready: true },
  { provider: { id: "corporate", label: "Corporate aerial", kind: "raster", service: "wmts", endpoint: "https://gis.example.test/wmts",
                layer: "aerial", tile_matrix_set: "GoogleMapsCompatible", format: "image/png", wmts_style: "default",
                credential_param: "apikey", proxy: "required", attribution: "Corporate GIS",
                licence: { id: "internal", redistributable: false, client_scope: "per-deployment", note: null }, variables: {} },
    tier: 4, key_state: "none", needs_key: true, key_set_at: null, key_set_by: null, state: "Needs a key: none is set.", ready: false },
];  // prettier-ignore
let mapDefault = "osm-local";
let areas: Record<string, unknown>[] = [
  { name: "Area of operations", provider_id: "hosted", west: -1.3, south: 51.7, east: -1.2, north: 51.8, zoom_min: 10, zoom_max: 12 },
];
let schedule: { every_hours: number | null } = { every_hours: 24 };
const history = [{ at: "2026-11-08T09:00:00Z", by: "admin-1", action: "key_set", provider: "hosted", changes: {}, outcome: "done" }];
const asked: string[] = [];
(window as unknown as { mapsAsked: string[] }).mapsAsked = asked;

const view = () => ({
  default: mapDefault,
  providers,
  changed_in_admin: true,
  basemap: {
    basemaps: [{ provider_id: "osm-local", file: "rutland.pmtiles", built, size_bytes: built ? 2_100_000 : null,
                 built_at: built ? "2026-11-08T08:00:00Z" : null }],
    glyphs_installed: built, glyph_fonts: ["Noto Sans Regular"], builder_ready: true,
    builder_state: "Ready: Java and the map builder are installed.", regions: ["great-britain", "rutland"],
  },  // prettier-ignore
  areas: areas.map((area) => ({
    area, tiles: 21,
    last_run: built ? { area: area.name, provider_id: area.provider_id, at: "2026-11-08T07:00:00Z", tiles_fetched: 21, tiles_already_cached: 0, failed: null } : null,
  })),  // prettier-ignore
  schedule,
  next_run_at: schedule.every_hours ? "2026-11-09T07:00:00Z" : null,
});

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = new URL(String(input));
  const path = url.pathname;
  const method = init?.method ?? "GET";
  asked.push(`${method} ${path}`);
  const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
  const reply = (status: number, value: unknown) => new Response(JSON.stringify(value), { status });
  if (path === "/v1/admin/maps/history") return reply(200, { entries: history });
  if (path === "/v1/admin/maps" && method === "GET") return reply(200, view());
  if (path === "/v1/admin/geospatial/build-basemap") {
    const stream =
      `data: ${JSON.stringify({ line: `Downloading the '${String(body.region)}' Geofabrik extract...` })}\n\n` +
      `data: ${JSON.stringify({ line: "Running planetiler..." })}\n\n` +
      `event: complete\ndata: ${JSON.stringify({ returncode: 0, result: { pmtiles_file: `${String(body.region)}.pmtiles` } })}\n\n`;
    return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
  }
  if (path === "/v1/admin/geospatial/verify") return reply(200, { passed: true, issues: [] });
  if (path === "/v1/admin/maps/prefetch") {
    return reply(200, areas.map((a) => ({ area: a.name, provider_id: a.provider_id, at: "2026-11-08T11:00:00Z", tiles_fetched: 21, tiles_already_cached: 0, failed: null })));
  }
  if (path === "/v1/admin/maps/areas") {
    areas = body.areas as Record<string, unknown>[];
    return reply(200, view());
  }
  if (path === "/v1/admin/maps/schedule") {
    schedule = body.schedule as typeof schedule;
    return reply(200, view());
  }
  if (path === "/v1/admin/maps/default") {
    mapDefault = String(body.default);
    return reply(200, view());
  }
  if (path === "/v1/admin/maps/providers" && method === "POST") {
    const provider = body.provider as Row["provider"];
    providers.push({ provider, tier: 3, key_state: "none", needs_key: false, key_set_at: null, key_set_by: null, state: "Ready: fetched through the Conduit.", ready: true });
    return reply(200, view());
  }
  const match = /^\/v1\/admin\/maps\/providers\/([^/]+)(\/key)?$/.exec(path);
  const row = match ? providers.find((r) => r.provider.id === decodeURIComponent(match[1])) : undefined;
  if (!match || !row) return reply(404, { detail: { detail: "There is no map provider of that name." } });
  if (match[2] === "/key") {
    // The key is never kept here either: only that one was sent.
    if (method === "PUT") Object.assign(row, { key_state: "set", key_set_at: "2026-11-08T10:00:00Z", key_set_by: "admin-1", ready: true, state: "Ready: fetched through the Conduit." });
    else Object.assign(row, { key_state: "none", key_set_at: null, key_set_by: null });
    return reply(200, view());
  }
  if (method === "PUT") row.provider = body.provider as Row["provider"];
  if (method === "DELETE") providers.splice(providers.indexOf(row), 1);
  return reply(200, view());
};

createRoot(document.getElementById("root")!).render(
  <section className="admin-section" aria-label="Maps">
    <h2>Maps</h2>
    <Maps api={{ apiBaseUrl: "http://keyboard-test.invalid", bearerToken: "unused" }} />
  </section>,
);

const opened = params.get("open");
if (opened) {
  const name = opened === "add" ? "Add a provider" : opened === "area" ? "Add a prefetch area" : "Enter key for Corporate aerial";
  for (let i = 0; i < 40; i++) {
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.getAttribute("aria-label") === name);
    if (button) {
      button.click();
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}
