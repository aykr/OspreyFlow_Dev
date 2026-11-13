// Shell harness: the brand frame (skip link, GOV.UK header, phase banner, footer)
// around the classification strip and the top bar, for `shell.spec.ts` and the GOV.UK scans (ADR-132).
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { BrandFrame } from "../src/brand/BrandFrame";
import { PLAIN_APPEARANCE } from "../src/brand/brand";
import { ClassificationStrip } from "../src/shell/ClassificationStrip";
import { TopBar } from "../src/shell/TopBar";
import { Drawer } from "../src/design/primitives/Drawer";
import { ContextBanner, MODE_NOTE } from "../src/shell/ContextBanner";

const brand = await applyHarnessBrand();
// ADR-132 Amendment 7: `?banner=1` gives the deployment's own banner words (the owner's wording for
// the demonstration), under GOV.UK beside the beta tag and under OspreyFlow alone; `?banner=alone`
// is the demonstration's own deployment, GOV.UK with no phase, the words alone.
const BANNER = "Demonstration only: this is not a government service, and all data is synthetic.";
const asked = new URLSearchParams(window.location.search).get("banner");
const bannerText = asked === "1" || asked === "alone" ? BANNER : undefined;
const phase = asked === "alone" ? "none" : "beta";
// ADR-132 Amendment 7: `?host=` stands for the page's own address (a harness is served on localhost,
// which is not gov.uk), so the footer on gov.uk can be shown too.
const hostname = new URLSearchParams(window.location.search).get("host") ?? window.location.hostname;
// ADR-145 Amendment 14 decision 2: `?drawer=1` opens a drawer (the Cases drawer's frame) over the page,
// so where it starts can be measured against the top bar and the GOV.UK header's navigation.
const drawer = new URLSearchParams(window.location.search).get("drawer") === "1";

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <BrandFrame
    hostname={hostname}
    appearance={
      brand === "govuk"
        ? { brand: "govuk", serviceName: "Prison Intelligence", organisation: "Ministry of Examples", phase, bannerText }
        : { ...PLAIN_APPEARANCE, bannerText }
    }
  >
    <ClassificationStrip marking="OFFICIAL" />
    <TopBar
      app="glass"
      caseSwitcher={<button type="button" className="btn">Case: Example</button>}
      account={null}
    />
    {drawer && (
      // The Glass's context row as `App.tsx` draws it, its case switcher and cross-link at its end, which the
      // drawer must not cover either (ADR-145 Amendment 14 decision 2).
      <ContextBanner
        place="glass"
        sections={[
          { id: "case", label: "Graph", current: true, onSelect: () => undefined },
          { id: "boards", label: "Drawing board", current: false, onSelect: () => undefined },
        ]}
        note={MODE_NOTE.graph}
        caseSwitcher={<button type="button" className="btn">Case: Example</button>}
        datasets={["Prison intel"]}
        crossLink={{ label: "Open this case's data in the Ingest Studio ↗", onFollow: () => undefined }}
      />
    )}
    <button type="button" className="btn">Workspace control</button>
    {drawer && (
      <Drawer open onClose={() => undefined} title="Cases">
        <p>The case's views and the cases, as the Glass's Cases drawer lists them.</p>
      </Drawer>
    )}
  </BrandFrame>,
);
