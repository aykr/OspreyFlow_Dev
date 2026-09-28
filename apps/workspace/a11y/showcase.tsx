// a11y contrast showcase — `spec/02_GLASS_FRONTEND.md` §6: "Contrast floor
// met in both themes; verify with automated checks in CI, not by eye."
// Renders a representative sample of the twenty primitives (`docs/
// 02_GLASS_FRONTEND.md` §8) with real text content, so `a11y.spec.ts` has
// something meaningful for axe-core's colour-contrast rule to scan — not
// the full app (which needs a live investigation) or every primitive
// (Popover/ContextMenu/RadialMenu/Drawer are transient overlays with
// nothing to statically show; their surfaces reuse the same panel/overlay
// tokens Panel/Toast already exercise here).
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { SEQ_HEX } from "../src/color/tokens";
import { Button } from "../src/design/primitives/Button";
import { Checkbox } from "../src/design/primitives/Checkbox";
import { Histogram } from "../src/design/primitives/Histogram";
import { IconButton } from "../src/design/primitives/IconButton";
import { Input } from "../src/design/primitives/Input";
import { explanationBasis } from "../src/resolution/explainView";
import type { PairwiseExplanation } from "../src/workingset/models";
import { HighlightedMessage } from "../src/dossier/HighlightedMessage";
import type { DocumentView } from "../src/dossier/models";
import { OntologyRegistry } from "../src/ontology/schema";
import { Panel } from "../src/design/primitives/Panel";
import { RadioGroup } from "../src/design/primitives/RadioGroup";
import { Select } from "../src/design/primitives/Select";
import { Slider } from "../src/design/primitives/Slider";
import { Table } from "../src/design/primitives/Table";
import { Tabs } from "../src/design/primitives/Tabs";
import { Toast } from "../src/design/primitives/Toast";
import { Toggle } from "../src/design/primitives/Toggle";
import { Tooltip } from "../src/design/primitives/Tooltip";

// Phase 6a Stage 4 (B6): one `asserted` span (solid underline) and one `inferred` span (dashed
// underline) in the same message — the two visual states `HighlightedMessage`'s own
// `highlightStyle` distinguishes, both densely close together, the shape most likely to fail the
// contrast floor per this stage's own plan.
const DOSSIER_ONTOLOGY = new OntologyRegistry({
  version: 1,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [] },
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "hexagon", identifiers: [] },
  ],
  edge_types: [],
});
const DOSSIER_DOCUMENT: DocumentView = {
  document_id: "showcase-doc",
  text: "Dana called +441621926368 about the shipment on Tuesday.",
  spans: [
    { start: 0, end: 4, node_id: "n1", entity_type: "Person", provenance_state: "asserted" },
    { start: 12, end: 26, node_id: "n2", entity_type: "Endpoint", provenance_state: "inferred" },
  ],
};

