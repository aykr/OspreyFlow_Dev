// Stage 2 of the Ingest Studio — `spec/09_INGEST_STUDIO.md` §3. Automatic:
// this screen only ever renders what `GET /v1/ingest/recipes/{id}/profile`
// (`services/api/app.py`) already computed — `services/ingest/profiler.py`
// (Phase 2) does the type inference, pattern recognition and anomaly
// detection; nothing here re-derives any of it. The one decision this
// screen owns is display: per-column type/confidence, the shape-masked (or
// unmasked) samples exactly as the profiler returned them, pattern-match
// badges, and the anomaly flags, grouped by kind with a count and a sample
// (§3's own closing line: "each becomes a decision in the mapping stage
// rather than a silent default").
import { useEffect, useState } from "react";

import type {
  ColumnProfile,
  ProfileAnomaly,
  SourceProfile,
  StudioRecipeDraft,
} from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives/Button";
import { Panel } from "../design/primitives/Panel";
import { Table, type TableColumn } from "../design/primitives/Table";
import { fetchDraft, fetchProfile, ProfileError } from "./api";

export interface ProfileScreenProps {
  apiBaseUrl: string;
  bearerToken: string;
  recipeId: string;
  onBack: () => void;
}

// `generate_ts.py`'s index only re-exports the interfaces, not every
// scalar string-literal alias — `ProfileAnomaly["kind"]` gets the same
// union `AnomalyKind` names without needing a second export added there.
type AnomalyKind = ProfileAnomaly["kind"];

const ANOMALY_LABELS: Record<AnomalyKind, string> = {
  ragged_row: "Ragged row — column count varies",
  duplicate_row: "Apparent duplicate record",
  mixed_datetime_formats: "Mixed timestamp formats",
  undetermined_timezone: "Undeterminable timezone",
};

/** `services/api/app.py`'s exception handlers on this route — mirrors
 * `ProfileError.code`'s own doc comment. A code this screen has never seen
 * (a future addition) still gets `error.message`, never a blank screen. */
const ERROR_MESSAGES: Record<string, string> = {
  recipe_not_ready_for_profile:
    "This source isn't ready for Profile yet — go back to Connect and answer the location, handling marking and legal basis.",
  connector_not_available: "This source's connector has no reader yet, so it can't be profiled.",
  source_unreadable: "The source couldn't be read — check it's still at the location Connect recorded.",
  source_handling_incomplete:
    "This source's handling marking is incomplete — go back to Connect and fill in classification, handling code, originator and owning unit.",
};

function friendlyError(err: unknown): string {
  if (err instanceof ProfileError) {
    return ERROR_MESSAGES[err.code] ?? err.message;
  }
  return err instanceof Error ? err.message : String(err);
}

function typeLabel(column: ColumnProfile): string {
  const pct = Math.round(column.type_confidence * 100);
  return `${column.inferred_type} (${pct}%)`;
}

