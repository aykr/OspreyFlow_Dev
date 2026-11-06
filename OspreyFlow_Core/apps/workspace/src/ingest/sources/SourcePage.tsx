// One registered source (ADR-140 decision 7): its profile (computed for this reader, never stored),
// its governance and an audited edit of it, its lineage (the dataset's pipelines that read it),
// Re-profile and Open in a pipeline. Editing its governance flags every deployed pipeline reading it
// as needing attention, and every draft reading it follows at once (ADR-140 Amendment 4).
import { useCallback, useEffect, useState } from "react";

import type { SourceLineage, SourceProfile, SourceTable } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import type { HandlingScheme } from "../api";
import { statusWords } from "../studio/vocabulary";
import { editGovernance, pauseRefresh, resumeRefresh, sourceLineage, sourceProfile, type SourcesApi } from "./api";
import { type Governance, GovernanceFields, governanceOf, handlingOf, missing, refreshInWords } from "./GovernanceFields";

export interface SourcePageProps {
  api: SourcesApi;
  datasetId: string;
  source: SourceTable;
  scheme: HandlingScheme | null;
  onBack: () => void;
  onChanged: (source: SourceTable) => void;
  /** Opens the Pipelines tab, where a pipeline's source node chooses this source. */
  onOpenInPipeline: () => void;
}

function markingOf(handling: Record<string, unknown>): string {
  return [handling.classification, handling.handling_code].filter((v) => typeof v === "string" && v).join(" · ") || "not marked";
}

