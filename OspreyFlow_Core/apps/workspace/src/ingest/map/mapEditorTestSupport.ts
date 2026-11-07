// The pipeline the migrated Map tests open the Map editor from (phase 6: `MapScreen`'s tests run
// against `MapEditor`, the strip above the kept `MapScreen`, as the Studio hosts it).
import type { PipelineGraph } from "../../../../../packages/schemas/generated";

export const STRIP: PipelineGraph = {
  nodes: [
    { id: "source", kind: "source", label: "Carrier B", config: {} },
    { id: "profile", kind: "profile", label: "Profile", config: {} },
    { id: "map", kind: "map", label: "Map", config: {} },
    { id: "load", kind: "load", label: "Load", config: {} },
  ],
  edges: [
    { source: "source", target: "profile" },
    { source: "profile", target: "map" },
    { source: "map", target: "load" },
  ],
};
