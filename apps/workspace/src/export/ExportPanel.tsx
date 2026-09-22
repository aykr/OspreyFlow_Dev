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
// **Rendering the three artefact shapes' own bytes (a PNG, an assembled report document) is not
// this component's job — disclosed, not silently narrowed.** `services/api/export.py`'s own
// module docstring names Stage 4e as the renderer, but no chart-image or report-assembly engine
// exists anywhere in `apps/workspace` yet (`GlassCanvasHandle` has no `exportImage` method;
// `@sigma/export-image` is listed as a dependency, `02_GLASS_FRONTEND.md` §1, never wired to a
// component). This drawer submits the real selection to the real gate and renders the real
// mark/manifest/ledger response — the safety-critical half A15 actually tests — for all three
// `artefact_kind` values; producing a downloadable file per shape is real, separately-owned work,
// recorded in `07_BUILD_PLAN.md`'s own Stage 4e entry rather than stubbed out here to look done.
import type Graph from "graphology";
import { useState } from "react";

import { listJudgements } from "../assessment/api";
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
  type ExportResult,
} from "./api";

export interface ExportPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The working set's own graphology instance — the same instance `GlassCanvas`/`JudgementsPanel`
   * already read from, never a second copy. */
  graph: Graph;
  open: boolean;
  onClose: () => void;
}

type ArtefactKind = "chart" | "subgraph" | "report";

function itemLabel(graph: Graph, id: string, kind: "node" | "edge"): string {
  if (kind === "node") {
    if (!graph.hasNode(id)) return id;
    const data = graph.getNodeAttribute(id, "data") as
      | { type?: string; properties?: Record<string, unknown> }
      | undefined;
    const name =
      (data?.properties?.family_name as string | undefined) ??
      (data?.properties?.value_normalised as string | undefined);
    return name ? `${data?.type ?? "Node"}: ${name}` : id;
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

export function ExportPanel({
  apiBaseUrl,
  bearerToken,
  investigationId,
  graph,
  open,
  onClose,
}: ExportPanelProps) {
  const [artefactKind, setArtefactKind] = useState<ArtefactKind>("subgraph");
  const [justification, setJustification] = useState("");
  const [originatorReference, setOriginatorReference] = useState("");
  const [blocked, setBlocked] = useState<BlockedItem[] | null>(null);
  const [overridable, setOverridable] = useState(false);
  const [result, setResult] = useState<ExportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
            {result.manifest.policy === "disclose" && result.manifest.withheld_count !== null && (
              // The exact status-bar phrasing (`02_GLASS_FRONTEND.md` §2/§10.3) — "N hidden by
              // handling" — not a second wording for the same fact.
              <p className="value">{result.manifest.withheld_count} hidden by handling</p>
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
