// The Publish screen's keyboard harness (ADR-110 decision 7, `CLAUDE.md` rule 13): its own surface,
// its own registry (`PUBLISH_ACTIONS`). Every call is intercepted by `publish.spec.ts`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { PublishScreen } from "../src/ingest/publish/PublishScreen";

createRoot(document.getElementById("root")!).render(
  <PublishScreen apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" recipeId="r1" investigationId="c1" onBack={() => {}} />,
);
