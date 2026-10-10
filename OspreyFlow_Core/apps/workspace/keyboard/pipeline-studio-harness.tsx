// Pipeline Studio keyboard harness (ADR-108 phase B): the fresh Studio mounted whole;
// `pipeline-studio.spec.ts` intercepts the routes at the transport.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { PipelineStudio } from "../src/ingest/dag/PipelineStudio";

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(
  <PipelineStudio apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" investigationId="inv-1" />,
);
