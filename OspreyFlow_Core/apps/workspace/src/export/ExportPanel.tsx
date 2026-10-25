// The export drawer — `02_GLASS_FRONTEND.md` §10, Phase 8 Stage 4e. Three artefact-shape
// triggers, the handling-gate UI (named blocker list, justification/originator-reference
// override), the manifest and mark display, and the refusal path — all against one gate
// (`services/api/export.py::submit_export`'s own docstring: "there is one gate, not three").
//
// **Errors surface as an inline banner, not `ActionErrorOverlay`** — the same reasoning
// `assessment/JudgementsPanel.tsx`'s own header comment already gives: this drawer has no cursor
// position or canvas selection for a failure to anchor to (`02_GLASS_FRONTEND.md` §4.1's own
// "panel inline banner — non-canvas surfaces" rule).
//
// **Phase 8 Stage 4h now builds the downloadable half this header comment used to disclose as
// missing.** Chart bytes come from the caller's own `onExportChartImage` (delegating to
// `GlassCanvasHandle.exportImage`/`export/chartExport.ts`'s `captureChartImage`, since this
// component has no Sigma instance of its own); subgraph and report bytes are assembled directly
// here via `export/subgraphExport.ts`/`export/reportExport.ts`, both pure and unit-tested. This
// drawer still submits the real selection to the real gate first — the safety-critical half A15
// already tested — and only builds/downloads the artefact once that gate's own response
// (`ExportResult`) confirms the export is allowed.
import type Graph from "graphology";
import { useState } from "react";

import type { Node } from "../../../../packages/schemas/generated";
import { listAssumptions, listGaps, listJudgements, getYardstick } from "../assessment/api";
import { nodeLabel } from "../canvas/nodeAttributes";
import { caseLabel, listCases } from "../investigation/cases";
import { Button } from "../design/primitives/Button";
import { Drawer } from "../design/primitives/Drawer";
import { Input } from "../design/primitives/Input";
import { Select } from "../design/primitives/Select";
import {
  ExportBlockedApiError,
  getResolutionThreshold,
  OverrideRequiredApiError,
  submitExport,
  type BlockedItem,
  type ExportItemRequest,
  manifestSentence,
  type ExportMark,
  type ExportResult,
} from "./api";
import { buildReportArtefact } from "./reportExport";
import { buildSubgraphArtefact, serialiseSubgraphArtefact } from "./subgraphExport";
import { triggerDownload } from "./triggerDownload";

export interface ExportPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The working set's own graphology instance — the same instance `GlassCanvas`/`JudgementsPanel`
   * already read from, never a second copy. */
  graph: Graph;
  open: boolean;
  onClose: () => void;
  /** The chart artefact's own real capture path — delegates to `GlassCanvasHandle.exportImage`.
   * Optional so the keyboard harness (which mounts this drawer with no live `GlassCanvas`/Sigma
   * instance at all) can supply a fake in its place; a real host always passes it. */
  onExportChartImage?: (mark: ExportMark) => Promise<Blob>;
}

type ArtefactKind = "chart" | "subgraph" | "report";

function itemLabel(graph: Graph, id: string, kind: "node" | "edge"): string {
  if (kind === "node") {
    if (!graph.hasNode(id)) return id;
    // Named as the canvas names it; a labeller of this panel's own once knew only `family_name`
    // and sent a document to the gate by its content id (9 October 2026).
    const data = graph.getNodeAttribute(id, "data") as Node | undefined;
    if (!data) return id;
    return `${data.type}: ${nodeLabel({ ...data, id })}`;
  }
  if (!graph.hasEdge(id)) return id;
  const data = graph.getEdgeAttribute(id, "data") as { type?: string } | undefined;
  return data?.type ? `${data.type} edge` : id;
}

/** The current working set — nodes and edges, each carrying its own real `handling` block — the
 * `subgraph` trigger's own source (`02_GLASS_FRONTEND.md` §10.1: "the current working set"). A
 * `chart` export also submits this selection today, for the reason the module docstring above
 * states: the gate evaluates the same selection regardless of which artefact shape eventually
 * renders it, and only the shape differs, not what gets checked. */
