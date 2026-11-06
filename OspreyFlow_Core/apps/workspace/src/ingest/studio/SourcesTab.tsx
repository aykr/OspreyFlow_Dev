// 2 Sources (ADR-140 decision 7), thin until phase 3: each file a pipeline of the dataset reads, with
// the marking and legal basis its pipeline gave it, and the files added straight to the dataset (the
// unstructured path, ADR-094 step 3). Phase 3 registers a source once, with its own governance.
import { useState } from "react";

import type { StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { AddFiles } from "../../content/AddFiles";
import { Button } from "../../design/primitives/Button";
import { sourceName } from "../../inspector/sourceLocator";

export interface SourcesTabProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  pipelines: readonly StudioRecipeDraft[] | null;
}

function markingOf(p: StudioRecipeDraft): string {
  const classification = (p.handling as { classification?: unknown } | undefined)?.classification;
  return typeof classification === "string" && classification ? classification : "not yet marked";
}

export function SourcesTab({ apiBaseUrl, bearerToken, investigationId, pipelines }: SourcesTabProps) {
  const read = (pipelines ?? []).filter((p) => p.source_location);
  const [adding, setAdding] = useState(false);
  return (
    <div style={{ padding: "var(--sp-16)", display: "grid", gap: "var(--sp-16)", alignContent: "start" }}>
      <section aria-label="Sources" style={{ display: "grid", gap: "var(--sp-8)" }}>
        <h2 style={{ margin: 0, fontSize: "var(--fs-16)" }}>Source tables</h2>
        {pipelines === null && <p className="label">Reading the sources…</p>}
        {pipelines !== null && read.length === 0 && (
          <p className="label">No pipeline reads a source yet. Set a source up on a pipeline&apos;s canvas.</p>
        )}
        {read.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Source</th>
                <th scope="col">Pipeline</th>
                <th scope="col">Marking</th>
                <th scope="col">Legal basis</th>
              </tr>
            </thead>
            <tbody>
              {read.map((p) => (
                <tr key={`${p.recipe_id}:${p.version}`}>
                  <td>{sourceName(p.source_location ?? "")}</td>
                  <td>{p.label}</td>
                  <td>{markingOf(p)}</td>
                  <td>{p.legal_basis || "not given"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section aria-label="Files added to the dataset" style={{ display: "grid", gap: "var(--sp-8)" }}>
        <h2 style={{ margin: 0, fontSize: "var(--fs-16)" }}>Files added to the dataset</h2>
        <p className="label" style={{ margin: 0 }}>
          Images, video and text added straight to the dataset, each a Document with its own marking.
        </p>
        {adding ? (
          <AddFiles
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            // The canvas is not open here; the case's view gains each Document when it opens.
            onDelta={() => undefined}
            onClose={() => setAdding(false)}
          />
        ) : (
          <div>
            <Button onClick={() => setAdding(true)}>Add files</Button>
          </div>
        )}
      </section>
    </div>
  );
}