export function SourcePage({ api, datasetId, source, scheme, onBack, onChanged, onOpenInPipeline }: SourcePageProps) {
  const [profile, setProfile] = useState<SourceProfile | null>(null);
  const [lineage, setLineage] = useState<SourceLineage[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [editing, setEditing] = useState<Governance | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // ADR-110 Amendment 13: why the refresh is being paused, said before it is.
  const [pauseReason, setPauseReason] = useState("");

  const reprofile = useCallback(() => {
    setProfile(null);
    sourceProfile(api, datasetId, source.id)
      .then(setProfile)
      .catch((e: Error) => setProblem(e.message));
  }, [api, datasetId, source.id]);

  useEffect(() => {
    reprofile();
    sourceLineage(api, datasetId, source.id)
      .then(setLineage)
      .catch((e: Error) => setProblem(e.message));
  }, [api, datasetId, source.id, reprofile]);

  async function save() {
    if (!editing) return;
    setBusy(true);
    setProblem(null);
    try {
      const edited = await editGovernance(api, datasetId, source.id, {
        handling: handlingOf(editing),
        legal_basis: editing.legalBasis.trim(),
        refresh: editing.refresh,
      });
      setEditing(null);
      const flagged = edited.needs_attention ?? [];
      setSaid(
        flagged.length > 0
          ? `Saved as version ${edited.source.version}. These deployed pipelines now need attention until deployed again: ${flagged.join(", ")}.`
          : `Saved as version ${edited.source.version}.`,
      );
      onChanged(edited.source);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "The governance could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function setPaused(paused: boolean) {
    setBusy(true);
    setProblem(null);
    try {
      const changed = paused
        ? await pauseRefresh(api, datasetId, source.id, pauseReason)
        : await resumeRefresh(api, datasetId, source.id);
      setPauseReason("");
      setSaid(paused ? "The refresh is paused; its files wait until it is resumed." : "The refresh is resumed.");
      onChanged(changed);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "The refresh could not be changed.");
    } finally {
      setBusy(false);
    }
  }

  const refresh = source.refresh;
  return (
    <section aria-label={`Source ${source.name}`} style={{ display: "grid", gap: "var(--sp-12)" }}>
      <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
        <Button onClick={onBack}>← Sources</Button>
        <h2 style={{ margin: 0, fontSize: "var(--fs-16)" }}>{source.name}</h2>
        <span className="label">{`version ${source.version}`}</span>
        <span style={{ flex: 1 }} />
        <Button onClick={reprofile}>Re-profile</Button>
        <Button onClick={onOpenInPipeline}>Open in a pipeline</Button>
      </div>
      {problem && <p role="alert">{problem}</p>}
      {said && <p role="status">{said}</p>}

      <section aria-label="Governance" style={{ display: "grid", gap: "var(--sp-8)" }}>
        <h3 style={{ margin: 0, fontSize: "var(--fs-14)" }}>Governance</h3>
        {editing ? (
          <>
            <GovernanceFields scheme={scheme} value={editing} onChange={setEditing} />
            <p className="label" style={{ margin: 0 }}>
              Saving is a new version of the source, recorded in the audit trail. Every deployed pipeline that reads
              it will need attention until it is deployed again; every draft reading it takes the change at once
              and must be tested again.
            </p>
            {missing(editing).length > 0 && <p className="label" style={{ margin: 0 }}>{`Still to give: ${missing(editing).join(", ")}.`}</p>}
            <div style={{ display: "flex", gap: "var(--sp-8)" }}>
              <Button onClick={() => setEditing(null)}>Cancel</Button>
              <Button variant="primary" disabled={busy || missing(editing).length > 0} onClick={() => void save()}>
                {busy ? "Saving…" : "Save the governance"}
              </Button>
            </div>
          </>
        ) : (
          <>
            <dl style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "var(--sp-4) var(--sp-16)", margin: 0 }}>
              <dt>Marking</dt>
              <dd style={{ margin: 0 }}>{markingOf(source.handling ?? {})}</dd>
              <dt>Legal basis</dt>
              <dd style={{ margin: 0 }}>{source.legal_basis || "not given"}</dd>
              <dt>Refresh</dt>
              <dd style={{ margin: 0 }}>{refreshInWords(refresh)}</dd>
              {refresh?.trigger === "watch" && (
                <>
                  <dt>Runs as</dt>
                  <dd style={{ margin: 0 }}>{refresh.owner ?? "nobody: set the refresh again"}</dd>
                  <dt>State</dt>
                  <dd style={{ margin: 0 }}>{refresh.paused ? `paused: ${refresh.paused_reason ?? "by hand"}` : "running"}</dd>
                </>
              )}
            </dl>
            {refresh?.trigger === "watch" &&
              (refresh.paused ? (
                <div>
                  <Button disabled={busy} onClick={() => void setPaused(false)}>
                    Resume the refresh
                  </Button>
                </div>
              ) : (
                <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "end", flexWrap: "wrap" }}>
                  <label style={{ display: "grid", gap: "var(--sp-2)" }}>
                    <span className="label">Why pause it (optional)</span>
                    <Input value={pauseReason} onChange={(e) => setPauseReason(e.target.value)} />
                  </label>
                  <Button disabled={busy} onClick={() => void setPaused(true)}>
                    Pause the refresh
                  </Button>
                </div>
              ))}
            <div>
              <Button onClick={() => setEditing(governanceOf(source.handling ?? {}, source.legal_basis, source.refresh))}>
                Edit governance
              </Button>
            </div>
          </>
        )}
      </section>

      <section aria-label="Profile" style={{ display: "grid", gap: "var(--sp-8)" }}>
        <h3 style={{ margin: 0, fontSize: "var(--fs-14)" }}>Profile</h3>
        {profile === null ? (
          <p className="label" style={{ margin: 0 }}>Profiling…</p>
        ) : (
          <>
            <p className="label" style={{ margin: 0 }}>
              {`${profile.rows_sampled} rows ${profile.sample_is_whole_source ? "(the whole source)" : "sampled"}${profile.values_masked ? "; values above your clearance are masked" : ""}.`}
            </p>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Column</th>
                  <th scope="col">Type</th>
                  <th scope="col">Empty</th>
                  <th scope="col">Distinct</th>
                </tr>
              </thead>
              <tbody>
                {profile.columns.map((c) => (
                  <tr key={c.name}>
                    <td>{c.name}</td>
                    <td>{c.inferred_type}</td>
                    <td>{c.null_count}</td>
                    <td>{c.distinct_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      <section aria-label="Lineage" style={{ display: "grid", gap: "var(--sp-8)" }}>
        <h3 style={{ margin: 0, fontSize: "var(--fs-14)" }}>Lineage</h3>
        {lineage === null ? (
          <p className="label" style={{ margin: 0 }}>Reading…</p>
        ) : lineage.length === 0 ? (
          <p className="label" style={{ margin: 0 }}>No pipeline reads this source yet.</p>
        ) : (
          <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            {lineage.map((l) => (
              <li key={`${l.recipe_id}:${l.version}`}>{`${l.label} · v${l.version} · ${statusWords(l.status)}`}</li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