function Showcase() {
  return (
    <div style={{ padding: "var(--sp-24)", display: "flex", flexDirection: "column", gap: "var(--sp-16)" }}>
      <Tabs
        tabs={[
          { id: "graph", label: "Graph" },
          { id: "map", label: "Map" },
        ]}
        activeId="graph"
        onChange={() => {}}
      />
      <Panel title="Inspector">
        <p>Endpoint +441621926368, first seen 2026-01-01.</p>
        <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
          <Button variant="primary">Confirm</Button>
          <Button>Split</Button>
          <IconButton label="Close">×</IconButton>
        </div>
        <Input placeholder="Search entities, identifiers, documents" />
        <Select defaultValue="official">
          <option value="official">OFFICIAL</option>
          <option value="secret">SECRET</option>
        </Select>
        <label style={{ display: "flex", gap: "var(--sp-6)", alignItems: "center" }}>
          <Checkbox /> Include superseded
        </label>
        <RadioGroup
          name="resolution"
          options={[
            { value: "strict", label: "Strict" },
            { value: "balanced", label: "Balanced" },
          ]}
          value="balanced"
          onChange={() => {}}
          aria-label="Resolution threshold"
        />
        <Slider value={5} min={0} max={10} onChange={() => {}} aria-label="Degree filter" />
        <Toggle checked label="Show labels" onChange={() => {}} />
        <Tooltip text="Occurrence count over the brush window">
          <span className="value">42</span>
        </Tooltip>
      </Panel>
      <Table
        columns={[
          { key: "type", header: "Type", render: (r: { type: string }) => r.type },
          { key: "id", header: "ID", render: (r: { id: string }) => r.id, numeric: true },
        ]}
        rows={[{ type: "Person", id: "n1" }]}
        getRowId={(r) => r.id}
      />
      <Table
        columns={[
          { key: "node_a", header: "Node A", render: (p: PairwiseExplanation) => p.node_a },
          { key: "node_b", header: "Node B", render: (p: PairwiseExplanation) => p.node_b },
          { key: "basis", header: "Basis", render: explanationBasis },
          {
            key: "meets_threshold",
            header: "Meets τ",
            render: (p: PairwiseExplanation) => (p.meets_threshold ? "Yes" : "No"),
          },
        ]}
        rows={[
          {
            node_a: "n1",
            node_b: "n2",
            edge_type: "SAME_AS",
            score: 0.97,
            model_version: "splink-3.9.9-config-1",
            comparison_vector: { given_name: 0.88, family_name: 0.95 },
            manually_asserted: false,
            meets_threshold: true,
          },
          {
            node_a: "n2",
            node_b: "n3",
            edge_type: "SAME_AS",
            score: null,
            model_version: null,
            comparison_vector: null,
            manually_asserted: true,
            meets_threshold: true,
          },
        ]}
        getRowId={(p: PairwiseExplanation) => `${p.node_a}-${p.node_b}`}
      />
      <Histogram
        buckets={[
          { key: "mon", count: 4, label: "Monday" },
          { key: "tue", count: 9, label: "Tuesday" },
        ]}
        selectedKey={null}
        onSelect={() => {}}
      />
      <Toast message="Query timed out at 30s. Narrow the date range." kind="error" />
      <Toast message="6 item(s) withheld by handling policy" kind="warning" />
      <Panel title="Messages">
        <HighlightedMessage document={DOSSIER_DOCUMENT} ontology={DOSSIER_ONTOLOGY} />
      </Panel>
      {/* Phase 7 Stage 3: the metrics panel's own representative sample — a ranked list row, a
          dense two-metric comparison (the shape most likely to fail the contrast floor, the same
          reasoning `DOSSIER_DOCUMENT`'s own two-span choice above already follows), and a
          community-hull legend entry. Static markup with the same primitives the real
          `metrics/MetricsPanel.tsx` uses, not the live-fetching component itself — this file's own
          convention throughout (the `Table` rows above are hand-written fixtures too), since a
          real fetch here would prove nothing about contrast and would fail against no real API. */}
      <Panel title="Metrics">
        <Select aria-label="Primary metric" defaultValue="betweenness">
          <option value="degree">Degree</option>
          <option value="betweenness">Betweenness</option>
        </Select>
        <Toggle checked label="Compare a second metric" onChange={() => {}} />
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          <li>
            <button
              type="button"
              style={{ width: "100%", display: "flex", justifyContent: "space-between" }}
            >
              <span>Person · n1</span>
              <span className="value">0.842 / 0.311</span>
            </button>
          </li>
          <li>
            <button
              type="button"
              style={{ width: "100%", display: "flex", justifyContent: "space-between" }}
            >
              <span>Endpoint · n2</span>
              <span className="value">0.573 / 0.204</span>
            </button>
          </li>
        </ul>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-6)" }}>
          <span
            style={{
              width: 12,
              height: 12,
              background: SEQ_HEX[2],
              display: "inline-block",
              borderRadius: 2,
            }}
          />
          <span>Community hull (cluster 3)</span>
        </div>
      </Panel>
      {/* Phase 7 Stage 4: the visual query builder's own representative sample — one pinned node,
          one node in the "needs pinning" state (a dashed `--warning` border plus an inline
          `role="status"` cue, the newest, least-proven-by-eye state this stage introduces and
          therefore the one most worth checking here), and the preview/run controls. Static
          markup with the same primitives `patterns/QueryBuilderPanel.tsx` uses, not the live
          component itself — this file's own convention throughout, see the Metrics panel above. */}
      <Panel title="Query builder">
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
          <div style={{ border: "1px solid var(--border)", borderRadius: 4, padding: "var(--sp-4)" }}>
            <strong>a</strong>: Person · n1
          </div>
          <div style={{ border: "2px dashed var(--warning)", borderRadius: 4, padding: "var(--sp-4)" }}>
            <strong>b</strong>: Person
            <span role="status" style={{ display: "block" }}>
              Second root — pin to a known node or connect it to the pattern
            </span>
          </div>
          <div style={{ display: "flex", gap: "var(--sp-8)" }}>
            <Button type="button">Preview</Button>
            <Button type="button" variant="primary">
              Run
            </Button>
          </div>
          <p>~12 matches</p>
        </div>
      </Panel>
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Showcase />);
