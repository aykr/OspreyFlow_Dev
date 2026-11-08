// Admin › Running › Maps (`06_DECISIONS.md` ADR-147): the basemap providers (tiers 1 to 4), each
// with its state and attribution, added and edited; a provider's key under ADR-135 Amendment 2's
// rule (typed into a write-only field, sent once and cleared; nothing the Conduit answers carries
// one); the local basemap's state, built and verified by the Conduit; the glyph fonts; prefetch
// areas run on a schedule. Behind `manage_geospatial`.
import { useEffect, useState, type FormEvent } from "react";

import type {
  AdminMapProvider,
  MapAdminEntry,
  MapsAdminView,
  PrefetchArea,
} from "../../../../../packages/schemas/generated";
import { Button, Checkbox, Input, Select } from "../../design/primitives";
import "./Maps.css";
import {
  addProvider,
  buildBasemap,
  editProvider,
  readMapHistory,
  readMaps,
  removeMapKey,
  removeProvider,
  runPrefetch,
  setAreas,
  setMapDefault,
  setMapKey,
  setSchedule,
  verifyMaps,
  type MapProvider,
  type MapsApi,
} from "./MapsApi";

const KEY_WORDS: Record<AdminMapProvider["key_state"], string> = {
  set: "Key set",
  env: "Key from the installer's settings",
  none: "No key",
};
const TIER_WORDS: Record<number, string> = {
  1: "Tier 1: OpenStreetMap, built here",
  2: "Tier 2: open data, a local file",
  3: "Tier 3: hosted, through the Conduit",
  4: "Tier 4: an OGC service",
};
const SCHEDULES = [
  { hours: 0, label: "By hand only" },
  { hours: 6, label: "Every 6 hours" },
  { hours: 24, label: "Every day" },
  { hours: 168, label: "Every week" },
];

function when(at: string | null | undefined): string {
  return at ? new Date(at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "";
}

function bytes(size: number | null | undefined): string {
  if (!size) return "";
  return size > 1e9 ? `${(size / 1e9).toFixed(1)} GB` : `${(size / 1e6).toFixed(1)} MB`;
}

interface Draft {
  id: string;
  label: string;
  kind: MapProvider["kind"];
  way: "address" | "wmts";
  address: string;
  layer: string;
  tile_matrix_set: string;
  format: string;
  wmts_style: string;
  credential_param: string;
  proxy: NonNullable<MapProvider["proxy"]>;
  cache_days: string;
  style: string;
  attribution: string;
  licence_id: string;
  redistributable: boolean;
  client_scope: MapProvider["licence"]["client_scope"];
  licence_note: string;
}

const EMPTY: Draft = {
  id: "", label: "", kind: "raster", way: "address", address: "", layer: "", tile_matrix_set: "",
  format: "image/png", wmts_style: "default", credential_param: "", proxy: "required", cache_days: "30",
  style: "", attribution: "", licence_id: "", redistributable: false, client_scope: "per-deployment",
  licence_note: "",
};  // prettier-ignore

function draftOf(p: MapProvider): Draft {
  return {
    id: p.id, label: p.label, kind: p.kind, way: p.service === "wmts" ? "wmts" : "address",
    address: (p.service === "wmts" ? p.endpoint : p.source) ?? "", layer: p.layer ?? "",
    tile_matrix_set: p.tile_matrix_set ?? "", format: p.format ?? "", wmts_style: p.wmts_style ?? "",
    credential_param: p.credential_param ?? "", proxy: p.proxy ?? "none",
    cache_days: p.cache ? String(p.cache.ttl_days) : "", style: p.style ?? "", attribution: p.attribution,
    licence_id: p.licence.id, redistributable: p.licence.redistributable, client_scope: p.licence.client_scope,
    licence_note: p.licence.note ?? "",
  };  // prettier-ignore
}

/** The provider a draft describes, keeping what the form does not show (a profile, its variables,
 * an installer's `env:` credential, the zoom range, prefetch areas named by geometry). */
function providerOf(draft: Draft, before?: MapProvider): MapProvider {
  const blank = (v: string) => (v.trim() === "" ? null : v.trim());
  const wmts = draft.way === "wmts";
  const days = Number.parseInt(draft.cache_days, 10);
  return {
    ...(before ?? {}),
    id: draft.id.trim(),
    label: draft.label.trim(),
    kind: draft.kind,
    source: wmts ? null : blank(draft.address),
    service: wmts ? "wmts" : null,
    endpoint: wmts ? blank(draft.address) : null,
    layer: wmts ? blank(draft.layer) : null,
    tile_matrix_set: wmts ? blank(draft.tile_matrix_set) : null,
    format: wmts ? blank(draft.format) : null,
    wmts_style: wmts ? blank(draft.wmts_style) : null,
    credential_param: wmts ? blank(draft.credential_param) : null,
    profile: null,
    proxy: draft.proxy,
    cache: Number.isFinite(days) && days > 0 ? { ttl_days: days, prefetch_areas: before?.cache?.prefetch_areas ?? [] } : null,
    style: blank(draft.style),
    attribution: draft.attribution.trim(),
    licence: {
      id: draft.licence_id.trim(),
      redistributable: draft.redistributable,
      client_scope: draft.client_scope,
      note: blank(draft.licence_note),
    },
  } as MapProvider;
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="admin-maps-row">
      <label htmlFor={id}>{label}</label>
      {children}
    </div>
  );
}

