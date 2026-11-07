// L2.3 part 1 (ADR-145 decision 4, N4): a prototype round for the case screen's lightening, for the
// owner to choose from. Never wired into the app. Most of the chrome is the real shell (`TopBar`, the
// place switcher, the context banner, `LeftRail`, `SidePanelStack`), but the mark is drawn without its
// Home button, and what needs the Conduit (search, the panels' contents, the canvas) is a stand-in. `?variant=`:
//   today — the case screen as built (all three panels open), for reference;
//   a     — ADR-145 decision 4 as written: the right-hand column opens with the Inspector only,
//           Metrics and the Query builder folded below it, one click away, in their order;
//   b     — a, and the rail keeps Cases and Explore, the rest under *More* (Monitoring is already the
//           banner's); the view switch keeps Graph and Map, Matrix and Reports under *More views*;
//   c     — b, and no rail: the Glass's tools are one *Tools* menu in the banner beside its sections;
//           Help is in the account menu.
// `case-screen-options.spec.ts` counts each variant's controls and takes the screenshots.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { BrandFrame } from "../src/brand/BrandFrame";
import { PLAIN_APPEARANCE } from "../src/brand/brand";
import { AccordionSection } from "../src/design/primitives/AccordionSection";
import { SidePanelStack } from "../src/layout/SidePanelStack";
import { ClassificationStrip } from "../src/shell/ClassificationStrip";
import { ContextBanner } from "../src/shell/ContextBanner";
import { LeftRail, type RailItem } from "../src/shell/LeftRail";
import { PlaceSwitcher } from "../src/shell/PlaceSwitcher";
import { TopBar } from "../src/shell/TopBar";

type Variant = "today" | "a" | "b" | "c";
const variant = ((new URLSearchParams(location.search).get("variant") ?? "a") as Variant);

// The folded panels are the real `SidePanelStack`'s, read from this browser's storage.
try {
  localStorage.setItem(
    "ospreyflow.side-panels-folded",
    JSON.stringify(variant === "today" ? [] : ["metrics", "query-builder"]),
  );
  localStorage.removeItem("ospreyflow.side-panel-order");
} catch {
  // A private window: the panels open as their defaults.
}

const brand = await applyHarnessBrand();

const PARTS = {
  inspector: ["Properties", "Picture", "Relationships", "Shares contacts", "Neighbourhood risk", "Provenance", "Source", "Judgements"],
  metrics: ["Ranking", "Community detection", "Filter"],
  "query-builder": ["Pattern", "Add to the pattern", "Connect", "Save and load"],
} as const;
const SUMMARY: Record<string, string> = {
  Properties: "type Person · name L. Marsh · marking OFFICIAL-SENSITIVE",
  Ranking: "Degree · 1 Z1042AB 4 · 2 L. Marsh 3 · 3 Z2217CD 3",
  Pattern: "Prisoner —visited by→ Person · Preview · Run",
};

function Parts({ names }: { names: readonly string[] }) {
  const [open, setOpen] = useState<string | null>(names[0] ?? null);
  return (
    <div style={{ padding: "var(--sp-4) var(--sp-8)" }}>
      {names.map((name) => (
        <AccordionSection key={name} title={name} open={open === name} onToggle={() => setOpen(open === name ? null : name)}>
          <p className="label" style={{ margin: "var(--sp-4) 0" }}>{SUMMARY[name] ?? `${name} (synthetic stand-in)`}</p>
        </AccordionSection>
      ))}
    </div>
  );
}