function selectionItems(graph: Graph): ExportItemRequest[] {
  const items: ExportItemRequest[] = [];
  graph.forEachNode((id) => {
    const data = graph.getNodeAttribute(id, "data") as { handling?: Record<string, unknown> };
    if (!data?.handling) return;
    items.push({ id, kind: "node", handling: data.handling, label: itemLabel(graph, id, "node") });
  });
  graph.forEachEdge((id) => {
    const data = graph.getEdgeAttribute(id, "data") as { handling?: Record<string, unknown> };
    if (!data?.handling) return;
    items.push({ id, kind: "edge", handling: data.handling, label: itemLabel(graph, id, "edge") });
  });
  return items;
}

function blockedListLabel(item: BlockedItem): string {
  const reasonLabel =
    item.reason === "consult_originator"
      ? "consult originator"
      : item.reason === "citation_unverifiable"
        ? "evidence not verifiable"
        : "access denied";
  return `${item.label} — ${reasonLabel}`;
}

/** The downloadable file's own name — one per shape, timestamped so repeat exports of the same
 * investigation do not collide in a Downloads folder. */
function artefactFilename(kind: ArtefactKind, mark: ExportMark): string {
  const extension = kind === "chart" ? "png" : kind === "subgraph" ? "json" : "html";
  const stamp = mark.exported_at.replace(/[:.]/g, "-");
  return `osprey-${kind}-${mark.investigation_id}-${stamp}.${extension}`;
}

