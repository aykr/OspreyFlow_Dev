// @vitest-environment jsdom
// Admin › Maps (ADR-147): a provider's key field is write-only — never filled, cleared once sent,
// the key never on the page afterwards, even when the Conduit refuses — each provider shows its
// tier, attribution and state, and the build's streamed lines and a prefetch run are shown in the
// Conduit's words.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Maps } from "./Maps";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PLANTED = "k-PLANTED-glass-map-key-H6J2";
const LICENCE_OPEN = { id: "ODbL-1.0", redistributable: true, client_scope: "open", note: null };
const OSM = { id: "osm-local", label: "OpenStreetMap", kind: "vector", source: "file:///data/tiles/gb.pmtiles",
              proxy: "none", style: "bundled:osprey-dark", attribution: "© OpenStreetMap contributors",
              licence: LICENCE_OPEN, variables: {} };  // prettier-ignore
const HOSTED = { id: "hosted", label: "Hosted tiles", kind: "raster",
                 source: "https://tiles.example.test/{z}/{x}/{y}.png?key={credential}", proxy: "required",
                 cache: { ttl_days: 30, prefetch_areas: [] }, attribution: "Example",
                 licence: { id: "example", redistributable: false, client_scope: "per-deployment", note: null },
                 variables: {} };  // prettier-ignore
const row = (provider: object, tier: number, extra: object = {}) => ({
  provider, tier, key_state: "none", needs_key: false, key_set_at: null, key_set_by: null,
  state: "Ready: a local file on this deployment.", ready: true, ...extra,
});  // prettier-ignore
const VIEW = {
  default: "osm-local",
  providers: [row(OSM, 1), row(HOSTED, 3, { needs_key: true, state: "Needs a key: none is set.", ready: false })],
  changed_in_admin: false,
  basemap: {
    basemaps: [{ provider_id: "osm-local", file: "gb.pmtiles", built: false, size_bytes: null, built_at: null }],
    glyphs_installed: false, glyph_fonts: ["Noto Sans Regular"], builder_ready: true,
    builder_state: "Ready: Java and the map builder are installed.", regions: ["great-britain", "rutland"],
  },  // prettier-ignore
  areas: [],
  schedule: { every_hours: null },
  next_run_at: null,
};
const SET = { ...VIEW, providers: [VIEW.providers[0], { ...VIEW.providers[1], key_state: "set", key_set_at: "2026-11-08T10:00:00Z", key_set_by: "admin-1", ready: true }] };

type Answer = { status: number; body?: unknown; text?: string };

function stub(answers: (path: string, init?: RequestInit) => Answer | undefined) {
  const sent: { path: string; method: string; body: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname;
      sent.push({ path, method: init?.method ?? "GET", body: String(init?.body ?? "") });
      const answer =
        answers(path, init) ?? (path === "/v1/admin/maps/history" ? { status: 200, body: { entries: [] } } : { status: 200, body: VIEW });
      return {
        ok: answer.status < 400,
        status: answer.status,
        json: async () => answer.body,
        text: async () => answer.text ?? JSON.stringify(answer.body),
      } as Response;
    }),
  );
  return sent;
}

const API = { apiBaseUrl: "http://api", bearerToken: "t" };

