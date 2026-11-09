// Home's *What you can do, and what you answer for* on its own (ADR-145 Amendment 4 decision 12; L2.7):
// for `needs-you.spec.ts` (rule 13) and the every-harness axe scan, in both themes and under GOV.UK. The
// reads are served by the page, synthetic (rule 9); where a line opens is recorded on `window.__opened`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import "../src/home/home.css";
import { AnswersForSection } from "../src/home/AnswersForSection";
import { applyHarnessBrand } from "./brandHarness";

await applyHarnessBrand();

const CASES = [
  { id: "SYN-c1", name: "Harbour wing review", level: "author", created_at: "", created_by: "engineer-1" },
  { id: "SYN-c2", name: "Carrier records intake", level: "viewer", created_at: "", created_by: "analyst-2" },
] as const;
const NEEDS = {
  promotions_overdue: [{ promotion_id: "SYN-pr-1", load_id: "SYN-load-7", dataset_id: "SYN-ds-a", raised_at: "",
                         words: "Promotion SYN-load-7 into Harbour prison extract (synthetic) has waited 3 days for review." }],
  proposals: [
    { dataset_id: "SYN-ds-a", dataset_name: "Harbour prison extract (synthetic)", to_decide: 2, above_clearance: false },
    { dataset_id: "SYN-ds-top", dataset_name: "Border watch (synthetic)", to_decide: 0, above_clearance: true },
  ],
}; // prettier-ignore

const opened: string[] = [];
(window as unknown as { __opened: string[] }).__opened = opened;
const reads = { cases: async () => [...CASES], needs: async () => NEEDS };

createRoot(document.getElementById("root")!).render(
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
  </main>,
);
