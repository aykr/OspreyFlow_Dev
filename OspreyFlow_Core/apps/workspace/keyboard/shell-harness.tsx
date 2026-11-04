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

const brand = await applyHarnessBrand();

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
    <ClassificationStrip marking="OFFICIAL" />
    <TopBar
      app="glass"
      caseSwitcher={<button type="button" className="btn">Case: Example</button>}
      account={null}
    />
    <button type="button" className="btn">Workspace control</button>
  </BrandFrame>,
);
