// The three places' keyboard harness (ADR-145 decisions 1–3, `CLAUDE.md` rule 13): the real brand
// frame, the real `TopBar` with the real `PlaceSwitcher` (inside the GOV.UK header under `?brand=govuk`),
// the real `ContextBanner` with the Glass's sections and its cross-link, and the real Admin place,
// wired as `App.tsx` wires them — the view to come back to through the same `useLastGlassView`. `?rights=`
// gives the person's rights. The open case is the real module's (`investigation/investigationId.ts`),
// and choosing another is the real `openCase`, which reloads the page as the Glass does (here, back
// into this harness with `?investigation=` and `?view=`), so a cross-link that lost the case or the
// view across that reload would show it; what was chosen is on `window.__PLACES__`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { AdminPlace } from "../src/admin/AdminPlace";
import { BrandFrame } from "../src/brand/BrandFrame";
import { PLAIN_APPEARANCE } from "../src/brand/brand";
import { ClassificationStrip } from "../src/shell/ClassificationStrip";
import { ContextBanner, crossLinkFor } from "../src/shell/ContextBanner";
import { PlaceSwitcher } from "../src/shell/PlaceSwitcher";
import { useLastGlassView } from "../src/shell/placeMemory";
import { openCase } from "../src/investigation/cases";
import { initialInvestigationId } from "../src/investigation/investigationId";
import { placesFor, type PlaceId } from "../src/shell/places";
import { TopBar } from "../src/shell/TopBar";

declare global {
  interface Window {
    __PLACES__?: { chosen: PlaceId[]; crossed: string[] };
  }
}
window.__PLACES__ = { chosen: [], crossed: [] };
// A walkthrough starts in a fresh tab; a reload inside it (`openCase`) keeps the tab's storage.
if (!new URLSearchParams(location.search).has("investigation")) sessionStorage.clear();

// The Admin place's reads answer empty: nothing here is under test but its frame (rule 9: synthetic).
window.fetch = async () => new Response("[]", { status: 200 });

const brand = await applyHarnessBrand();
const params = new URLSearchParams(location.search);
const rights = new Set((params.get("rights") ?? "investigate,read_alert_queue,edit_pipelines,manage_people").split(","));
const places = placesFor(rights);
const CASES: Record<string, string> = { kestrel: "Kestrel", harrier: "Harrier" };
type View = "graph" | "map" | "alerts" | "ingest";

function Harness() {
  const start = (params.get("place") as PlaceId | null) ?? (params.get("view") === "ingest" ? "ingest" : null) ?? places[0] ?? "glass";
  const [admin, setAdmin] = useState(start === "admin");
  const [view, setView] = useState<View>(start === "ingest" ? "ingest" : "graph");
  const caseId = initialInvestigationId() ?? "kestrel";
  const lastGlassView = useLastGlassView(view, "ingest", "graph", ["graph", "map", "alerts"] as const);
  // The real `openCase`, its reload kept inside the harness.
  const reopen = (id: string) =>
    openCase(id, view === "ingest" ? "ingest" : undefined, (url) => {
      const next = new URLSearchParams(new URL(url, location.href).search);
      const here = new URLSearchParams(location.search);
      here.set("investigation", next.get("investigation") ?? id);
      here.delete("place");
      if (next.get("view")) here.set("view", next.get("view")!);
      else here.delete("view");
      location.assign(`${location.pathname}?${here}`);
    });
  const place: PlaceId = admin ? "admin" : view === "ingest" ? "ingest" : "glass";
  const choose = (to: PlaceId) => {
    window.__PLACES__!.chosen.push(to);
    setAdmin(to === "admin");
    if (to === "ingest") setView("ingest");
    else if (to === "glass" && view === "ingest") setView(lastGlassView());
  };
  const caseMenu = (
    <button type="button" className="btn" onClick={() => reopen(caseId === "kestrel" ? "harrier" : "kestrel")}>
      Case: {CASES[caseId] ?? caseId}
    </button>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", width: "100%" }}>
      <ClassificationStrip marking="OFFICIAL" />
      <TopBar
        app={place === "ingest" ? "ingest" : "glass"}
        places={<PlaceSwitcher places={places} current={place} onChoose={choose} />}
        views={
          place === "glass"
            ? (["graph", "map"] as const).map((v) => ({ id: v, label: v === "graph" ? "Graph" : "Map", pressed: view === v, onSelect: () => setView(v) }))
            : []
        }
        account={null}
      />
      <ContextBanner
        place={place}
        sections={
          place === "glass"
            ? [
                { id: "case", label: "Case", current: view !== "alerts", onSelect: () => setView("graph") },
                { id: "boards", label: "Boards", current: false },
                { id: "monitoring", label: "Monitoring", current: view === "alerts", onSelect: () => setView("alerts") },
              ]
            : []
        }
        caseSwitcher={place === "admin" ? undefined : caseMenu}
        datasets={place === "glass" ? ["Prison intel"] : null}
        crossLink={crossLinkFor(place, places, CASES[caseId] ?? caseId, ["Prison intel"], {
          toStudio: () => {
            window.__PLACES__!.crossed.push("to-studio");
            setView("ingest");
          },
          toGlass: () => {
            window.__PLACES__!.crossed.push("to-glass");
            setView(lastGlassView());
          },
        })}
      />
      {place === "admin" ? (
        <AdminPlace apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" rights={rights} />
      ) : (
        <main aria-label="Place content">
          <p>{`${place}, ${view}, on case ${caseId}`}</p>
        </main>
      )}
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(
  <BrandFrame
    appearance={
      brand === "govuk"
        ? { brand: "govuk", serviceName: "Prison Intelligence", organisation: "Ministry of Examples", phase: "beta" }
        : PLAIN_APPEARANCE
    }
  >
    <Harness />
  </BrandFrame>,
);
