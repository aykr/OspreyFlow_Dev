// *Show YAML* (ADR-140 decision 3; brief §6): the pipeline as the Conduit writes it, always
// available. In expert mode it is editable and saved through the canvas's own gates, its refusals in
// the gate's words; the text is read as a pipeline, never run. In guided mode it reads only.
import { useEffect, useState } from "react";

import type { StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { fetchPipelineYaml, savePipelineYaml } from "../api";
import type { StudioMode } from "./studioMode";

export function PipelineYaml({
  apiBaseUrl,
  bearerToken,
  investigationId,
  recipeId,
  mode,
  version,
  onSaved,
}: {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  recipeId: string;
  mode: StudioMode;
  /** The pipeline as last saved, so the text reads again after any save. */
  version: string;
  onSaved: (draft: StudioRecipeDraft) => void;
}) {
  const [text, setText] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchPipelineYaml(apiBaseUrl, bearerToken, investigationId, recipeId)
      .then((found) => !cancelled && setText(found))
      .catch((err: unknown) => !cancelled && setProblems([err instanceof Error ? err.message : "The YAML could not be read."]));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, recipeId, version]);

  async function save() {
    if (text === null) return;
    setBusy(true);
    setSaid(null);
    try {
      const outcome = await savePipelineYaml(apiBaseUrl, bearerToken, investigationId, recipeId, text);
      if (outcome.kind === "invalid") setProblems(outcome.problems);
      else {
        setProblems([]);
        setSaid("Saved.");
        onSaved(outcome.draft);
      }
    } catch (err: unknown) {
      setProblems([err instanceof Error ? err.message : "The YAML could not be saved."]);
    } finally {
      setBusy(false);
    }
  }

  const editable = mode === "expert";
  return (
    <section aria-label="Pipeline as YAML" style={{ display: "grid", gap: "var(--sp-8)", minWidth: 0 }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-14)" }}>Pipeline as YAML</h3>
      <p className="label" style={{ margin: 0 }}>
        {editable
          ? "The pipeline is this YAML. Edit it and save: the same gates as the canvas judge it, and nothing in it is run."
          : "The pipeline is this YAML. Switch to expert mode to edit it."}
      </p>
      {text === null && problems.length === 0 && <p className="label">Reading the YAML…</p>}
      {text !== null && (
        <textarea
          className="input"
          aria-label="Pipeline YAML"
          rows={24}
          spellCheck={false}
          readOnly={!editable}
          style={{ fontFamily: "var(--mono)", minWidth: 0, width: "100%" }}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      )}
      {editable && text !== null && (
        <div>
          <Button variant="primary" disabled={busy} onClick={() => void save()}>
            Save YAML
          </Button>
        </div>
      )}
      {problems.length > 0 && (
        <div role="alert" style={{ display: "grid", gap: "var(--sp-2)" }}>
          {problems.map((p) => (
            <p key={p} style={{ margin: 0 }}>
              {p}
            </p>
          ))}
        </div>
      )}
      {said && (
        <p role="status" className="label" style={{ margin: 0 }}>
          {said}
        </p>
      )}
    </section>
  );
}
