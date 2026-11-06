// A pipeline's first source names a registered source (ADR-140 decision 7, Amendment 4): choosing one
// writes its file, connector, marking and legal basis to the draft, so no marking is asked inside the
// pipeline; the source's own page is where they are set. The deduplication key stays the draft's own
// until the Load node takes it (phase 6), so the draft's settings remain one press away.
import { useEffect, useMemo, useState } from "react";

import type { SourceTable, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Select } from "../../design/primitives/Select";
import { updateDraft } from "../api";
import { listSources } from "./api";

export interface SourceChooserProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  draft: StudioRecipeDraft;
  disabled: boolean;
  onUsed: (draft: StudioRecipeDraft, source: SourceTable) => void;
  onOpenDraftSettings: () => void;
}

export function SourceChooser({ apiBaseUrl, bearerToken, investigationId, draft, disabled, onUsed, onOpenDraftSettings }: SourceChooserProps) {
  const api = useMemo(() => ({ apiBaseUrl, bearerToken }), [apiBaseUrl, bearerToken]);
  const [sources, setSources] = useState<SourceTable[] | null>(null);
  const [chosen, setChosen] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!draft.dataset_id) return;
    listSources(api, draft.dataset_id)
      .then((found) => {
        setSources(found);
        setChosen(found.find((s) => s.location === draft.source_location)?.id ?? "");
      })
      .catch((e: Error) => setProblem(e.message));
  }, [api, draft.dataset_id, draft.source_location]);

  const current = (sources ?? []).find((s) => s.location === draft.source_location);

  async function use() {
    const source = (sources ?? []).find((s) => s.id === chosen);
    if (!source) return;
    setBusy(true);
    setProblem(null);
    try {
      const updated = await updateDraft(apiBaseUrl, bearerToken, investigationId, draft.recipe_id, {
        label: draft.label,
        connector_profile: source.connector_profile,
        source_location: source.location,
        handling: source.handling ?? {},
        legal_basis: source.legal_basis ?? null,
      });
      onUsed(updated, source);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "The source could not be used.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Source settings" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>Source</h3>
      <p className="label" style={{ margin: 0 }}>
        A registered source of this dataset. Its file, marking and legal basis come with it; they are set on the
        Sources tab.
      </p>
      {!draft.dataset_id && <p className="label">This pipeline belongs to no dataset, so it has no registered sources.</p>}
      {current && (
        <p style={{ margin: 0 }} role="status">{`Reads ${current.name} (version ${current.version}).`}</p>
      )}
      {sources?.length === 0 && <p className="label">No source is registered for this dataset yet: register one on the Sources tab.</p>}
      {sources && sources.length > 0 && (
        <label style={{ display: "grid", gap: "var(--sp-2)" }}>
          <span className="label">Registered source</span>
          <Select value={chosen} onChange={(e) => setChosen(e.target.value)}>
            <option value="">Choose a source</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </label>
      )}
      {problem && <p role="alert">{problem}</p>}
      <div style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
        <Button variant="primary" disabled={disabled || busy || !chosen || chosen === current?.id} onClick={() => void use()}>
          Use this source
        </Button>
        <Button onClick={onOpenDraftSettings}>The draft&apos;s own settings</Button>
      </div>
    </section>
  );
}
