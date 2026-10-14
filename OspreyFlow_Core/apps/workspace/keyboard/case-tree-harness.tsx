// Case tree keyboard harness (ADR-084 Amendment 4): the tree the case menu and the Cases drawer show.
// `case-tree.spec.ts` intercepts the case routes; the case on screen is `?current=` (default the case).
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { CaseTree } from "../src/investigation/CaseTree";

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
const current = new URLSearchParams(window.location.search).get("current") ?? "ledger";

createRoot(container).render(
  <CaseTree
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    currentId={current}
    onOpen={(id) => {
      document.body.dataset.opened = id;
    }}
  />,
);
