// Start's keyboard harness (ADR-114 Amendment 5 point 9, `CLAUDE.md` rule 13): the real `startScreen`
// the Glass runs, with the real `TopBar` standing for the workspace once a case is open. Opening a case
// stands in for the reload it causes; what happened is on `window.__START__` for `start.spec.ts`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { TopBar } from "../src/shell/TopBar";
import { startScreen, type StartChoice } from "../src/shell/startScreen";

declare global {
  interface Window {
    __START__?: { opened: { id: string; view?: string } | null };
  }
}
window.__START__ = { opened: null };

const params = new URLSearchParams(location.search);
const rights = new Set((params.get("rights") ?? "investigate,edit_pipelines,manage_people").split(","));

function Harness() {
  const [investigationId, setInvestigationId] = useState<string | null>(params.get("case"));
  const [startChoice, setStartChoice] = useState<StartChoice>(null);
  const [view, setView] = useState("graph");
  const [browsing, setBrowsing] = useState(false);
  const shown = startScreen({
    rights,
    rightsSettled: true,
    investigationId,
    startChoice,
    setStartChoice,
    account: <span>osprey-demo-admin</span>,
    marking: "OFFICIAL",
    apiBaseUrl: "http://keyboard-test.invalid",
    bearerToken: "unused",
    lastCaseId: null,
    isAdministrator: false,
    openCase: (id, opened) => {
      window.__START__!.opened = { id, view: opened };
      setInvestigationId(id);
      setView(opened ?? "graph");
    },
    browseCases: () => setBrowsing(true),
    openStudio: () => setView("ingest"),
  });
  if (shown) return shown;
  return (
    <div style={{ display: "flex", flexDirection: "column", width: "100%" }}>
      <TopBar app={view === "ingest" ? "ingest" : "glass"} caseSwitcher={null} account={null} onStart={() => setStartChoice("start")} />
      <p>{browsing ? `Cases, over ${investigationId}` : `Workspace on ${investigationId}, ${view}`}</p>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
