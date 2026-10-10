// Pipeline canvas keyboard harness (ADR-108 phase A): the read-only canvas mounted alone, a
// migrated chain plus one branch, as `pipeline-canvas.spec.ts` walks it.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import type { PipelineGraph } from "../../../packages/schemas/generated";
import { PipelineCanvas } from "../src/ingest/dag/PipelineCanvas";

const PIPELINE: PipelineGraph = {
  nodes: [
    { id: "domain", kind: "domain_model", label: "Domain model", config: { pack: "pole" } },
    {
      id: "source",
      kind: "source",
      label: "Carrier B phone records",
      config: { connector_profile: "cell-site-csv", source_location: "uploaded/carrier-b.csv" },
    },
    { id: "profile", kind: "profile", label: "Profile", config: {} },
    { id: "map", kind: "map", label: "Map", config: {} },
    { id: "load", kind: "load", label: "Load", config: { dataset_id: "ds-1" } },
  ],
  edges: [
    { source: "domain", target: "source" },
    { source: "source", target: "profile" },
    { source: "profile", target: "map" },
    { source: "map", target: "load" },
  ],
};

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<PipelineCanvas pipeline={PIPELINE} />);
