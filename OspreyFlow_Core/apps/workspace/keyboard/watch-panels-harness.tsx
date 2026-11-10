// Watch-panels keyboard harness — its own surface (`CLAUDE.md` rule 13): the hotlists and watched
// patterns kept in Rules and Monitoring (`HotlistPanel`, `MonitorPanel` with each watch's own
// schedule, ADR-146 decision 4), and what the Glass makes for them (`GlassWatchActions`: *Watch for
// this*, *Save as a watch*, *Raise an alert…*, decisions 4 and 7). The Watches inbox went in L2.10
// (one queue). Every call is intercepted by `watch-panels.spec.ts` at the transport.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { HotlistPanel } from "../src/watches/HotlistPanel";
import { MonitorPanel } from "../src/watches/MonitorPanel";
import { RaiseAlert, SaveAsWatch, WatchForThis } from "../src/watches/GlassWatchActions";
import { applyHarnessBrand } from "./brandHarness";

// `?brand=govuk`: the GOV.UK brand, so axe scans these in dark, light and GOV.UK.
await applyHarnessBrand();

const API = { apiBaseUrl: "http://keyboard-test.invalid", bearerToken: "unused", investigationId: "inv-1" };

function Harness() {
  return (
    <div style={{ width: 480, display: "flex", flexDirection: "column", gap: 16 }}>
      <HotlistPanel {...API} />
      <MonitorPanel {...API} />
      <section aria-label="Made in the Glass" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <WatchForThis {...API} node={{ id: "n1", properties: { value_normalised: "+447700900918" } }} />
        <SaveAsWatch {...API} patternId="pat-1" />
        <RaiseAlert {...API} nodeIds={["n1", "n2"]} foundBy="the query 'two people at one address'" />
      </section>
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<Harness />);
