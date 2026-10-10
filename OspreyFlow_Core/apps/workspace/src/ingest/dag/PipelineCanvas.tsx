// The pipeline canvas (ADR-108 phase A: read-only). Every node is a real button — reachable by
// Tab, named by its stage and label — placed by `pipelineLayout` and joined by SVG edges. A chosen
// node's settings read in place; nothing here edits (phase B's editable canvas supersedes this
// surface, not this file's contract: the layout and naming stay).
import { useState } from "react";

import type { PipelineGraph, PipelineNode } from "../../../../../packages/schemas/generated";
import { pipelineLayout } from "./pipelineLayout";

const KIND_NAMES: Record<string, string> = {
  domain_model: "Domain model",
  source: "Source",
  profile: "Profile",
  map: "Map",
  extract: "Extract",
  enrich: "Enrich",
  load: "Load",
};

const COLUMN_WIDTH = 190;
const ROW_HEIGHT = 86;
const NODE_WIDTH = 160;
const NODE_HEIGHT = 56;

export interface PipelineCanvasProps {
  pipeline: PipelineGraph;
}

export function PipelineCanvas({ pipeline }: PipelineCanvasProps) {
  const [chosen, setChosen] = useState<PipelineNode | null>(null);
  const allNodes = pipeline.nodes ?? [];
  const allEdges = pipeline.edges ?? [];
  const placed = new Map(pipelineLayout(pipeline).map((p) => [p.id, p]));
  const columns = Math.max(0, ...[...placed.values()].map((p) => p.column)) + 1;
  const rows = Math.max(0, ...[...placed.values()].map((p) => p.row)) + 1;
  const width = columns * COLUMN_WIDTH;
  const height = rows * ROW_HEIGHT;

  const centre = (id: string) => {
    const at = placed.get(id);
    if (!at) return { x: 0, y: 0 };
    return {
      x: at.column * COLUMN_WIDTH + NODE_WIDTH / 2,
      y: at.row * ROW_HEIGHT + NODE_HEIGHT / 2,
    };
  };

  return (
    <div style={{ display: "grid", gap: "var(--sp-12)" }}>
      <div
        role="group"
        aria-label="Pipeline"
        style={{ position: "relative", width, height, minHeight: NODE_HEIGHT }}
      >
        <svg
          aria-hidden="true"
          width={width}
          height={height}
          style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
        >
          {allEdges.map((edge) => {
            const a = centre(edge.source);
            const b = centre(edge.target);
            return (
              <line
                key={`${edge.source}->${edge.target}`}
                x1={a.x + NODE_WIDTH / 2}
                y1={a.y}
                x2={b.x - NODE_WIDTH / 2}
                y2={b.y}
                stroke="var(--border-strong)"
                strokeWidth={1.5}
              />
            );
          })}
        </svg>
        {allNodes.map((node) => {
          const at = placed.get(node.id);
          if (!at) return null;
          const kind = KIND_NAMES[node.kind] ?? node.kind;
          return (
            <button
              key={node.id}
              type="button"
              aria-label={`${kind}: ${node.label}`}
              aria-pressed={chosen?.id === node.id}
              onClick={() => setChosen(node)}
              style={{
                position: "absolute",
                left: at.column * COLUMN_WIDTH,
                top: at.row * ROW_HEIGHT,
                width: NODE_WIDTH,
                height: NODE_HEIGHT,
                display: "grid",
                alignContent: "center",
                gap: "var(--sp-2)",
                textAlign: "left",
                padding: "var(--sp-8)",
                font: "inherit",
                background: "var(--surface-raised)",
                color: "var(--text-primary)",
                border:
                  chosen?.id === node.id
                    ? "2px solid var(--border-strong)"
                    : "1px solid var(--border-subtle)",
                borderRadius: "var(--r-control)",
                cursor: "pointer",
              }}
            >
              <span style={{ color: "var(--text-secondary)", fontSize: "var(--fs-12)" }}>{kind}</span>
              <span
                style={{
                  fontSize: "var(--fs-13)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {node.label}
              </span>
            </button>
          );
        })}
      </div>
      {chosen && (
        <section
          aria-label="Node settings"
          style={{
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--r-panel)",
            padding: "var(--sp-12)",
            display: "grid",
            gap: "var(--sp-4)",
          }}
        >
          <p style={{ margin: 0, fontWeight: 600 }}>
            {(KIND_NAMES[chosen.kind] ?? chosen.kind) + ": " + chosen.label}
          </p>
          {Object.entries(chosen.config ?? {}).length === 0 && (
            <p style={{ margin: 0, color: "var(--text-tertiary)" }}>This stage has no settings.</p>
          )}
          <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: "var(--sp-2) var(--sp-12)" }}>
            {Object.entries(chosen.config ?? {}).map(([key, value]) => (
              <div key={key} style={{ display: "contents" }}>
                <dt style={{ color: "var(--text-secondary)" }}>{key}</dt>
                <dd className="value" style={{ margin: 0 }}>
                  {value === null || value === undefined ? "—" : String(value)}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </div>
  );
}
