import { useEffect, useState } from "react";

import { ApiError, getProfileOptions } from "../api/client";
import type { AnalyticsEngine, GraphStore, OspreyConfig, ProfileOptions } from "../api/types";

export function ComponentsScreen({
  config,
  onSave,
}: {
  config: OspreyConfig;
  onSave: (patch: Partial<OspreyConfig>) => Promise<void>;
}) {
  const [options, setOptions] = useState<ProfileOptions | null>(null);
  const [graphStore, setGraphStore] = useState<GraphStore>(
    config.components?.graph_store ?? "arcadedb",
  );
  const [analyticsEngine, setAnalyticsEngine] = useState<AnalyticsEngine>(
    config.components?.analytics_engine ?? "duckdb",
  );
  // Owner ruling R6, 27 September 2026 — the fourth storage root, and the only one an analyst
  // ever touches. The other three (data, staging, backups) are not editable here either; this
  // screen gains the one the ruling names rather than growing editors nobody asked for.
  const [ingestRoot, setIngestRoot] = useState<string>(
    config.components?.storage?.ingest ?? "/var/lib/osprey/ingest",
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProfileOptions(config.profile ?? "local-lite").then((result) => {
      if (cancelled) return;
      setOptions(result);
      // §2.1: "every later screen filters its options to what is valid here" — if the currently
      // selected value is not valid for the profile now in force, fall forward to the profile's
      // own first allowed option rather than offering a choice this profile already refuses.
      if (!result.allowed_graph_stores.includes(graphStore)) {
        setGraphStore(result.allowed_graph_stores[0] as GraphStore);
      }
      if (!result.allowed_analytics_engines.includes(analyticsEngine)) {
        setAnalyticsEngine(result.allowed_analytics_engines[0] as AnalyticsEngine);
      }
    });
    return () => {
      cancelled = true;
    };
    // Re-runs only when the saved profile changes — the filter this screen applies is the saved
    // profile's own, not a draft one Profile screen has not yet saved.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.profile]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave({
        components: {
          ...config.components,
          graph_store: graphStore,
          analytics_engine: analyticsEngine,
          storage: { ...config.components?.storage, ingest: ingestRoot },
        },
      });
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.body : String(exc));
    } finally {
      setSaving(false);
    }
  }

  if (!options) return <p>Loading…</p>;

  return (
    <section aria-labelledby="components-heading">
      <h2 id="components-heading">Components</h2>
      <p>Valid at profile {config.profile}: {options.allowed_graph_stores.join(", ")} /{" "}
        {options.allowed_analytics_engines.join(", ")}</p>

      <label htmlFor="graph-store">Graph store</label>
      <select
        id="graph-store"
        className="select"
        value={graphStore}
        onChange={(event) => setGraphStore(event.target.value as GraphStore)}
      >
        {options.allowed_graph_stores.map((value) => (
          <option key={value} value={value}>
            {value}
          </option>
        ))}
      </select>

      <label htmlFor="analytics-engine">Analytics engine</label>
      <select
        id="analytics-engine"
        className="select"
        value={analyticsEngine}
        onChange={(event) => setAnalyticsEngine(event.target.value as AnalyticsEngine)}
      >
        {options.allowed_analytics_engines.map((value) => (
          <option key={value} value={value}>
            {value}
          </option>
        ))}
      </select>

      <label htmlFor="ingest-root">Ingest folder</label>
      <input
        id="ingest-root"
        className="input"
        value={ingestRoot}
        onChange={(event) => setIngestRoot(event.target.value)}
        aria-describedby="ingest-root-help"
      />
      <p id="ingest-root-help" className="help">
        Where an operator places source files for analysts to ingest. Mounted read-only into the
        Conduit, and listed by the Ingest Studio&rsquo;s Connect stage so an analyst picks a file
        rather than typing a path. OspreyFlow never writes here.
      </p>

      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save components
      </button>
    </section>
  );
}
