// Start (ADR-114 Amendment 5 point 9): where a person goes after signing in, with no case open — a
// tile for each place their rights open. ADR-107's welcome page did this until ADR-114 removed it
// with the launcher. The tiles are a convenience, never the gate: every route checks its own right.
import type { ReactNode } from "react";

import type { StartPlace } from "../rights/visibility";
import { BrandMark } from "./BrandMark";
import { ClassificationStrip } from "./ClassificationStrip";

const TILES: Record<StartPlace, { title: string; does: string; then: string }> = {
  glass: { title: "The Glass", does: "Investigate a case: the graph, the map and its reports.", then: "Choose a case" },
  ingest: { title: "Ingest Studio", does: "Load data into a case: pipelines, files and their review.", then: "Choose the case to load into" },
  admin: { title: "Admin", does: "People, dashboards, demo packs and the system.", then: "No case needed" },
};

export interface StartPageProps {
  places: readonly StartPlace[];
  onChoose: (place: StartPlace) => void;
  /** The account menu, as the top bar shows it. */
  account: ReactNode;
  /** The deployment's marking (ADR-115 decision 2); no strip where it is unknown. */
  marking: string | null;
}

/** The chrome every surface outside a case shares: the marking strip, then the bar (ADR-115 E1). */
export function StartBar({ account, onStart, marking }: { account: ReactNode; onStart?: () => void; marking: string | null }) {
  return (
    <>
    {marking && <ClassificationStrip marking={marking} />}
    <header className="app-header top-bar">
      {onStart ? (
        <button type="button" className="brand-mark-button" aria-label="OspreyFlow, go to Start" onClick={onStart}>
          <BrandMark />
        </button>
      ) : (
        <BrandMark />
      )}
      <div className="app-header__account" style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
        {account}
      </div>
    </header>
    </>
  );
}

export function StartPage({ places, onChoose, account, marking }: StartPageProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <StartBar account={account} marking={marking} />
      <main style={{ display: "flex", justifyContent: "center", padding: "var(--sp-24)" }}>
        <div style={{ width: "min(960px, 100%)", display: "flex", flexDirection: "column", gap: "var(--sp-16)" }}>
          <h1>Where to?</h1>
          <div className="start-tiles">
            {places.map((place) => (
              <button key={place} type="button" className="start-tile" onClick={() => onChoose(place)}>
                <span className="start-tile__title">{TILES[place].title}</span>
                <span className="start-tile__does">{TILES[place].does}</span>
                <span className="start-tile__then label">{TILES[place].then}</span>
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