export function ProfileScreen({ apiBaseUrl, bearerToken, recipeId, onBack }: ProfileScreenProps) {
  const [draft, setDraft] = useState<StudioRecipeDraft | null>(null);
  const [profile, setProfile] = useState<SourceProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Independent, not `Promise.all` — a failed profile fetch (source
    // unreadable, connector unavailable, ...) shouldn't also blank out the
    // header's source label, which only needs the draft fetch to succeed.
    void fetchDraft(apiBaseUrl, bearerToken, recipeId)
      .then((draftResult) => {
        if (!cancelled) setDraft(draftResult);
      })
      .catch(() => {
        // Surfaced already by the profile fetch below if the recipe itself
        // is the problem; the label is a nice-to-have, not worth a second
        // error banner.
      });
    void fetchProfile(apiBaseUrl, bearerToken, recipeId)
      .then((profileResult) => {
        if (!cancelled) setProfile(profileResult);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(friendlyError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, recipeId]);

  const columns: TableColumn<ColumnProfile>[] = [
    { key: "name", header: "Field", render: (c) => <strong>{c.name}</strong> },
    { key: "type", header: "Inferred type", render: typeLabel },
    {
      key: "nulls",
      header: "Nulls / distinct",
      numeric: true,
      render: (c) => `${c.null_count} / ${c.distinct_count} of ${c.sample_size}`,
    },
    {
      key: "samples",
      header: "Sample values",
      render: (c) => (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4, 4px)" }}>
          {(c.sample_values ?? []).map((v, i) => (
            <span key={i} className="identifier" style={{ fontFamily: "var(--mono)" }}>
              {v}
            </span>
          ))}
        </div>
      ),
    },
    {
      key: "patterns",
      header: "Pattern matches",
      render: (c) => {
        const matches = c.pattern_matches ?? [];
        return matches.length === 0 ? (
          <span style={{ color: "var(--text-tertiary)" }}>—</span>
        ) : (
          <div style={{ display: "flex", gap: "var(--sp-4, 4px)", flexWrap: "wrap" }}>
            {matches.map((m) => (
              <span
                key={m.adapter}
                title={`${Math.round(m.match_rate * 100)}% of sampled values matched`}
                style={{
                  border: "1px solid var(--border-strong)",
                  borderRadius: "var(--r-panel)",
                  padding: "0 var(--sp-8)",
                  fontSize: "0.85em",
                  color: "var(--text-secondary)",
                }}
              >
                {m.adapter} {Math.round(m.match_rate * 100)}%
              </span>
            ))}
          </div>
        );
      },
    },
  ];

  const anomalies = profile?.anomalies ?? [];
  const rowAnomalies = anomalies.filter((a) => a.column === null);
  const columnAnomalies = anomalies.filter((a) => a.column !== null);

  function anomalyRow(a: ProfileAnomaly, key: number) {
    return (
      <li key={key} style={{ marginBottom: "var(--sp-8)" }}>
        <span style={{ color: "var(--warning)" }}>⚠</span>{" "}
        <strong>{ANOMALY_LABELS[a.kind]}</strong>
        {a.column && <> — column <code>{a.column}</code></>} — {a.count} row(s)
        <div style={{ color: "var(--text-tertiary)", fontFamily: "var(--mono)" }}>{a.sample}</div>
      </li>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-16)",
        padding: "var(--sp-16)",
        height: "100%",
        overflow: "auto",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
        <Button onClick={onBack}>← Connect</Button>
        <h1 style={{ fontSize: "1.1em", margin: 0 }}>
          Profile{draft ? ` — ${draft.label}` : ""}
        </h1>
      </div>

      {loading && <p style={{ color: "var(--text-secondary)" }}>Profiling the source…</p>}

      {error && (
        <div
          role="alert"
          style={{
            background: "var(--surface-raised)",
            border: "1px solid var(--border-strong)",
            borderRadius: "var(--r-panel)",
            padding: "var(--sp-8)",
          }}
        >
          {error}
        </div>
      )}

      {profile && (
        <>
          <p style={{ color: "var(--text-secondary)" }}>
            {profile.rows_sampled} row(s) sampled
            {profile.sample_is_whole_source
              ? " — the whole source."
              : " — the source has more rows than were profiled."}
          </p>

          {profile.values_masked && (
            <div
              role="status"
              style={{
                background: "var(--surface-raised)",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--r-panel)",
                padding: "var(--sp-8)",
                color: "var(--text-secondary)",
              }}
            >
              You aren't cleared for this source's handling marking, so sample values are
              shown shape-masked — letters as <code>A</code>, digits as <code>#</code>,
              everything else shown as-is.
            </div>
          )}

          <Panel title="Columns">
            <Table columns={columns} rows={profile.columns} getRowId={(c) => c.name} />
          </Panel>

          {(rowAnomalies.length > 0 || columnAnomalies.length > 0) && (
            <Panel title="What will hurt later">
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {[...columnAnomalies, ...rowAnomalies].map((a, i) => anomalyRow(a, i))}
              </ul>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
