// The four places' keyboard harness (ADR-145 decisions 1–3 and Amendment 4, ADR-146 decision 2,
// `CLAUDE.md` rule 13): the real brand
// frame, the real `TopBar` with the real `PlaceSwitcher` (inside the GOV.UK header under `?brand=govuk`),
// the real `ContextBanner` with the Glass's sections and its cross-link, and the real Admin place,
// wired as `App.tsx` wires them — the view to come back to through the same `useLastGlassView`. `?rights=`
// gives the person's rights. The open case is the real module's (`investigation/investigationId.ts`),
// and choosing another is the real `openCase`, which reloads the page as the Glass does (here, back
// into this harness with `?investigation=` and `?view=`), so a cross-link that lost the case or the
// view across that reload would show it; what was chosen is on `window.__PLACES__`.
import { PANEL_OPENERS, RAIL_LABELS, railMark, splitRail } from "../src/shell/railLayout";
import type { RailEntry } from "../src/rights/visibility";

const RAIL_ENTRIES: RailEntry[] = ["cases", "explore", "questions", "dashboards", "history", "ownership", "strength"];
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { AdminPlace } from "../src/admin/AdminPlace";
import { BrandFrame } from "../src/brand/BrandFrame";
import { PLAIN_APPEARANCE } from "../src/brand/brand";
import { ClassificationStrip } from "../src/shell/ClassificationStrip";
import { ContextBanner, crossLinkFor, glassMode, MODE_NOTE } from "../src/shell/ContextBanner";
import { PlaceSwitcher } from "../src/shell/PlaceSwitcher";
import { useLastGlassView } from "../src/shell/placeMemory";
import { openCase } from "../src/investigation/cases";
import { initialInvestigationId } from "../src/investigation/investigationId";
import { placesFor, type PlaceId } from "../src/shell/places";
import { LeftRail } from "../src/shell/LeftRail";
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
type View = "graph" | "map" | "dossier" | "matrix" | "reports" | "strength" | "ownership" | "dashboards" | "alerts" | "ingest" | "boards";

function Harness() {
  const start = (params.get("place") as PlaceId | null) ?? (params.get("view") === "ingest" ? "ingest" : null) ?? places[0] ?? "glass";
  const [admin, setAdmin] = useState(start === "admin");
  const [view, setView] = useState<View>(start === "ingest" ? "ingest" : start === "rules" ? "alerts" : "graph");
  // The rail's panels, open or not (ADR-145 Amendment 14): each opener toggles its own, as `App.tsx`'s do.
  const [panels, setPanels] = useState<ReadonlySet<RailEntry>>(new Set());
  const toggle = (id: RailEntry) =>
    setPanels((open) => {
      const next = new Set(open);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  const caseId = initialInvestigationId() ?? "kestrel";
  // The same kept-view list as `App.tsx` (`KEPT_GLASS_VIEWS`), so the Messages case tests the Glass's.
  const lastGlassView = useLastGlassView(view, "ingest", "graph");
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
  const place: PlaceId = admin ? "admin" : view === "ingest" ? "ingest" : view === "alerts" ? "rules" : "glass";
  const choose = (to: PlaceId) => {
    window.__PLACES__!.chosen.push(to);
    setAdmin(to === "admin");
    if (to === "ingest") setView("ingest");
    else if (to === "rules") setView("alerts");
    else if (to === "glass" && (view === "ingest" || view === "alerts")) setView(lastGlassView());
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
        app={place === "ingest" ? "ingest" : place === "rules" ? "rules" : "glass"}
        // `?badge=1`: Rules and Monitoring with its open count, as `App.tsx` draws it (ADR-146 decision 2).
        places={<PlaceSwitcher places={places} current={place} onChoose={choose} counts={{ rules: params.has("badge") ? 3 : undefined }} />}
        views={
          place === "glass"
            ? (["graph", "map", "dossier"] as const).map((v) => ({
                id: v,
                label: { graph: "Graph", map: "Map", dossier: "Messages" }[v],
                pressed: view === v,
                onSelect: () => setView(v),
              }))
            : []
        }
        // ADR-145 Amendment 2: Matrix and Reports one click away, as `App.tsx` offers them.
        moreViews={
          place === "glass"
            ? (["matrix", "reports"] as const).map((v) => ({
                id: v,
                label: { matrix: "Matrix", reports: "Figures" }[v],
                pressed: view === v,
                onSelect: () => setView(v),
              }))
            : []
        }
        account={null}
      />
      <ContextBanner
        place={place}
        sections={
          place === "glass"
            ? [
                // ADR-145 Amendment 13: the mode toggle, as `App.tsx` draws it; neither current on a place of
                // the rail's own, such as Connection strength (Amendment 14 decision 3, the same `glassMode`).
                { id: "case", label: "Graph", current: glassMode(view) === "graph", onSelect: () => setView("graph") },
                { id: "boards", label: "Drawing board", current: glassMode(view) === "board", onSelect: () => setView("boards") },
              ]
            : []
        }
        note={place === "glass" && glassMode(view) ? MODE_NOTE[glassMode(view)!] : undefined}
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
        <div style={{ display: "flex", minHeight: 0 }}>
          {place === "glass" && (
            // The Glass's rail as `App.tsx` splits it (ADR-145 Amendment 12, `shell/railLayout.ts`).
            <LeftRail
              {...splitRail(RAIL_ENTRIES.map((id) => ({
                id, label: RAIL_LABELS[id], icon: id,
                onSelect: PANEL_OPENERS.includes(id) ? () => toggle(id) : () => setView(id as View),
                // ADR-145 Amendment 14 decision 3: marked by the same `railMark` as `App.tsx`, never a copy.
                ...railMark(id, { view, open: panels }),
              })))}
              onHelp={() => undefined}
            />
          )}
          <main aria-label="Place content">
            <p>{`${place}, ${view}, on case ${caseId}`}</p>
          </main>
        </div>
      )}
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
// `?open=more` or `?open=views`: the rail's ⋯ Explore Details or the top bar's More views drawn open, so the
// accessibility scan sees the menu itself (`a11y/every-harness.spec.ts`).
const opening = params.get("open");
if (opening) {
  const press = () => {
    const button =
      opening === "more"
        ? document.querySelector<HTMLButtonElement>('nav[aria-label="Workspace"] button[aria-label^="Explore Details"]')
        : [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent?.startsWith("More views"));
    if (button) button.click();
    else setTimeout(press, 50);
  };
  setTimeout(press, 0);
}

// ADR-132 Amendment 8: `?banner=1` is the demonstration's own deployment (osprey-small): its banner words
// alone, no phase, so the height above a case's workspace is measured as the owner saw it.
const DEMO_BANNER = "Demonstration only: this is not a government service, and all data is synthetic.";
const demo = params.get("banner") === "1";

createRoot(container).render(
  <BrandFrame
    appearance={
      brand === "govuk"
        ? { brand: "govuk", serviceName: "Prison Intelligence", organisation: "Ministry of Examples",
            ...(demo ? { phase: "none" as const, bannerText: DEMO_BANNER } : { phase: "beta" as const }) }
        : { ...PLAIN_APPEARANCE, ...(demo ? { bannerText: DEMO_BANNER } : {}) }
    }
  >
    <Harness />
  </BrandFrame>,
);
