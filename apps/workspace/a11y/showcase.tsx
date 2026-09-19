// a11y contrast showcase — `docs/02_GLASS_FRONTEND.md` §6: "Contrast floor
// met in both themes; verify with automated checks in CI, not by eye."
// Renders a representative sample of the twenty primitives (`docs/
// 02_GLASS_FRONTEND.md` §8) with real text content, so `a11y.spec.ts` has
// something meaningful for axe-core's colour-contrast rule to scan — not
// the full app (which needs a live investigation) or every primitive
// (Popover/ContextMenu/RadialMenu/Drawer are transient overlays with
// nothing to statically show; their surfaces reuse the same panel/overlay
// tokens Panel/Toast already exercise here).
import { createRoot } from "react-dom/client";

import "../../../docs/design/tokens.css";
import "../src/design/primitives.css";
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
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Showcase />);
