// The legend (ADR-097 step 2, design review item 10), at the canvas's lower left: each type now in
// view, drawn as the canvas draws it, with how many there are, most first. It folds to its title, and
// the list stays in the page while folded.
import { useState } from "react";

import { TypeChip } from "../inspector/TypeChip";
import type { EntityVisual } from "../ontology/schema";

export interface LegendType {
  type: string;
  count: number;
  visual?: EntityVisual;
}

export function CanvasLegend({ types }: { types: readonly LegendType[] }) {
  const [open, setOpen] = useState(true);
  if (types.length === 0) return null;
  const sorted = [...types].sort((a, b) => b.count - a.count || a.type.localeCompare(b.type));
  return (
    <div className="canvas-legend">
      <button type="button" className="canvas-legend__toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        Legend
      </button>
      <ul aria-label="Types in view" className="canvas-legend__list" hidden={!open}>
        {sorted.map((t) => (
          <li key={t.type}>
            <TypeChip type={t.type} visual={t.visual} />
            <span className="value">{t.count.toLocaleString("en-GB")}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