export function ExportPanel({
  apiBaseUrl,
  bearerToken,
  investigationId,
  graph,
  open,
  onClose,
  onExportChartImage,
}: ExportPanelProps) {
  const [artefactKind, setArtefactKind] = useState<ArtefactKind>("subgraph");
  const [justification, setJustification] = useState("");
  const [originatorReference, setOriginatorReference] = useState("");
  const [blocked, setBlocked] = useState<BlockedItem[] | null>(null);
  const [overridable, setOverridable] = useState(false);
  const [result, setResult] = useState<ExportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  /** Builds the real artefact bytes for `kind` and triggers a download — called only once
   * `submitExport` has already confirmed the gate allows it, so this never produces an artefact
   * the gate has not itself already cleared. Errors here surface as the same inline banner a
   * failed submit already uses, per this drawer's own established error-handling convention. */
  async function downloadArtefact(kind: ArtefactKind, exported: ExportResult): Promise<void> {
    if (kind === "chart") {
      if (!onExportChartImage) {
        throw new Error("chart export: no chart-capture callback was supplied");
      }
      const blob = await onExportChartImage(exported.mark);
      triggerDownload(blob, artefactFilename(kind, exported.mark));
      return;
    }
    if (kind === "subgraph") {
      const artefact = buildSubgraphArtefact(graph, exported.mark, exported.manifest);
      const blob = new Blob([serialiseSubgraphArtefact(artefact)], { type: "application/json" });
      triggerDownload(blob, artefactFilename(kind, exported.mark));
      return;
    }
    const [judgements, gaps, assumptions, yardstick, cases] = await Promise.all([
      listJudgements(apiBaseUrl, bearerToken, investigationId),
      listGaps(apiBaseUrl, bearerToken, investigationId),
      listAssumptions(apiBaseUrl, bearerToken, investigationId),
      getYardstick(apiBaseUrl, bearerToken),
      // The case's name for the report's title; without it, the title falls back to the id.
      listCases(apiBaseUrl, bearerToken).catch(() => []),
    ]);
    const current = cases.find((entry) => entry.id === investigationId);
    const html = buildReportArtefact({
      caseName: current ? caseLabel(current) : undefined,
      // A cited node on the canvas is named as the canvas names it; one not on it, by its id.
      citationLabel: (id) => itemLabel(graph, id, "node"),
      judgements,
      gaps,
      assumptions,
      yardstick,
      mark: exported.mark,
      manifest: exported.manifest,
    });
    const blob = new Blob([html], { type: "text/html" });
    triggerDownload(blob, artefactFilename(kind, exported.mark));
  }

  function reset(): void {
    setBlocked(null);
    setOverridable(false);
    setResult(null);
    setError(null);
    setJustification("");
    setOriginatorReference("");
  }

  async function handleSubmit(): Promise<void> {
    setSubmitting(true);
    setError(null);
    try {
      const resolutionThreshold = await getResolutionThreshold(
        apiBaseUrl,
        bearerToken,
        investigationId,
      );
      const items = selectionItems(graph);
      const judgementIds =
        artefactKind === "report"
          ? (await listJudgements(apiBaseUrl, bearerToken, investigationId)).map((j) => j.id)
          : [];

      const exported = await submitExport(apiBaseUrl, bearerToken, investigationId, {
        artefact_kind: artefactKind,
        items,
        judgement_ids: judgementIds,
        resolution_threshold: resolutionThreshold,
        justification: justification || undefined,
        originator_reference: originatorReference || undefined,
      });
      setBlocked(null);
      setOverridable(false);
      setResult(exported);
      await downloadArtefact(artefactKind, exported);
    } catch (err) {
      if (err instanceof OverrideRequiredApiError) {
        setBlocked(err.blocked);
        setOverridable(true);
        setError(null);
      } else if (err instanceof ExportBlockedApiError) {
        setBlocked(err.blocked);
        setOverridable(false);
        setError(null);
      } else {
        setBlocked(null);
        setOverridable(false);
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = !overridable || (justification.trim().length > 0 && originatorReference.trim().length > 0);

  return (
    <Drawer
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Export"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
        <label>
          Artefact
          <Select
            value={artefactKind}
            onChange={(e) => setArtefactKind(e.target.value as ArtefactKind)}
          >
            <option value="chart">Chart</option>
            <option value="subgraph">Subgraph</option>
            <option value="report">Report</option>
          </Select>
        </label>

        {error && (
          <p role="alert" style={{ color: "var(--error)" }}>
            {error}
          </p>
        )}

        {/* A15's own literal assertion: a blocking item is named, not a generic "export
         * blocked" message (`02_GLASS_FRONTEND.md` §10.2). Every reason renders here, including
         * the never-overridable ones — an analyst should see the whole picture on one attempt. */}
        {blocked && blocked.length > 0 && (
          <div role="alert" style={{ color: "var(--error)" }}>
            <p style={{ margin: 0 }}>
              {overridable
                ? "The following item requires an originator's sign-off before this export can proceed:"
                : "The following item cannot be included in this export:"}
            </p>
            <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
              {blocked.map((item) => (
                <li key={item.id} className="value">
                  {blockedListLabel(item)}
                </li>
              ))}
            </ul>
          </div>
        )}

        {overridable && (
          <>
            <label>
              Justification
              <Input value={justification} onChange={(e) => setJustification(e.target.value)} />
            </label>
            <label>
              Originator reference
              <Input
                value={originatorReference}
                onChange={(e) => setOriginatorReference(e.target.value)}
              />
            </label>
          </>
        )}

        {result && (
          <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "var(--sp-8)" }}>
            {manifestSentence(result.manifest) !== null && (
              // The status bar's standing sentence (ADR-124 decision 5), a yes or no and never a
              // number, while the case holds material this exporter may not view and the
              // deployment discloses it (ADR-045); nothing otherwise.
              <p className="value">{manifestSentence(result.manifest)}</p>
            )}
            <p className="label" style={{ margin: 0 }}>
              {result.mark.osprey_mark} · {result.mark.handling_level} ·{" "}
              {new Date(result.mark.exported_at).toLocaleString()}
            </p>
          </div>
        )}

        {/* Disabled until valid — the same pattern `assessment/JudgementsPanel.tsx`'s own Save
         * button already establishes, applied here to the override form's own two required
         * fields (`02_GLASS_FRONTEND.md` §10.2). */}
        <Button
          variant="primary"
          disabled={submitting || !canSubmit}
          onClick={() => void handleSubmit()}
        >
          {submitting ? "Exporting…" : "Export"}
        </Button>
      </div>
    </Drawer>
  );
}
