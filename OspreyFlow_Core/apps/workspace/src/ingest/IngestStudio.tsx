// The Ingest Studio as four places with one method (ADR-140 decision 1, the owner's rulings R1 and
// R7): 1 Model, 2 Sources, 3 Pipelines, 4 Runs, under a readiness strip, opened on a dataset. Until
// phase 5 gives the Studio routes of its own, the dataset is reached through one of the person's
// cases that loads into it (ADR-140 Amendment 2: "Dataset label, case behind"), so every route,
// role and access check is the case's, exactly as before.
import { useEffect, useState } from "react";

import { Select } from "../design/primitives/Select";
import { Tabs } from "../design/primitives/Tabs";
import { type CaseListing, listCases } from "../investigation/cases";
import { PipelineStudio } from "./dag/PipelineStudio";
import { RunsTab } from "./runs/RunsTab";
import { caseForDataset, currentDataset, studioDatasets } from "./studio/datasets";
import { ModelProposals } from "../linktypes/ModelProposals";
import { ModelTab } from "./studio/ModelTab";
import { ReadinessStrip } from "./studio/ReadinessStrip";
import { SourcesTab } from "./studio/SourcesTab";
import { useRegisteredSources } from "./studio/useRegisteredSources";
import { useStudioData } from "./studio/useStudioData";

export interface IngestStudioProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** The case the Studio works through (ADR-099 Amendment 3: a recipe and a source file belong to
   * the dataset of the case they are made in). */
  investigationId: string | null;
  /** Opening the case that serves another dataset, chosen in the switcher. */
  onOpenCase: (id: string) => void;
  /** The person's rights (`GET /v1/me/rights`): `revert_loads` shows a load's revert command. */
  rights?: ReadonlySet<string> | null;
  /** The person's user name, for the revert command's `--reverted-by`. */
  username?: string | null;
}

export type StudioPlace = "model" | "sources" | "pipelines" | "runs";

export const STUDIO_PLACES: { id: StudioPlace; label: string }[] = [
  { id: "model", label: "1 Model" },
  { id: "sources", label: "2 Sources" },
  { id: "pipelines", label: "3 Pipelines" },
  { id: "runs", label: "4 Runs" },
];

export function IngestStudio({ apiBaseUrl, bearerToken, investigationId, onOpenCase, rights, username }: IngestStudioProps) {
  if (!investigationId) {
    return (
      <p className="label" style={{ padding: "var(--sp-16)" }}>
        Open a case to use the Ingest Studio: it works on the dataset the case loads into.
      </p>
    );
  }
  return (
    <Studio
      apiBaseUrl={apiBaseUrl}
      bearerToken={bearerToken}
      investigationId={investigationId}
      onOpenCase={onOpenCase}
      rights={rights ?? null}
      username={username ?? null}
    />
  );
}

function Studio({
  apiBaseUrl,
  bearerToken,
  investigationId,
  onOpenCase,
  rights,
  username,
}: Omit<IngestStudioProps, "investigationId"> & { investigationId: string }) {
  // The entry point is the person's (R7); Pipelines is where they were before the redesign.
  const [place, setPlace] = useState<StudioPlace>("pipelines");
  const [cases, setCases] = useState<CaseListing[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const data = useStudioData(apiBaseUrl, bearerToken, investigationId);
  // Read again when the Sources tab registers or edits one, so the strip counts what the tab lists.
  const [sourcesGeneration, setSourcesGeneration] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listCases(apiBaseUrl, bearerToken)
      .then((found) => !cancelled && setCases(found))
      .catch(() => !cancelled && setCases([]));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken]);

  const datasets = studioDatasets(cases ?? [], investigationId);
  const datasetId = currentDataset(cases ?? [], investigationId);
  const dataset = datasets.find((d) => d.id === datasetId);
  const datasetName = dataset?.name ?? "this dataset";
  const servingCase = (cases ?? []).find((c) => c.id === investigationId);
  const sources = useRegisteredSources(apiBaseUrl, bearerToken, datasetId, cases !== null, sourcesGeneration);

  function choose(id: string) {
    const caseId = caseForDataset(cases ?? [], id, investigationId);
    if (caseId) {
      setProblem(null);
      if (caseId !== investigationId) onOpenCase(caseId);
    } else {
      setProblem("None of your cases loads into that dataset, so the Studio cannot open on it.");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-16)",
          padding: "var(--sp-8) var(--sp-16)",
          borderBottom: "1px solid var(--border-subtle)",
          flexWrap: "wrap",
        }}
      >
        <label style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
          <span className="label">Dataset</span>
          <Select value={datasetId ?? ""} onChange={(e) => choose(e.target.value)} disabled={datasets.length === 0}>
            {datasetId === null && <option value="">{cases === null ? "Reading…" : "This case loads into no dataset"}</option>}
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        </label>
        {servingCase && (
          <span className="label">{`Working through the case “${servingCase.name}”: what loads here goes into ${datasetName}.`}</span>
        )}
        {problem && <span role="alert">{problem}</span>}
      </div>
      <ReadinessStrip packs={servingCase?.domains} pipelines={data.pipelines} sources={sources} runs={data.runs} />
      <Tabs tabs={STUDIO_PLACES} activeId={place} onChange={(id) => setPlace(id as StudioPlace)} />
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        {data.problem && <p role="alert" style={{ padding: "var(--sp-16)" }}>{data.problem}</p>}
        {place === "model" && <ModelTab datasetName={datasetName} packs={servingCase?.domains} />}
        {place === "model" && datasetId && <div style={{ padding: "0 var(--sp-16) var(--sp-16)", maxWidth: 720 }}><ModelProposals apiBaseUrl={apiBaseUrl} bearerToken={bearerToken} datasetId={datasetId} datasetName={datasetName} /></div>}
        {place === "sources" && (
          <SourcesTab
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            datasetId={datasetId}
            onOpenPipelines={() => setPlace("pipelines")}
            onSourcesChanged={() => setSourcesGeneration((g) => g + 1)}
          />
        )}
        {place === "pipelines" && (
          <PipelineStudio apiBaseUrl={apiBaseUrl} bearerToken={bearerToken} investigationId={investigationId} onChanged={data.reload} username={username ?? null} rights={rights ?? null} />
        )}
        {place === "runs" && (
          <RunsTab
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            datasetId={datasetId}
            datasetName={datasetName}
            pipelines={data.pipelines}
            runs={data.runs}
            level={servingCase?.level ?? null}
            canRevert={rights?.has("revert_loads") ?? false}
            username={username ?? null}
            onChanged={data.reload}
          />
        )}
      </div>
    </div>
  );
}
