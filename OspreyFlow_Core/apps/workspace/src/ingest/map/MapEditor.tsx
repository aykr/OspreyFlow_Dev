// The Map editor (redesign brief §6.5; ADR-140 decision 8): choosing Map collapses the pipeline to a
// strip across the top, so the pipeline is never lost, and opens the row template beneath it in
// three panes: the staged columns (today's source fields, with ◂ ▸ paging and the unmapped columns
// always shown), the template canvas (today's `MapScreen` canvas, kept) and the inspector. A step on
// the strip goes back to the canvas with that step chosen in the drawer.
import type { PipelineGraph, PipelineNode } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { KIND_NAMES } from "../dag/PipelineCanvas";
import { stepsInOrder } from "../dag/GuidedSteps";
import { MapScreen } from "./MapScreen";

export interface MapEditorProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  recipeId: string;
  pipeline: PipelineGraph;
  /** The Map node this editor opened from, marked on the strip as where the person is. */
  mapNodeId: string;
  /** A step on the strip: back to the canvas with it chosen. */
  onStep: (node: PipelineNode) => void;
}

export function MapEditor({ apiBaseUrl, bearerToken, investigationId, recipeId, pipeline, mapNodeId, onStep }: MapEditorProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <nav aria-label="Pipeline strip" style={{ padding: "var(--sp-8) var(--sp-16)", borderBottom: "1px solid var(--border-subtle)" }}>
        <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", gap: "var(--sp-4)", flexWrap: "wrap", alignItems: "center" }}>
          {stepsInOrder(pipeline).map((node, i) => {
            const here = node.id === mapNodeId;
            return (
              <li key={node.id} style={{ display: "flex", gap: "var(--sp-4)", alignItems: "center" }}>
                {i > 0 && <span aria-hidden="true" style={{ color: "var(--text-tertiary)" }}>→</span>}
                {here ? (
                  // Where the person is: said, not offered as a button that would do nothing.
                  <span
                    aria-current="step"
                    style={{ fontSize: "var(--fs-12)", padding: "var(--sp-2) var(--sp-8)", border: "2px solid var(--border-strong)", borderRadius: "var(--r-control)" }}
                  >
                    {`${KIND_NAMES[node.kind] ?? node.kind}: ${node.label}`}
                  </span>
                ) : (
                  <Button onClick={() => onStep(node)}>{`${KIND_NAMES[node.kind] ?? node.kind}: ${node.label}`}</Button>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
      <div style={{ flex: 1, minHeight: 0 }}>
        <MapScreen apiBaseUrl={apiBaseUrl} bearerToken={bearerToken} investigationId={investigationId} recipeId={recipeId} />
      </div>
    </div>
  );
}
