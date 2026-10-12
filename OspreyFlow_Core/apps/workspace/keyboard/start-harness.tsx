// Start's keyboard harness (ADR-114 Amendment 5 point 9, `CLAUDE.md` rule 13): the real `startScreen`
// the Glass runs, with the real `TopBar` standing for the workspace once a case is open. Opening a case
// stands in for the reload it causes; what happened is on `window.__START__` for `start.spec.ts`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { TopBar } from "../src/shell/TopBar";
import type { HomeSummary } from "../src/home/homeData";
import { startScreen, type StartChoice } from "../src/shell/startScreen";

declare global {
  interface Window {
    __START__?: { opened: { id: string; view?: string } | null };
  }
}
window.__START__ = { opened: null };

const params = new URLSearchParams(location.search);
const rights = new Set((params.get("rights") ?? "investigate,edit_pipelines,manage_people").split(","));

// `?figures=1`: Home with figures in, for looking at it (the walkthroughs leave it reading).
const FIGURES: HomeSummary = {
  glass: [{ tone: "warn", text: "3 alerts in your team's queue, 1 claimed by you" },
          { tone: "info", text: "8 cases open to you, last worked on Operation Ledger (synthetic demo)" }],
  studio: [{ tone: "warn", text: "2 rows held for review" }],
  admin: [{ tone: "ok", text: "6 of 6 services healthy" }],
  attention: [
    { place: "glass", tone: "warn", title: "KYC screening alert in Operation Ledger (synthetic demo)",
      detail: "Halcyon Marine Ltd's beneficial owner matches a sanctions list entry. Claimed by you.", at: new Date().toISOString(), caseId: "c1" },
    { place: "ingest", tone: "warn", title: "2 rows held for review in Operation Ledger (synthetic demo)",
      detail: "A rule could not reach its screening list.", at: new Date(Date.now() - 3600_000).toISOString(), caseId: "c1" },
  ],
  recent: [{ id: "c1", name: "Operation Ledger (synthetic demo)", level: "Author", entities: 68, created: "2026-10-11T09:00:00Z" },
           { id: "c2", name: "HMP fixture (synthetic demo)", level: "Viewer", entities: 1041, created: "2026-10-09T09:00:00Z" }],
  services: [{ name: "Graph store", ok: true }, { name: "Analytics", ok: true }, { name: "Cache", ok: true },
             { name: "Models", ok: true }, { name: "Identity", ok: true }, { name: "Search", ok: true }],
  held: 2,
}; // prettier-ignore

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
    person: { username: "osprey-demo-admin", clearance: "OFFICIAL", roles: ["osprey-admin"] },
    summary: params.get("figures") ? FIGURES : null,
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
