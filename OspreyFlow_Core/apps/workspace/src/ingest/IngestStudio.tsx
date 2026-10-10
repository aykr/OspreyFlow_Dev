// The Ingest Studio (ADR-108 phase B): the pipelines home and canvas are the Studio — the 1–9
// step wizard is replaced outright (the owner's ruling Q6). The unstructured path (ADR-094 step 3,
// files straight into the case) keeps its own tab, unchanged.
import { useState } from "react";

import { AddFiles } from "../content/AddFiles";
import { Tabs } from "../design/primitives/Tabs";
import { CaseSwitcher } from "../investigation/CaseSwitcher";
import { PipelineStudio } from "./dag/PipelineStudio";

export interface IngestStudioProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** ADR-099 Amendment 3: a recipe and a source file belong to the dataset of the case they are
   * made in, so the studio works only within a case. */
  investigationId: string | null;
  /** Switching to another case, or one just created, from the studio (owner, 29 September 2026). */
  onOpenCase: (id: string) => void;
}

type Stage = "pipelines" | "files";

export function IngestStudio({ apiBaseUrl, bearerToken, investigationId, onOpenCase }: IngestStudioProps) {
  const [stage, setStage] = useState<Stage>("pipelines");

  if (!investigationId) {
    return (
      <p className="label" style={{ padding: "var(--sp-16)" }}>
        Open a case to use the Ingest Studio: what it loads goes into the case&apos;s data.
      </p>
    );
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
        }}
      >
        <span className="label">Data loaded from this studio goes into</span>
        <CaseSwitcher
          apiBaseUrl={apiBaseUrl}
          bearerToken={bearerToken}
          currentId={investigationId}
          onOpen={onOpenCase}
        />
      </div>
      <Tabs
        tabs={[
          { id: "pipelines", label: "Pipelines" },
          { id: "files", label: "Files" },
        ]}
        activeId={stage}
        onChange={(id) => setStage(id === "files" ? "files" : "pipelines")}
      />
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        {stage === "pipelines" && (
          <PipelineStudio apiBaseUrl={apiBaseUrl} bearerToken={bearerToken} investigationId={investigationId} />
        )}
        {stage === "files" && (
          <AddFiles
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            // The canvas is not open here; the case's view gains each Document when it opens.
            onDelta={() => undefined}
            onClose={() => setStage("pipelines")}
          />
        )}
      </div>
    </div>
  );
}
