import { useEffect, useState } from "react";

import { ApiError, getModelChoices, postConsequences } from "../api/client";
import type { Consequences, ModelChoices, ModelJob, OspreyConfig } from "../api/types";

// ADR-095 decision 1: the system administrator chooses the deployment's own models here, from the
// pinned list the harness serves (never a copy kept in this file); the defaults are the ones the
// product ships with. Changing the extraction model downloads it on the next Launch.
const JOBS: { job: ModelJob; label: string }[] = [
  { job: "extraction", label: "Entity extraction model" },
  { job: "vision", label: "Image description model" },
  { job: "transcription", label: "Transcription model" },
  { job: "embedding", label: "Embedding model" },
];

export function ModelsScreen({
  config,
  onSave,
}: {
  config: OspreyConfig;
  onSave: (patch: Partial<OspreyConfig>) => Promise<void>;
}) {
  const [localOnly, setLocalOnly] = useState(config.models?.local_only ?? true);
  const [hostedFallback, setHostedFallback] = useState(config.models?.hosted_fallback ?? "");
  const [codes, setCodes] = useState((config.models?.sendable_handling_codes ?? []).join(", "));
  const [consequences, setConsequences] = useState<Consequences | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [choices, setChoices] = useState<ModelChoices | null>(null);
  const [chosen, setChosen] = useState<Partial<Record<ModelJob, string>>>({
    extraction: config.models?.extraction,
    vision: config.models?.vision,
    transcription: config.models?.transcription,
    embedding: config.models?.embedding,
  });

  useEffect(() => {
    getModelChoices()
      .then(setChoices)
      .catch(() => setChoices(null));
  }, []);

  const picked = (job: ModelJob): string | undefined => chosen[job] ?? choices?.defaults[job];

  const draftModels = {
    ...Object.fromEntries(
      JOBS.map(({ job }) => [job, picked(job)]).filter(([, name]) => name !== undefined),
    ),
    local_only: localOnly,
    hosted_fallback: localOnly ? null : hostedFallback || null,
    sendable_handling_codes: localOnly
      ? []
      : codes
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean),
  };

  useEffect(() => {
    let cancelled = false;
    postConsequences({ ...config, models: draftModels })
      .then((result) => {
        if (!cancelled) setConsequences(result);
      })
      .catch(() => {
        if (!cancelled) setConsequences(null);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config, localOnly, hostedFallback, codes, chosen, choices]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ models: draftModels });
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.body : String(exc));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="models-heading">
      <h2 id="models-heading">Models</h2>
      {choices === null && <p role="status">Reading the models this deployment may use…</p>}
      {choices !== null &&
        JOBS.map(({ job, label }) => (
          <div key={job}>
            <label htmlFor={`model-${job}`}>{label}</label>
            <select
              id={`model-${job}`}
              className="input"
              value={picked(job) ?? ""}
              onChange={(event) => setChosen({ ...chosen, [job]: event.target.value })}
            >
              {choices[job].map(({ name }) => (
                <option key={name} value={name}>
                  {name === choices.defaults[job] ? `${name} (default)` : name}
                </option>
              ))}
            </select>
          </div>
        ))}
      <label>
        <input
          type="checkbox"
          checked={localOnly}
          onChange={(event) => setLocalOnly(event.target.checked)}
        />{" "}
        Local only — no hosted fallback (default)
      </label>

      {!localOnly && (
        <>
          <label htmlFor="hosted-fallback">Hosted fallback provider</label>
          <input
            id="hosted-fallback"
            className="input"
            value={hostedFallback}
            onChange={(event) => setHostedFallback(event.target.value)}
          />
          <label htmlFor="sendable-codes">Sendable handling codes (comma-separated)</label>
          <input
            id="sendable-codes"
            className="input"
            value={codes}
            onChange={(event) => setCodes(event.target.value)}
          />
        </>
      )}

      {consequences?.egress_exception && (
        <p role="status">Egress exception: {consequences.egress_detail}</p>
      )}
      {consequences && !consequences.egress_exception && <p role="status">No egress exception.</p>}

      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save models
      </button>
    </section>
  );
}
