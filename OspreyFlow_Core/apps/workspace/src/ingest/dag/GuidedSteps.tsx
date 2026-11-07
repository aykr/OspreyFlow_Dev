// Guided mode's numbered list (ADR-140 decision 3; brief §6): the pipeline's steps in the order they
// run, each opening the same drawer the canvas opens. A step guided mode does not offer (an expert
// step: SQL transform and Fuzzy match from phase 8) is listed, labelled and opened read-only; it is
// never hidden, so a pipeline edited in expert mode reads whole here. The step's button carries the
// same name as its node on the canvas ("Source: Call log"); the number is the list's own marker, so
// one keyboard path serves both modes.
import type { PipelineGraph, PipelineNode } from "../../../../../packages/schemas/generated";
import { KIND_NAMES } from "./PipelineCanvas";
import { pipelineLayout } from "./pipelineLayout";

/** The closed catalogue (ADR-140 decision 9) plus today's stages: what guided mode edits. */
export const GUIDED_KINDS: ReadonlySet<string> = new Set([
  "domain_model", "source", "profile", "map", "extract", "enrich", "load",
  "lookup", "join", "filter", "derive", "union", "dedupe",
]);  // prettier-ignore

export function isExpertStep(node: Pick<PipelineNode, "kind">): boolean {
  return !GUIDED_KINDS.has(node.kind);
}

/** The steps in the order they run: by column (longest path from a root), then row. */
export function stepsInOrder(pipeline: PipelineGraph): PipelineNode[] {
  const placed = new Map(pipelineLayout(pipeline).map((p) => [p.id, p]));
  return [...(pipeline.nodes ?? [])].sort((a, b) => {
    const pa = placed.get(a.id)!;
    const pb = placed.get(b.id)!;
    return pa.column - pb.column || pa.row - pb.row;
  });
}

export interface GuidedStepsProps {
  pipeline: PipelineGraph;
  selectedId: string | null;
  onSelect: (node: PipelineNode) => void;
}

export function GuidedSteps({ pipeline, selectedId, onSelect }: GuidedStepsProps) {
  return (
    <ol aria-label="Steps" style={{ margin: 0, paddingLeft: "var(--sp-24)", display: "grid", gap: "var(--sp-4)" }}>
      {stepsInOrder(pipeline).map((node) => {
        const kind = KIND_NAMES[node.kind] ?? node.kind;
        const expert = isExpertStep(node);
        return (
          <li key={node.id} style={{ paddingLeft: "var(--sp-4)" }}>
            <span style={{ display: "inline-flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
              <button
                type="button"
                className="guided-step"
                aria-pressed={selectedId === node.id}
                onClick={() => onSelect(node)}
                style={{
                  font: "inherit",
                  textAlign: "left",
                  padding: "var(--sp-4) var(--sp-8)",
                  minHeight: 32,
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                  border: selectedId === node.id ? "2px solid var(--border-strong)" : "1px solid var(--border-subtle)",
                  borderRadius: "var(--r-control)",
                  cursor: "pointer",
                }}
              >
                {`${kind}: ${node.label}`}
              </button>
              {expert && <span className="label">Expert step, read-only here</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
