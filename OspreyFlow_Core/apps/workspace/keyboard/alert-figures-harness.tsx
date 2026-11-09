// L2.12's keyboard and axe harness (ADR-145 Amendment 4 decisions 8–10 and 12; ADR-146 decision 9):
// the case's Figures with its Alerts panel, the Alert monitoring board first on the Dashboards, the
// Reports Viewer's alert row on Home and the way back, and the *Roles, teams and Authors* page. A
// synthetic Conduit (rule 9) answers in the page itself, so the axe scan sees every panel drawn;
// `alert-figures.spec.ts` reads what each control asked for from `window.__DID__`.
//
// States: none (the Figures); `from=alert` (opened from an alert); `board=1` (the Dashboards, the
// Alert monitoring board first), with `rule=hotlists` and `from=alert` for the journey's filter;
// `home=1` (a Reports Viewer's Home); `help=1` (the help page).
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { HomePage } from "../src/home/HomePage";
import type { HomeSummary } from "../src/home/homeData";
import { RolesHelpPage } from "../src/help/RolesHelpPage";
import { ALERT_MONITORING, AlertMonitoringBoard } from "../src/reports/AlertMonitoringBoard";
import { EmbeddedDashboards } from "../src/reports/EmbeddedDashboards";
import { ReportsPlace } from "../src/reports/ReportsPlace";
import { applyHarnessBrand } from "./brandHarness";

declare global {
  interface Window {
    __DID__?: string[];
  }
}
window.__DID__ = [];
const did = (what: string) => window.__DID__!.push(what);

const now = new Date();
const daysAgo = (n: number) => new Date(now.getTime() - n * 86_400_000).toISOString();
const monday = (n: number) => {
  const d = new Date(now.getTime() - n * 7 * 86_400_000);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
};

const FIGURES = {
  period_weeks: 12, as_of: now.toISOString().slice(0, 10), generated_at: now.toISOString(), alerts_total: 3,
  alerts_by_week: [{ week_start: monday(1), typology: "structuring", count: 3 }],
  open_by_age: [{ label: "under a day", value: 1 }, { label: "1 to 7 days", value: 2 }, { label: "7 to 30 days", value: 0 }, { label: "over 30 days", value: 0 }],
  outcomes: [{ typology: "structuring", open: 2, claimed: 1, true_positive: 0, false_positive: 0 }],
  monitoring: {
    raised_by_rule: [
      { week_start: monday(1), label: "typology", typology: "structuring", count: 3 },
      { week_start: monday(0), label: "hotlists", typology: "", count: 2 },
    ],
    closed_by_outcome: [{ week_start: monday(0), label: "false_positive", typology: "", count: 1 }],
    time_to_close: [{ label: "under a day", value: 1 }, { label: "1 to 7 days", value: 0 }, { label: "7 to 30 days", value: 0 }, { label: "over 30 days", value: 0 }],
    hotlist_matches: [{ week_start: monday(0), label: "hotlists", typology: "", count: 2 }],
    open_by_source: [
      { label: "typology", typology: "structuring", age: "1 to 7 days", count: 2 },
      { label: "hotlists", typology: "", age: "under a day", count: 1 },
    ],
    team: [
      { label: "typology", typology: "structuring", unassigned: 1, mine: 1, older_than_week: 0, closed: 1, not_of_interest: 1 },
      { label: "hotlists", typology: "", unassigned: 1, mine: 0, older_than_week: 0, closed: 0, not_of_interest: 0 },
    ],
  },
  held: null, kyc: null, pole: null,
};  // prettier-ignore

const row = (id: string, kind: string, typology: string | null, age: number, summary: string) => ({
  alert: { id, rule_id: `${kind}:r`, owner_id: "o", mode: "full", referent_node_ids: ["n1"], created_at: daysAgo(age), status: "open", typology },
  summary, kind,
});  // prettier-ignore
const QUEUE = [
  row("a14", "hotlist", null, 0.2, "Synthetic Person A matched a hotlist."),
  row("a12", "typology", "structuring", 2, "Four cash deposits under the threshold."),
];

const answer = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = new URL(String(input));
  did(`${init?.method ?? "GET"} ${url.pathname}${url.search}`);
  if (url.pathname === "/v1/reports/dashboards") return answer([{ slug: "fraud-board", title: "Fraud board" }]);
  if (url.pathname.endsWith("/guest-token")) return answer({ token: "g", uuid: "uuid-fraud", superset_origin: "http://bi.invalid" });
  if (url.pathname.endsWith("/alert-queue")) return answer(QUEUE);
  if (url.pathname.endsWith("/data-feeds")) return answer([]);
  return answer(FIGURES);
};

const api = { apiBaseUrl: "http://keyboard-test.invalid", bearerToken: "unused", investigationId: "inv-1" };
const params = new URLSearchParams(window.location.search);
const fromAlert = params.get("from") === "alert" ? { words: "alert: Hotlist alert in Operation Kestrel (synthetic)", onBack: () => did("back to your alerts") } : null;

const SUMMARY: HomeSummary = {
  glass: [{ tone: "info", text: "1 case open to you" }],
  rules: [{ tone: "warn", text: "2 alerts in your team's queue, 0 claimed by you" }],
  studio: [], admin: [],
  attention: [{ place: "rules", tone: "warn", title: "Hotlist alert in Operation Kestrel (synthetic)", detail: "Synthetic Person A matched a hotlist.",
                at: daysAgo(0.2), caseId: "inv-1", alertId: "a14", alertRule: { label: "hotlists", typology: "" } }],
  recent: [{ id: "inv-1", name: "Operation Kestrel (synthetic)", level: "Viewer", entities: 12, created: daysAgo(30) }],
  services: [], held: null,
};  // prettier-ignore

function Harness() {
  if (params.has("help")) return <RolesHelpPage backTo="Admin" onBack={() => did("back to Admin")} />;
  if (params.has("home")) {
    return (
      <HomePage rights={new Set(["read_alert_queue", "read_reports", "read_report_feed"])} summary={SUMMARY}
                person={{ username: "reports-viewer", givenName: "Robin", clearance: "OFFICIAL", roles: ["reports_viewer"] }}
                onChoose={(p) => did(`choose ${p}`)} onOpenCase={(id) => did(`open case ${id}`)}
                onOpenAlert={(id) => did(`open alert ${id}`)} onAlertJourney={(a, to) => did(`journey ${to} ${a.caseId} ${a.alertId} ${a.rule.label}`)}
                account={null} marking="OFFICIAL" />
    );  // prettier-ignore
  }
  if (params.has("board")) {
    const rule = params.get("rule");
    return (
      <div style={{ flex: 1, display: "flex", padding: "var(--sp-16)", minHeight: 0 }}>
        <EmbeddedDashboards apiBaseUrl={api.apiBaseUrl} bearerToken={api.bearerToken}
          embed={async ({ id }) => { did(`embed ${id}`); }}
          leading={{ ...ALERT_MONITORING, draw: () => (
            <AlertMonitoringBoard api={api} fromAlert={fromAlert} onOpenAlert={(id) => did(`open alert ${id}`)}
              filter={rule ? { rule: { label: rule, typology: "" }, weeks: 4 } : undefined} />
          ) }} />
      </div>
    );  // prettier-ignore
  }
  return (
    <ReportsPlace {...api} canDownload fromAlert={fromAlert} initialWeeks={fromAlert ? 4 : undefined}
                  onOpenAlert={(id) => did(`open alert ${id}`)} />
  );  // prettier-ignore
}

void applyHarnessBrand().then(() => createRoot(document.getElementById("root")!).render(<Harness />));
