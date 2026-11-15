// The page frame harness (the owner's screenshot of Admin › System, 15 November 2026): the Glass's page as `main.tsx`
// and `App.tsx` draw it, for measuring how it scrolls. The brand frame (GOV.UK's header and footer under that brand),
// App's root at the window's height less what the frame shows above (`--workspace-height`), the classification strip,
// the top bar, and the Glass's body as `App.tsx` lays it: a row filling what is left, the canvas filling the row.
// `?drawer=1` opens a drawer whose body is taller than it (a real `Drawer`, as Ask & Chat's, Explore's and History's
// are); `?overlay=1` draws the empty canvas's start overlay with more than it can show (`App.tsx`'s explore overlay).
// `?brand=govuk` as every harness. Synthetic (rule 9).
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import "../src/shell/places.css";
import { BrandFrame } from "../src/brand/BrandFrame";
import { PLAIN_APPEARANCE } from "../src/brand/brand";
import { Drawer } from "../src/design/primitives/Drawer";
import { ClassificationStrip } from "../src/shell/ClassificationStrip";
import { TopBar } from "../src/shell/TopBar";
import { applyHarnessBrand } from "./brandHarness";

const brand = await applyHarnessBrand();
const params = new URLSearchParams(location.search);
const lines = (what: string) => Array.from({ length: 60 }, (_, i) => <p key={i}>{`${what}, line ${i + 1}.`}</p>);

createRoot(document.getElementById("root")!).render(
  <BrandFrame
    appearance={brand === "govuk"
      ? { brand: "govuk", serviceName: "Prison Intelligence", organisation: "Ministry of Examples", phase: "beta" }
      : PLAIN_APPEARANCE}
  >
    <div style={{ display: "flex", flexDirection: "column", height: "var(--workspace-height, 100vh)" }}>
      <ClassificationStrip marking="OFFICIAL" />
      <TopBar app="glass" account={null} />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, position: "relative" }}>
          <div style={{ flex: 1, position: "relative" }} aria-label="Canvas" role="region">
            {params.get("overlay") === "1" && (
              <div className="explore-overlay" style={{ position: "absolute", top: "var(--sp-40)", left: "50%",
                transform: "translateX(-50%)", maxHeight: "calc(100% - var(--sp-56) - var(--sp-24))", overflowY: "auto",
                padding: "var(--sp-16)", background: "var(--surface-panel)" }}>
                {lines("Where to start")}
              </div>
            )}
          </div>
        </div>
      </div>
      {params.get("drawer") === "1" && (
        <Drawer open onClose={() => undefined} title="Ask & Chat">
          {lines("An answer")}
        </Drawer>
      )}
    </div>
  </BrandFrame>,
);