describe("Maps", () => {
  it("heads its parts with h2s beneath Admin's h1, sized as People's (ADR-145 Amendment 16)", async () => {
    stub(() => undefined);
    const { container } = render(<Maps api={API} />);
    await screen.findByRole("heading", { name: "Providers" });
    const headings = [...container.querySelectorAll("h1, h2, h3, h4, h5, h6")];
    expect(headings.map((h) => h.tagName)).toEqual(headings.map(() => "H2"));
    expect(headings.length).toBeGreaterThan(2);
    expect(headings.every((h) => h.classList.contains("value"))).toBe(true);
  });

  it("shows each provider's tier, attribution and state", async () => {
    stub(() => undefined);
    render(<Maps api={API} />);
    const table = await screen.findByRole("table", { name: "Map providers" });
    expect(table.textContent).toContain("Tier 1: OpenStreetMap, built here");
    expect(table.textContent).toContain("© OpenStreetMap contributors");
    expect(table.textContent).toContain("Tier 3: hosted, through the Conduit");
    expect(table.textContent).toContain("Needs a key: none is set.");
    expect(table.textContent).toContain("No key needed");
    expect(screen.getByText(/Not installed: the map is drawn without names/)).toBeTruthy();
  });

  it("sends the key once, clears the field, and never shows it again", async () => {
    const sent = stub((path, init) =>
      path === "/v1/admin/maps/providers/hosted/key" && init?.method === "PUT" ? { status: 200, body: SET } : undefined,
    );
    render(<Maps api={API} />);
    fireEvent.click(await screen.findByRole("button", { name: "Enter key for Hosted tiles" }));
    const field = screen.getByLabelText(/Key for Hosted tiles/) as HTMLInputElement;
    expect(field.type).toBe("password");
    expect(field.getAttribute("autocomplete")).toBe("off");
    fireEvent.change(field, { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Set the key" }));
    await screen.findByText(/the key is set/);
    const put = sent.find((s) => s.method === "PUT");
    expect(put?.body).toBe(JSON.stringify({ key: PLANTED }));
    expect(document.body.innerHTML).not.toContain(PLANTED);
    expect(screen.getByRole("table", { name: "Map providers" }).textContent).toContain("Key set");
  });

  it("shows the Conduit's refusal in its words and still never the key", async () => {
    stub((path, init) =>
      path === "/v1/admin/maps/providers/hosted/key" && init?.method === "PUT"
        ? { status: 409, body: { detail: { error: "map_admin_refused", detail: "This provider takes no key." } } }
        : undefined,
    );
    render(<Maps api={API} />);
    fireEvent.click(await screen.findByRole("button", { name: "Enter key for Hosted tiles" }));
    fireEvent.change(screen.getByLabelText(/Key for Hosted tiles/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Set the key" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This provider takes no key.");
    expect(document.body.innerHTML).not.toContain(PLANTED);
  });

  it("shows the build's streamed lines and the file it built", async () => {
    const stream =
      'data: {"line": "Downloading the \'rutland\' Geofabrik extract..."}\n\n' +
      'data: {"line": "Running planetiler..."}\n\n' +
      'event: complete\ndata: {"returncode": 0, "result": {"pmtiles_file": "rutland.pmtiles"}}\n\n';
    const sent = stub((path) => (path === "/v1/admin/geospatial/build-basemap" ? { status: 200, text: stream } : undefined));
    render(<Maps api={API} />);
    fireEvent.change(await screen.findByLabelText("Region to build"), { target: { value: "rutland" } });
    fireEvent.click(screen.getByRole("button", { name: "Build the basemap" }));
    const status = await screen.findByRole("status");
    await waitFor(() => expect(status.textContent).toContain("Built rutland.pmtiles."));
    expect(status.textContent).toContain("Running planetiler...");
    expect(sent.find((s) => s.path === "/v1/admin/geospatial/build-basemap")?.body).toBe(JSON.stringify({ region: "rutland" }));
  });

  it("sends the unit the place names are held by, and says a refused one in the Conduit's words", async () => {
    // ADR-147 Amendment 2 (the owner's ruling 8).
    const words = "No case or dataset in this deployment is held by the unit 'unit-9', so a gazetteer cannot be built for it.";
    const sent = stub((path) =>
      path === "/v1/admin/geospatial/build-basemap" ? { status: 422, body: { detail: words } } : undefined,
    );
    render(<Maps api={API} />);
    fireEvent.change(await screen.findByLabelText(/Unit the place names are held by/), { target: { value: " unit-9 " } });
    fireEvent.click(screen.getByRole("button", { name: "Build the basemap" }));
    expect((await screen.findByRole("alert")).textContent).toContain(words);
    expect(sent.find((s) => s.path === "/v1/admin/geospatial/build-basemap")?.body).toBe(
      JSON.stringify({ region: "rutland", unit: "unit-9" }),
    );
  });

  it("says a build that did not finish in the Conduit's words", async () => {
    const stream = 'event: complete\ndata: {"returncode": 1, "error": "planetiler stopped"}\n\n';
    stub((path) => (path === "/v1/admin/geospatial/build-basemap" ? { status: 200, text: stream } : undefined));
    render(<Maps api={API} />);
    fireEvent.click(await screen.findByRole("button", { name: "Build the basemap" }));
    expect((await screen.findByRole("status")).textContent).toContain("The build did not finish: planetiler stopped");
  });

  it("adds a prefetch area for a provider the Conduit fetches and keeps", async () => {
    const sent = stub((path) => (path === "/v1/admin/maps/areas" ? { status: 200, body: VIEW } : undefined));
    render(<Maps api={API} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a prefetch area" }));
    const values: Record<string, string> = {
      "Area name": "Area of operations", "West (degrees of longitude)": "-1.3", "South (degrees of latitude)": "51.7",
      "East (degrees of longitude)": "-1.2", "North (degrees of latitude)": "51.8", "Lowest zoom": "10", "Highest zoom": "12",
    };  // prettier-ignore
    for (const [label, value] of Object.entries(values)) fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Add the area" }));
    await screen.findByText(/is added/);
    expect(JSON.parse(sent.find((s) => s.path === "/v1/admin/maps/areas")!.body)).toEqual({
      areas: [{ name: "Area of operations", provider_id: "hosted", west: -1.3, south: 51.7, east: -1.2, north: 51.8, zoom_min: 10, zoom_max: 12 }],
    });
  });
});
