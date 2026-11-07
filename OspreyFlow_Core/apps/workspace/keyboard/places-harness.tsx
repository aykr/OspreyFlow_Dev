// The three places' keyboard harness (ADR-145 decisions 1–3, `CLAUDE.md` rule 13): the real brand
// frame, the real `TopBar` with the real `PlaceSwitcher` (inside the GOV.UK header under `?brand=govuk`)
// and the real `ContextBanner` with its cross-link, wired as `App.tsx` wires them. `?rights=` gives the
// person's rights; what was chosen, and the case kept across the cross-link, are on `window.__PLACES__`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { BrandFrame } from "../src/brand/BrandFrame";
import { PLAIN_APPEARANCE } from "../src/brand/brand";
import { ClassificationStrip } from "../src/shell/ClassificationStrip";
import { ContextBanner, crossLinkFor } from "../src/shell/ContextBanner";
import { PlaceSwitcher } from "../src/shell/PlaceSwitcher";
import { placesFor, type PlaceId } from "../src/shell/places";
import { TopBar } from "../src/shell/TopBar";

declare global {
  interface Window {
    __PLACES__?: { chosen: PlaceId[]; crossed: string[]; caseId: string };
  }
}
window.__PLACES__ = { chosen: [], crossed: [], caseId: "kestrel" };

const brand = await applyHarnessBrand();
const params = new URLSearchParams(location.search);
const rights = new Set((params.get("rights") ?? "investigate,edit_pipelines,manage_people").split(","));
const places = placesFor(rights);

function Harness() {
  const [place, setPlace] = useState<PlaceId>((params.get("place") as PlaceId | null) ?? places[0] ?? "glass");
  const go = (to: PlaceId, how: string) => {
    window.__PLACES__!.crossed.push(how);
    setPlace(to);
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", width: "100%" }}>
      <ClassificationStrip marking="OFFICIAL" />
      <TopBar
        app={place === "ingest" ? "ingest" : "glass"}
        places={
          <PlaceSwitcher
            places={places}
            current={place}
            onChoose={(to) => {
              window.__PLACES__!.chosen.push(to);
              setPlace(to);
            }}
          />
        }
        account={null}
      />
      <ContextBanner
        place={place}
        caseSwitcher={place === "admin" ? undefined : <button type="button" className="btn">Case: Kestrel</button>}
        datasets={place === "admin" ? null : ["Prison intel"]}
        crossLink={crossLinkFor(place, places, "Kestrel", ["Prison intel"], {
          toStudio: () => go("ingest", "to-studio"),
          toGlass: () => go("glass", "to-glass"),
        })}
      />
      <main aria-label={`${place} content`}>
        <p>{`${place} on case ${window.__PLACES__!.caseId}`}</p>
      </main>
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