function ProviderForm({
  initial,
  editing,
  onSave,
  onCancel,
}: {
  initial: Draft;
  editing: boolean;
  onSave: (draft: Draft) => void;
  onCancel: () => void;
}) {
  const [d, setD] = useState<Draft>(initial);
  const id = editing ? `edit-${initial.id}` : "add-provider";
  const set = (patch: Partial<Draft>) => setD({ ...d, ...patch });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSave(d);
  };
  return (
    <form className="admin-maps-form" aria-label={editing ? `Edit ${initial.label}` : "Add a provider"} onSubmit={submit}>
      <Field id={`${id}-id`} label="Provider id">
        <Input id={`${id}-id`} value={d.id} readOnly={editing} aria-readonly={editing} onChange={(e) => set({ id: e.target.value })} />
      </Field>
      <Field id={`${id}-label`} label="Label analysts see">
        <Input id={`${id}-label`} value={d.label} onChange={(e) => set({ label: e.target.value })} />
      </Field>
      <Field id={`${id}-kind`} label="Kind of tiles">
        <Select id={`${id}-kind`} value={d.kind} onChange={(e) => set({ kind: e.target.value as Draft["kind"] })}>
          <option value="vector">Vector</option>
          <option value="raster">Raster</option>
          <option value="image">A georeferenced image</option>
          <option value="dem">Terrain</option>
        </Select>
      </Field>
      <Field id={`${id}-way`} label="How the tiles are reached">
        <Select id={`${id}-way`} value={d.way} onChange={(e) => set({ way: e.target.value as Draft["way"] })}>
          <option value="address">A tile address or a local file</option>
          <option value="wmts">A WMTS service</option>
        </Select>
      </Field>
      <Field
        id={`${id}-address`}
        label={d.way === "wmts" ? "The service's address" : "Tile address ({z}/{x}/{y}, and {credential} for a key) or file://"}
      >
        <Input id={`${id}-address`} value={d.address} spellCheck={false} onChange={(e) => set({ address: e.target.value })} />
      </Field>
      {d.way === "wmts" && (
        <>
          <Field id={`${id}-layer`} label="Layer">
            <Input id={`${id}-layer`} value={d.layer} onChange={(e) => set({ layer: e.target.value })} />
          </Field>
          <Field id={`${id}-tms`} label="Tile matrix set">
            <Input id={`${id}-tms`} value={d.tile_matrix_set} onChange={(e) => set({ tile_matrix_set: e.target.value })} />
          </Field>
          <Field id={`${id}-format`} label="Image format">
            <Input id={`${id}-format`} value={d.format} onChange={(e) => set({ format: e.target.value })} />
          </Field>
          <Field id={`${id}-wstyle`} label="Service style">
            <Input id={`${id}-wstyle`} value={d.wmts_style} onChange={(e) => set({ wmts_style: e.target.value })} />
          </Field>
          <Field id={`${id}-param`} label="The query parameter its key goes in (blank for none)">
            <Input id={`${id}-param`} value={d.credential_param} onChange={(e) => set({ credential_param: e.target.value })} />
          </Field>
        </>
      )}
      <Field id={`${id}-proxy`} label="Fetched by">
        <Select id={`${id}-proxy`} value={d.proxy} onChange={(e) => set({ proxy: e.target.value as Draft["proxy"] })}>
          <option value="required">The Conduit, always (keeps any key on the server)</option>
          <option value="recommended">The Conduit</option>
          <option value="none">The analyst&apos;s browser</option>
        </Select>
      </Field>
      <Field id={`${id}-cache`} label="Keep fetched tiles for (days; blank for not at all)">
        <Input id={`${id}-cache`} inputMode="numeric" value={d.cache_days} onChange={(e) => set({ cache_days: e.target.value })} />
      </Field>
      <Field id={`${id}-style`} label="Map style">
        <Select id={`${id}-style`} value={d.style} onChange={(e) => set({ style: e.target.value })}>
          <option value="">None (an image or raster layer)</option>
          <option value="bundled:osprey-dark">OspreyFlow dark</option>
          <option value="bundled:osprey-light">OspreyFlow light</option>
        </Select>
      </Field>
      <Field id={`${id}-attribution`} label="Attribution shown on the map">
        <Input id={`${id}-attribution`} value={d.attribution} onChange={(e) => set({ attribution: e.target.value })} />
      </Field>
      <Field id={`${id}-licence`} label="Licence">
        <Input id={`${id}-licence`} value={d.licence_id} onChange={(e) => set({ licence_id: e.target.value })} />
      </Field>
      <Field id={`${id}-scope`} label="Who the licence covers">
        <Select id={`${id}-scope`} value={d.client_scope} onChange={(e) => set({ client_scope: e.target.value as Draft["client_scope"] })}>
          <option value="open">Anyone</option>
          <option value="per-deployment">This deployment</option>
          <option value="per-seat">Each seat</option>
        </Select>
      </Field>
      <div className="admin-maps-check">
        <Checkbox id={`${id}-redistributable`} checked={d.redistributable} onChange={(e) => set({ redistributable: e.target.checked })} />
        <label htmlFor={`${id}-redistributable`}>The tiles may be passed on to others</label>
      </div>
      <Field id={`${id}-note`} label="Anything the licence asks to be said">
        <Input id={`${id}-note`} value={d.licence_note} onChange={(e) => set({ licence_note: e.target.value })} />
      </Field>
      <div className="admin-maps-actions">
        <Button type="submit" variant="primary">
          {editing ? "Save the provider" : "Add the provider"}
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function KeyForm({ row, onSend, onCancel }: { row: AdminMapProvider; onSend: (key: string) => void; onCancel: () => void }) {
  const [key, setKeyText] = useState("");
  const { id, label } = row.provider;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const typed = key;
    setKeyText("");
    onSend(typed);
  };
  return (
    <form className="admin-maps-form" aria-label={`The key for ${label}`} onSubmit={submit}>
      <label htmlFor={`map-key-${id}`}>
        {row.key_state === "set" ? "New key" : "Key"} for {label} (not shown, never sent back)
      </label>
      <Input id={`map-key-${id}`} type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => setKeyText(e.target.value)} />
      <div className="admin-maps-actions">
        <Button type="submit" variant="primary" disabled={key.trim() === ""}>
          {row.key_state === "set" ? "Rotate the key" : "Set the key"}
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

interface AreaDraft {
  name: string;
  provider_id: string;
  west: string;
  south: string;
  east: string;
  north: string;
  zoom_min: string;
  zoom_max: string;
}

function AreaForm({ providers, onSave, onCancel }: { providers: AdminMapProvider[]; onSave: (area: PrefetchArea) => void; onCancel: () => void }) {
  const [d, setD] = useState<AreaDraft>({
    name: "", provider_id: providers[0]?.provider.id ?? "", west: "", south: "", east: "", north: "", zoom_min: "10", zoom_max: "14",
  });  // prettier-ignore
  const set = (patch: Partial<AreaDraft>) => setD({ ...d, ...patch });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSave({
      name: d.name.trim(), provider_id: d.provider_id, west: Number(d.west), south: Number(d.south),
      east: Number(d.east), north: Number(d.north), zoom_min: Number(d.zoom_min), zoom_max: Number(d.zoom_max),
    });  // prettier-ignore
  };
  const number = (key: keyof AreaDraft, label: string) => (
    <Field id={`area-${key}`} label={label}>
      <Input id={`area-${key}`} inputMode="decimal" value={d[key]} onChange={(e) => set({ [key]: e.target.value })} />
    </Field>
  );
  return (
    <form className="admin-maps-form" aria-label="Add a prefetch area" onSubmit={submit}>
      <Field id="area-name" label="Area name">
        <Input id="area-name" value={d.name} onChange={(e) => set({ name: e.target.value })} />
      </Field>
      <Field id="area-provider" label="Provider">
        <Select id="area-provider" value={d.provider_id} onChange={(e) => set({ provider_id: e.target.value })}>
          {providers.map((p) => (
            <option key={p.provider.id} value={p.provider.id}>
              {p.provider.label}
            </option>
          ))}
        </Select>
      </Field>
      {number("west", "West (degrees of longitude)")}
      {number("south", "South (degrees of latitude)")}
      {number("east", "East (degrees of longitude)")}
      {number("north", "North (degrees of latitude)")}
      {number("zoom_min", "Lowest zoom")}
      {number("zoom_max", "Highest zoom")}
      <div className="admin-maps-actions">
        <Button type="submit" variant="primary">
          Add the area
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

type Open = { kind: "add" } | { kind: "edit"; id: string } | { kind: "key"; id: string } | { kind: "area" } | null;

export function Maps({ api }: { api: MapsApi }) {
  const [view, setView] = useState<MapsAdminView | null>(null);
  const [history, setHistory] = useState<MapAdminEntry[]>([]);
  const [open, setOpen] = useState<Open>(null);
  const [region, setRegion] = useState("rutland");
  const [said, setSaid] = useState<string | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshHistory = () => {
    readMapHistory(api)
      .then((h) => setHistory(h.entries))
      .catch(() => undefined);
  };
  const refresh = () => readMaps(api).then(setView);
  const act = (work: Promise<MapsAdminView>, words: string) => {
    setProblem(null);
    setSaid(null);
    setLines([]);
    void work
      .then((next) => {
        setView(next);
        setOpen(null);
        setSaid(words);
        refreshHistory();
      })
      .catch((e: Error) => setProblem(e.message));
  };
  const run = (work: () => Promise<{ said: string; lines: string[] }>) => {
    setProblem(null);
    setSaid(null);
    setLines([]);
    setBusy(true);
    void work()
      .then((done) => {
        setSaid(done.said);
        setLines(done.lines);
        refreshHistory();
        return refresh();
      })
      .catch((e: Error) => setProblem(e.message))
      .finally(() => setBusy(false));
  };
  useEffect(() => {
    refresh().catch((e: Error) => setProblem(e.message));
    refreshHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);

  const fetchable = view?.providers.filter((p) => p.provider.proxy !== "none" && p.provider.cache) ?? [];
  const scheduleHours = view?.schedule.every_hours ?? 0;

  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        The basemaps analysts may choose, the one the map opens on, each provider&apos;s key, the local basemap and the
        areas whose tiles are fetched ahead of use. A key is kept by the Conduit alone: it is never shown again, never
        sent back and never in the history. Every change is recorded there.
      </p>
      {problem && <p role="alert">{problem}</p>}
      {said && (
        <div role="status">
          <p style={{ margin: 0 }}>{said}</p>
          {lines.length > 0 && (
            <ul className="admin-maps-lines">
              {lines.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {!view && !problem && <p className="label">Reading the maps…</p>}
      {view && (
        <>
          <section aria-labelledby="maps-providers">
            <h3 id="maps-providers">Providers</h3>
            <p className="label" style={{ margin: 0 }}>
              {view.changed_in_admin
                ? "Changed here: these replace the map section of osprey.yaml."
                : "As the installer set them in osprey.yaml, until something is changed here."}
            </p>
            <table className="table" aria-label="Map providers">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Tier</th>
                  <th>Attribution and licence</th>
                  <th>Key</th>
                  <th>State</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {view.providers.map((row) => {
                  const p = row.provider;
                  const isDefault = p.id === view.default;
                  return (
                    <tr key={p.id}>
                      <td>
                        {p.label} <span className="label">({p.id})</span>
                        {isDefault && <div className="label">The map opens on this one</div>}
                      </td>
                      <td>{TIER_WORDS[row.tier]}</td>
                      <td>
                        {p.attribution}
                        <div className="label">
                          {p.licence.id}
                          {p.licence.note ? `: ${p.licence.note}` : ""}
                        </div>
                      </td>
                      <td>
                        {row.needs_key ? KEY_WORDS[row.key_state] : "No key needed"}
                        {row.key_state === "set" && row.key_set_at && (
                          <div className="label">
                            {when(row.key_set_at)}, by {row.key_set_by}
                          </div>
                        )}
                      </td>
                      <td>{row.state}</td>
                      <td className="admin-maps-actions">
                        {!isDefault && (
                          <Button aria-label={`Make the default: ${p.label}`} onClick={() => act(setMapDefault(api, p.id), `The map now opens on ${p.label}.`)}>
                            Make the default
                          </Button>
                        )}
                        <Button aria-label={`Edit ${p.label}`} onClick={() => setOpen({ kind: "edit", id: p.id })}>
                          Edit
                        </Button>
                        {row.needs_key && (
                          <Button
                            aria-label={`${row.key_state === "set" ? "Rotate" : "Enter"} key for ${p.label}`}
                            onClick={() => setOpen({ kind: "key", id: p.id })}
                          >
                            {row.key_state === "set" ? "Rotate key" : "Enter key"}
                          </Button>
                        )}
                        {row.key_state === "set" && (
                          <Button aria-label={`Remove key for ${p.label}`} onClick={() => act(removeMapKey(api, p.id), `${p.label}: the key is removed.`)}>
                            Remove key
                          </Button>
                        )}
                        {!isDefault && (
                          <Button aria-label={`Remove ${p.label}`} onClick={() => act(removeProvider(api, p.id), `${p.label} is removed.`)}>
                            Remove
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {open?.kind === "edit" &&
              (() => {
                const row = view.providers.find((r) => r.provider.id === open.id);
                return row ? (
                  <ProviderForm
                    key={open.id}
                    initial={draftOf(row.provider)}
                    editing
                    onCancel={() => setOpen(null)}
                    onSave={(draft) => {
                      const next = providerOf(draft, row.provider);
                      const moved = next.source !== row.provider.source || next.endpoint !== row.provider.endpoint;
                      act(
                        editProvider(api, next),
                        row.key_state === "set" && moved
                          ? `${draft.label} is saved. Its address changed, so its key was removed: a key is never sent to an address it was not entered for. Enter the key again.`
                          : `${draft.label} is saved.`,
                      );
                    }}
                  />
                ) : null;
              })()}
            {open?.kind === "key" &&
              (() => {
                const row = view.providers.find((r) => r.provider.id === open.id);
                return row ? (
                  <KeyForm
                    key={open.id}
                    row={row}
                    onCancel={() => setOpen(null)}
                    onSend={(key) => act(setMapKey(api, row.provider.id, key), `${row.provider.label}: the key is set. It is kept by the Conduit and never shown again.`)}
                  />
                ) : null;
              })()}
            {open?.kind === "add" ? (
              <ProviderForm
                initial={EMPTY}
                editing={false}
                onCancel={() => setOpen(null)}
                onSave={(draft) => act(addProvider(api, providerOf(draft)), `${draft.label || draft.id} is added.`)}
              />
            ) : (
              <Button aria-label="Add a provider" onClick={() => setOpen({ kind: "add" })}>
                Add a provider
              </Button>
            )}
          </section>

          <section aria-labelledby="maps-local">
            <h3 id="maps-local">The local basemap</h3>
            <table className="table" aria-label="Local basemaps">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>File</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {view.basemap.basemaps.map((b) => (
                  <tr key={b.provider_id}>
                    <td>{b.provider_id}</td>
                    <td>{b.file}</td>
                    <td>{b.built ? `Built ${when(b.built_at)}, ${bytes(b.size_bytes)}` : "Not built yet"}</td>
                  </tr>
                ))}
                <tr>
                  <td>Place-name fonts</td>
                  <td>{view.basemap.glyph_fonts.join(", ")}</td>
                  <td>{view.basemap.glyphs_installed ? "Installed" : "Not installed: the map is drawn without names"}</td>
                </tr>
              </tbody>
            </table>
            <p className="label" style={{ margin: 0 }}>
              {view.basemap.builder_state}
            </p>
            <div className="admin-maps-actions">
              <div className="admin-maps-row">
                <label htmlFor="maps-region">Region to build</label>
                <Select id="maps-region" value={region} onChange={(e) => setRegion(e.target.value)}>
                  {view.basemap.regions.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </Select>
              </div>
              <Button disabled={busy || !view.basemap.builder_ready} onClick={() => run(() => buildBasemap(api, region))}>
                Build the basemap
              </Button>
              <Button
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const r = await verifyMaps(api);
                    return {
                      said: r.passed ? "Verify passed: every provider is attributed and reachable as declared." : "Verify found issues.",
                      lines: r.issues.map((i) => `${i.provider_id}: ${i.check}: ${i.detail}`),
                    };
                  })
                }
              >
                Verify the providers
              </Button>
            </div>
          </section>

          <section aria-labelledby="maps-areas">
            <h3 id="maps-areas">Prefetch areas</h3>
            <p className="label" style={{ margin: 0 }}>
              An area&apos;s tiles are fetched ahead of use, so routine work there asks the provider nothing and says
              nothing about where analysts look. Only a provider fetched and kept by the Conduit can have one.
            </p>
            {view.areas.length > 0 && (
              <table className="table" aria-label="Prefetch areas">
                <thead>
                  <tr>
                    <th>Area</th>
                    <th>Provider</th>
                    <th>Box and zooms</th>
                    <th>Last run</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {view.areas.map(({ area, tiles, last_run }) => (
                    <tr key={area.name}>
                      <td>{area.name}</td>
                      <td>{area.provider_id}</td>
                      <td>
                        {area.west}, {area.south} to {area.east}, {area.north}; zooms {area.zoom_min} to {area.zoom_max} (
                        {tiles.toLocaleString("en-GB")} tiles)
                      </td>
                      <td>
                        {last_run
                          ? `${when(last_run.at)}: ${last_run.tiles_fetched.toLocaleString("en-GB")} fetched, ${last_run.tiles_already_cached.toLocaleString("en-GB")} already kept${last_run.failed ? `. ${last_run.failed}` : ""}`
                          : "Not run yet"}
                      </td>
                      <td>
                        <Button
                          aria-label={`Remove the area ${area.name}`}
                          onClick={() => act(setAreas(api, view.areas.map((a) => a.area).filter((a) => a.name !== area.name)), `The area ${area.name} is removed.`)}
                        >
                          Remove
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {open?.kind === "area" ? (
              <AreaForm
                providers={fetchable}
                onCancel={() => setOpen(null)}
                onSave={(area) => act(setAreas(api, [...view.areas.map((a) => a.area), area]), `The area ${area.name} is added.`)}
              />
            ) : (
              fetchable.length > 0 && (
                <Button onClick={() => setOpen({ kind: "area" })}>Add a prefetch area</Button>
              )
            )}
            <div className="admin-maps-actions">
              <div className="admin-maps-row">
                <label htmlFor="maps-schedule">Fetch every area</label>
                <Select
                  id="maps-schedule"
                  value={String(scheduleHours)}
                  onChange={(e) => {
                    const hours = Number(e.target.value);
                    act(setSchedule(api, { every_hours: hours === 0 ? null : hours }), "The prefetch schedule is saved.");
                  }}
                >
                  {SCHEDULES.map((s) => (
                    <option key={s.hours} value={String(s.hours)}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </div>
              <Button
                disabled={busy || view.areas.length === 0}
                onClick={() =>
                  run(async () => {
                    const runs = await runPrefetch(api);
                    return {
                      said: runs.every((r) => !r.failed) ? "Every area is fetched." : "Some areas did not finish.",
                      lines: runs.map((r) => `${r.area}: ${r.tiles_fetched} fetched, ${r.tiles_already_cached} already kept${r.failed ? `. ${r.failed}` : ""}`),
                    };
                  })
                }
              >
                Fetch every area now
              </Button>
            </div>
            {view.next_run_at && <p className="label">Next run: {when(view.next_run_at)}</p>}
          </section>

          <section aria-labelledby="maps-history">
            <h3 id="maps-history">History</h3>
            {history.length === 0 ? (
              <p className="label" style={{ margin: 0 }}>
                Nothing has been changed here yet.
              </p>
            ) : (
              <table className="table" aria-label="Maps' history">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Who</th>
                    <th>What</th>
                    <th>Provider</th>
                    <th>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((entry, i) => (
                    <tr key={`${entry.at}-${i}`}>
                      <td>{when(entry.at)}</td>
                      <td>{entry.by}</td>
                      <td>{entry.action.replaceAll("_", " ")}</td>
                      <td>{entry.provider ?? ""}</td>
                      <td>{entry.outcome}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </>
  );
}
