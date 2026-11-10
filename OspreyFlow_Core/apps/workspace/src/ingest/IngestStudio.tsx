// The Ingest Studio as four places with one method (ADR-140 decision 1, the owner's rulings R1 and
// R7): 1 Model, 2 Sources, 3 Pipelines, 4 Runs, under a readiness strip, opened on a dataset. Until
// phase 5 gives the Studio routes of its own, the dataset is reached through one of the person's
// cases that loads into it (ADR-140 Amendment 2: "Dataset label, case behind"), so every route,
// role and access check is the case's, exactly as before.
import { useEffect, useState } from "react";

import { NEEDS_YOU_WORDS, proposedIn, readNeedsYou, type NeedsYou } from "../admin/needsYou/needsYouApi";
import { onOpening, peekOpening, takeOpening } from "../admin/needsYou/openings";
import { Button } from "../design/primitives/Button";
import { Select } from "../design/primitives/Select";
import { Tabs } from "../design/primitives/Tabs";
import { HELP_TITLE } from "../help/roles";
import { RolesHelpPage } from "../help/RolesHelpPage";
import { type CaseListing, listCases } from "../investigation/cases";
import { PipelineStudio } from "./dag/PipelineStudio";
import { ReleasesTab } from "./releases/ReleasesTab";
import { RunsTab } from "./runs/RunsTab";
import { caseForDataset, currentDataset, studioDatasets } from "./studio/datasets";
import { ModelProposals } from "../linktypes/ModelProposals";
import { ModelTab } from "./studio/ModelTab";
import { ReadinessStrip } from "./studio/ReadinessStrip";
import { StudioRights, WhyNotLine } from "./studio/rightsGate";
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
  /** The person's rights (`GET /v1/me/rights`): each action that needs a right says why and who can
   * when the person lacks it (ADR-145 Amendment 4 decision 12; L1.8), and `revert_loads` shows a load's
   * revert command. */
  rights?: ReadonlySet<string> | null;
  /** The person's user name, for the revert command's `--reverted-by`. */
  username?: string | null;
}

export type StudioPlace = "model" | "sources" | "pipelines" | "runs" | "releases";

export const STUDIO_PLACES: { id: StudioPlace; label: string }[] = [
  { id: "model", label: "1 Model" },
  { id: "sources", label: "2 Sources" },
  { id: "pipelines", label: "3 Pipelines" },
  { id: "runs", label: "4 Runs" },
  // ADR-140 Amendment 9 decision 4: a dataset's release between environments, as YAML.
  { id: "releases", label: "5 Releases" },
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
    <StudioRights.Provider value={rights ?? null}>
    <Studio
      apiBaseUrl={apiBaseUrl}
      bearerToken={bearerToken}
      investigationId={investigationId}
      onOpenCase={onOpenCase}
      rights={rights ?? null}
      username={username ?? null}
    />
    </StudioRights.Provider>
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
  // *Roles, teams and Authors*, the one help page, opened from the Studio as from Admin (decision 12).
  const [helpOpen, setHelpOpen] = useState(false);
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
  // ADR-145 decision 11 (A2), ADR-090 Amendment 4 (L2.7): the proposed link types this person may
  // decide in this dataset, as the Conduit counted them for them (never one above their clearance).
  const [needs, setNeeds] = useState<NeedsYou | null>(null);
  const [needsUnread, setNeedsUnread] = useState(false);
  const [decisions, setDecisions] = useState(0);
  useEffect(() => {
    let cancelled = false;
    readNeedsYou(apiBaseUrl, bearerToken)
      .then((found) => {
        if (cancelled) return;
        setNeeds(found);
        setNeedsUnread(false);
      })
      .catch(() => {
        if (cancelled) return;
        setNeeds(null);
        setNeedsUnread(true); // said, never shown as none to decide (rule 2)
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, decisions]);
  const proposed = proposedIn(needs, datasetId);
  const tabs = STUDIO_PLACES.map((t) => (t.id === "model" && proposed > 0 ? { ...t, label: `1 Model · ${proposed} proposed` } : t));
  // *Needs you*'s proposals open this dataset's Model tab (`admin/needsYou/openings.ts`).
  useEffect(() => {
    if (datasetId === null) return;
    const take = () => {
      // Taken only when it is this dataset's: one for another is left for the reload into it.
      if (peekOpening("studio")?.datasetId !== datasetId) return;
      takeOpening("studio");
      setPlace("model");
    };
    take();
    return onOpening(take);
  }, [datasetId]);

  function choose(id: string) {
    const caseId = caseForDataset(cases ?? [], id, investigationId);
    if (caseId) {
      setProblem(null);
      if (caseId !== investigationId) onOpenCase(caseId);
    } else {
      setProblem("None of your cases loads into that dataset, so the Studio cannot open on it.");
    }
  }

  // The help page is drawn over the Studio, never instead of it: an open pipeline, map or form keeps
  // what was typed while the page is read (the lane review of L1.8).
  return (
    <>
    {helpOpen && <RolesHelpPage backTo="the Ingest Studio" onBack={() => setHelpOpen(false)} />}
    <div hidden={helpOpen} style={{ display: helpOpen ? "none" : "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
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
        <span style={{ flex: 1 }} />
        <Button onClick={() => setHelpOpen(true)}>{HELP_TITLE}</Button>
      </div>
      <ReadinessStrip packs={servingCase?.domains} pipelines={data.pipelines} sources={sources} runs={data.runs} />
      {proposed > 0 && place !== "model" && (
        <p className="caption studio-proposals-reminder" style={{ margin: 0, padding: "var(--sp-4) var(--sp-16)" }}>
          <button type="button" className="btn" aria-describedby="studio-proposals-tip" onClick={() => setPlace("model")}>
            {NEEDS_YOU_WORDS.reminder(proposed)}
          </button>{" "}
          <span id="studio-proposals-tip" role="note">{NEEDS_YOU_WORDS.reminderTip}</span>
        </p>
      )}
      {needsUnread && (
        <p className="caption" role="status" style={{ margin: 0, padding: "var(--sp-4) var(--sp-16)" }}>
          {NEEDS_YOU_WORDS.unreadProposals}
        </p>
      )}
      <Tabs tabs={tabs} activeId={place} onChange={(id) => setPlace(id as StudioPlace)} />
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        {data.problem && <p role="alert" style={{ padding: "var(--sp-16)" }}>{data.problem}</p>}
        {place === "model" && <ModelTab datasetName={datasetName} packs={servingCase?.domains} />}
        {place === "model" && datasetId && (
          <div style={{ padding: "0 var(--sp-16) var(--sp-16)", maxWidth: 720 }}>
            {/* The proposals' own panel hides itself from whoever cannot accept types; the Studio says
                why and who can instead (L1.8). */}
            {rights && !rights.has("accept_types") ? (
              <section aria-label="Proposed link types" style={{ display: "grid", gap: "var(--sp-8)" }}>
                <h3 style={{ margin: 0, fontSize: "var(--fs-14)" }}>Proposed link types</h3>
                <WhyNotLine right="accept_types" />
              </section>
            ) : (
              <ModelProposals apiBaseUrl={apiBaseUrl} bearerToken={bearerToken} datasetId={datasetId} datasetName={datasetName} onDecided={() => setDecisions((n) => n + 1)} />
            )}
          </div>
        )}
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
        {place === "releases" && (
          <ReleasesTab
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            datasetId={datasetId}
            datasetName={datasetName}
            rights={rights ?? null}
          />
        )}
      </div>
    </div>
    </>
  );
}
