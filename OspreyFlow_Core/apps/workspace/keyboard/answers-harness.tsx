// Home's *Your access and tasks* on its own (ADR-145 Amendment 4 decision 12, Amendment 11; L2.7): for
// `needs-you.spec.ts` (rule 13) and the every-harness axe scan, in both themes and under GOV.UK. The reads
// are served by the page, synthetic (rule 9); where a line opens is recorded on `window.__opened`.
// `?home=1` draws it where Home draws it, in the whole of Home (Amendment 11: its place below the two
// columns, its sub-headings beneath its title, measured by `needs-you.spec.ts`).
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import "../src/home/home.css";
import { AnswersForSection } from "../src/home/AnswersForSection";
import { HomePage } from "../src/home/HomePage";
import { applyHarnessBrand } from "./brandHarness";

await applyHarnessBrand();

const CASES = [
  { id: "SYN-c1", name: "Harbour wing review", level: "author", created_at: "", created_by: "engineer-1" },
  { id: "SYN-c2", name: "Carrier records intake", level: "viewer", created_at: "", created_by: "analyst-2" },
  { id: "SYN-c3", name: "Operation Ledger (synthetic demo)", level: "editor", created_at: "", created_by: "analyst-2" },
] as const;
const NEEDS = {
  promotions_overdue: [{ promotion_id: "SYN-pr-1", load_id: "SYN-load-7", dataset_id: "SYN-ds-a", raised_at: "",
                         words: "Promotion SYN-load-7 into Harbour prison extract (synthetic) has waited 3 days for review." }],
  proposals: [
    { dataset_id: "SYN-ds-a", dataset_name: "Harbour prison extract (synthetic)", to_decide: 2 },
  ],
}; // prettier-ignore

const opened: string[] = [];
(window as unknown as { __opened: string[] }).__opened = opened;
const reads = { cases: async () => [...CASES], needs: async () => NEEDS };

const RIGHTS = new Set(["investigate", "edit_pipelines", "review_promotions", "accept_types", "operate_schedules"]);
const section = (
  <AnswersForSection
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    rights={RIGHTS}
    roles={["data_engineer"]}
    onOpenCase={(id) => opened.push(`case:${id}`)}
    onOpenModel={(id) => opened.push(`model:${id}`)}
    onOpenOperations={() => opened.push("operations")}
    read={reads}
  />
);
const home = new URLSearchParams(window.location.search).has("home");

createRoot(document.getElementById("root")!).render(
  home ? (
    <HomePage rights={RIGHTS} answers={section} account={null} marking="OFFICIAL"
      person={{ username: "engineer-1", givenName: "Sam", clearance: "OFFICIAL", roles: ["data_engineer"] }}
      summary={{ glass: [], rules: [], studio: [], admin: [], services: [], held: null, recent: [], attention: [] }}
      onChoose={() => undefined} onOpenCase={(id) => opened.push(`case:${id}`)} />
  ) : (
  <main style={{ padding: "var(--sp-16)", maxWidth: 720 }}>
    <h1 className="value">Home</h1>
    <AnswersForSection
      apiBaseUrl="http://keyboard-test.invalid"
      bearerToken="unused"
      rights={new Set(["investigate", "edit_pipelines", "review_promotions", "accept_types", "operate_schedules"])}
      roles={["data_engineer"]}
      onOpenCase={(id) => opened.push(`case:${id}`)}
      onOpenModel={(id) => opened.push(`model:${id}`)}
      onOpenOperations={() => opened.push("operations")}
      read={reads}
    />
  </main>
  ),
);