function MoreMenu({ label, items, compact = false }: { label: string; items: readonly string[]; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      {compact ? (
        <button type="button" className="left-rail__item" aria-label={label} title={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
          <span aria-hidden="true">⋯</span>
        </button>
      ) : (
        <button type="button" className="btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
          {label} <span aria-hidden="true">▾</span>
        </button>
      )}
      {open && (
        <div role="menu" aria-label={label} className="menu" style={{ position: "absolute", zIndex: 5, top: "100%", left: 0 }}>
          {items.map((item) => (
            <button key={item} type="button" role="menuitem" className="menu__item" onClick={() => setOpen(false)}>
              {item}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Harness() {
  const [view, setView] = useState("graph");
  const rail = (id: string, label: string, icon: RailItem["icon"]): RailItem => ({ id, label, icon, onSelect: () => undefined });
  const fullRail = [
    rail("cases", "Cases", "cases"), rail("alerts", "Monitoring", "alerts"), rail("ownership", "Ownership", "ownership"),
    rail("history", "History", "history"), rail("explore", "Explore", "explore"), rail("questions", "Questions", "questions"),
    rail("dashboards", "Dashboards", "dashboards"),
  ]; // prettier-ignore
  const railItems = variant === "b" ? fullRail.filter((r) => ["cases", "explore"].includes(r.id)) : fullRail;
  const allViews = ["Graph", "Map", "Matrix", "Reports"];
  const views = (variant === "b" || variant === "c" ? ["Graph", "Map"] : allViews).map((label) => ({
    id: label.toLowerCase(), label, pressed: view === label.toLowerCase(), onSelect: () => setView(label.toLowerCase()),
  })); // prettier-ignore
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "var(--workspace-height, 100vh)" }}>
      <ClassificationStrip marking="OFFICIAL" />
      <TopBar
        app="glass"
        places={<PlaceSwitcher places={["glass", "ingest", "admin"]} current="glass" onChoose={() => undefined} />}
        search={
          <div className="global-search" style={{ display: "flex", gap: "var(--sp-4)" }}>
            <input role="combobox" aria-expanded="false" aria-label="Search entities (stand-in)" className="input" placeholder="Search…  /" />
            <button type="button" className="btn btn--ghost" aria-label="Filters">⚲</button>
            <button type="button" className="btn btn--ghost">Add many from a list</button>
          </div>
        }
        views={views}
        actions={
          <>
            {(variant === "b" || variant === "c") && <MoreMenu label="More views" items={["Matrix", "Reports"]} />}
            <button type="button" className="btn" aria-haspopup="dialog">Export <span aria-hidden="true">▾</span></button>
          </>
        }
        account={
          variant === "c" ? (
            <MoreMenu label="osprey-demo-analyst · OFFICIAL" items={["Help", "Theme", "Sign out"]} />
          ) : (
            <button type="button" className="btn menu-button">osprey-demo-analyst · OFFICIAL</button>
          )
        }
      />
      <ContextBanner
        place="glass"
        sections={[
          { id: "case", label: "Case", current: true, onSelect: () => undefined },
          { id: "boards", label: "Boards", current: false },
          { id: "monitoring", label: "Monitoring", current: false, onSelect: () => undefined },
        ]}
        caseSwitcher={
          <>
            <button type="button" className="btn menu-button menu-button--case">Case: Kestrel ▾</button>
            {variant === "c" && <MoreMenu label="Tools" items={["Ownership", "History", "Explore", "Questions", "Dashboards"]} />}
          </>
        }
        datasets={["Prison intel"]}
        crossLink={{ label: "Open Prison intel in the Ingest Studio ↗", onFollow: () => undefined }}
      />
      <div role="toolbar" aria-label="Graph view" className="view-toolbar">
        <label className="label" style={{ display: "flex", alignItems: "center", gap: "var(--sp-6)" }}>
          Match strictness <input type="range" min={0} max={2} defaultValue={1} aria-label="Match strictness" />
        </label>
      </div>
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {variant !== "c" && (
          <LeftRail items={railItems} onHelp={() => undefined} />
        )}
        {variant === "b" && (
          <div style={{ position: "absolute", left: 6, top: 230 }}>
            <MoreMenu label="More" compact items={["Ownership", "History", "Questions", "Dashboards"]} />
          </div>
        )}
        <main
          role="application"
          aria-label="Network canvas"
          tabIndex={0}
          className="network-canvas"
          style={{ flex: 1, minWidth: 0, display: "grid", placeItems: "center", color: "var(--text-secondary)" }}
        >
          Canvas (stand-in)
        </main>
        <aside aria-label="Side panels" style={{ width: 340, flex: "none", borderLeft: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", minHeight: 0 }}>
          <SidePanelStack
            panels={[
              { id: "inspector", name: "Inspector", content: <Parts names={PARTS.inspector} /> },
              { id: "metrics", name: "Metrics", content: <Parts names={PARTS.metrics} /> },
              { id: "query-builder", name: "Query builder", content: <Parts names={PARTS["query-builder"]} /> },
            ]}
          />
        </aside>
      </div>
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
