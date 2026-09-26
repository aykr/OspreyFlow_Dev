import { useEffect, useState } from "react";

import { ApiError, postConsequences } from "../api/client";
import type { Consequences, OspreyConfig } from "../api/types";

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

  const draftModels = {
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
  }, [config, localOnly, hostedFallback, codes]);

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
