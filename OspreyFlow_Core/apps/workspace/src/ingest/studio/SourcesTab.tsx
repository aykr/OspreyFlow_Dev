// 2 Sources (ADR-140 decision 7, Amendment 4): the dataset's registered sources, each registered once
// with its governance, the register wizard, and a source's own page; the screening lists the dataset
// subscribes to (Amendment 13). Below, the files added straight to the dataset (ADR-094 step 3).
import { useEffect, useMemo, useState } from "react";

import type { SourceTable } from "../../../../../packages/schemas/generated";
import { AddFiles } from "../../content/AddFiles";
import { Button } from "../../design/primitives/Button";
import { sourceName } from "../../inspector/sourceLocator";
import { fetchHandlingScheme, type HandlingScheme } from "../api";
import { listSources } from "../sources/api";
import { RegisterSourceWizard } from "../sources/RegisterSourceWizard";
import { ScreeningLists } from "../sources/ScreeningLists";
import { SourcePage } from "../sources/SourcePage";
import { RightButton, WhyNotLine } from "./rightsGate";

export interface SourcesTabProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The dataset the Studio is open on; `null` when the case loads into none. */
  datasetId: string | null;
  onOpenPipelines: () => void;
  /** A source was registered or its governance edited: the readiness strip reads them again. */
  onSourcesChanged?: () => void;
}

function markingOf(s: SourceTable): string {
  const c = (s.handling as { classification?: unknown } | undefined)?.classification;
  return typeof c === "string" && c ? c : "not marked";
}

export function SourcesTab({ apiBaseUrl, bearerToken, investigationId, datasetId, onOpenPipelines, onSourcesChanged }: SourcesTabProps) {
  const api = useMemo(() => ({ apiBaseUrl, bearerToken }), [apiBaseUrl, bearerToken]);
  const [sources, setSources] = useState<SourceTable[] | null>(null);
  const [scheme, setScheme] = useState<HandlingScheme | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);
  const [open, setOpen] = useState<SourceTable | null>(null);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    if (!datasetId) return;
    setSources(null);
    listSources(api, datasetId)
      .then(setSources)
      .catch((e: Error) => setProblem(e.message));
    fetchHandlingScheme(apiBaseUrl, bearerToken)
      .then(setScheme)
      .catch(() => setScheme(null));
  }, [api, apiBaseUrl, bearerToken, datasetId]);

  if (!datasetId) {
    return <p className="label" style={{ padding: "var(--sp-16)" }}>This case loads into no dataset, so it has no sources.</p>;
  }
  const replace = (s: SourceTable) => setSources((all) => (all ?? []).map((x) => (x.id === s.id ? s : x)));

  return (
    <div style={{ padding: "var(--sp-16)", display: "grid", gap: "var(--sp-16)", alignContent: "start" }}>
      {open ? (
        <SourcePage
          api={api}
          datasetId={datasetId}
          source={open}
          scheme={scheme}
          onBack={() => setOpen(null)}
          onChanged={(s) => {
            setOpen(s);
            replace(s);
            onSourcesChanged?.();
          }}
          onOpenInPipeline={onOpenPipelines}
        />
      ) : registering ? (
        <RegisterSourceWizard
          api={api}
          datasetId={datasetId}
          scheme={scheme}
          registered={(sources ?? []).map((s) => s.location)}
          onCancel={() => setRegistering(false)}
          onRegistered={(made) => {
            setSources((all) => [...(all ?? []), made]);
            setRegistering(false);
            setOpen(made);
            onSourcesChanged?.();
          }}
        />
      ) : (
        <section aria-label="Sources" style={{ display: "grid", gap: "var(--sp-8)" }}>
          <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
            <h2 style={{ margin: 0, fontSize: "var(--fs-16)", flex: 1 }}>Source tables</h2>
            <RightButton right="add_ingest_files" variant="primary" onClick={() => setRegistering(true)}>
              Register a source
            </RightButton>
          </div>
          <p className="label" style={{ margin: 0 }}>
            Each source is registered once, with its marking, legal basis and refresh; every pipeline that reads it
            inherits them.
          </p>
          {/* Listing a dataset's sources needs the same right as registering one (L1.8). */}
          <WhyNotLine right="add_ingest_files" />
          {problem && <p role="alert">{problem}</p>}
          {sources === null && !problem && <p className="label">Reading the sources…</p>}
          {sources?.length === 0 && <p className="label">No source is registered for this dataset yet.</p>}
          {sources && sources.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">File</th>
                  <th scope="col">Marking</th>
                  <th scope="col">Legal basis</th>
                  <th scope="col">Version</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <Button aria-label={`Open source ${s.name}`} onClick={() => setOpen(s)}>
                        {s.name}
                      </Button>
                    </td>
                    <td>{sourceName(s.location)}</td>
                    <td>{markingOf(s)}</td>
                    <td>{s.legal_basis || "not given"}</td>
                    <td>{s.version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
      {!open && !registering && <ScreeningLists api={api} datasetId={datasetId} />}
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
            <RightButton right="add_ingest_files" onClick={() => setAdding(true)}>Add files</RightButton>
          </div>
        )}
      </section>
    </div>
  );
}
