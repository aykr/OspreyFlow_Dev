// The top bar's *Needs you · n* on its own (ADR-145 decision 11, A2; L2.7): for `needs-you.spec.ts`
// (rule 13) and the every-harness axe scan, in both themes and under GOV.UK (`?brand=govuk`). The page
// serves `GET /v1/me/needs-you` itself, synthetic (rule 9): an overdue promotion, proposals to decide
// in one dataset. Where an entry opens is recorded on
// `window.__opened`. `?open=1` draws the panel open, for the scan.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import "../src/shell/chrome.css";
import { NeedsYou } from "../src/admin/needsYou/NeedsYou";
import { applyHarnessBrand } from "./brandHarness";

await applyHarnessBrand();

const NEEDS = {
  promotions_overdue: [
    { promotion_id: "SYN-pr-1", load_id: "SYN-load-7", dataset_id: "SYN-ds-a", raised_at: "2026-11-04T09:00:00Z",
      words: "Promotion SYN-load-7 into Harbour prison extract (synthetic) has waited 3 days for review." },
  ],
  proposals: [
    { dataset_id: "SYN-ds-a", dataset_name: "Harbour prison extract (synthetic)", to_decide: 2 },
  ],
}; // prettier-ignore

const opened: string[] = [];
(window as unknown as { __opened: string[] }).__opened = opened;
window.fetch = async () => new Response(JSON.stringify(NEEDS), { status: 200 });

function Harness() {
  return (
    <header className="app-header top-bar" data-app="glass">
      <h1 className="label" style={{ margin: 0 }}>
        Needs you harness
      </h1>
      <div className="app-header__account" style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)", marginLeft: "auto" }}>
        <NeedsYou
          apiBaseUrl="http://keyboard-test.invalid"
          bearerToken="unused"
          onOpenModel={(id) => opened.push(`model:${id}`)}
          onOpenOperations={() => opened.push("operations")}
        />
      </div>
    </header>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Harness />);
if (new URLSearchParams(location.search).get("open") === "1") {
  const press = () => {
    const button = [...document.querySelectorAll("button")].find((b) => b.textContent?.startsWith("Needs you"));
    if (button) button.click();
    else window.setTimeout(press, 20);
  };
  press();
}
