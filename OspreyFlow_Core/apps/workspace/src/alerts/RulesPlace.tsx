// Rules and Monitoring, a place of its own (`06_DECISIONS.md` ADR-146 decision 2; ADR-145
// Amendment 4 decision 1): Monitoring left the Glass. Its tabs are the owner's M1 ruling:
// - *Alerts*: the one queue, every kind the reader may see, with an alert's detail beside it (the
//   Watches inbox went in L2.10: what fired a watch's alert is on its detail);
// - *What raises alerts*: the inventory of every rule and watch (decision 5), then the rules and
//   their templates, the hotlists and watched patterns, and the screening lists the rules read;
// - *Held rows*: the rows a failing rule held;
// - *Changes*: the rule audit.
// Connection strength is not alerts: it stays in the Glass (ADR-139).
//
// An alert has an address, `/alerts/<id>` (decision 6): opened here, the Conduit says which case it
// is worked in, and the workspace opens that case on it (`address.ts`). An alert the reader may not
// see is answered exactly as one that does not exist (rule 3), and said so in the same words.
//
// What each account may do follows its level in the case, read as every other case surface reads it
// (`listCases`); the Conduit refuses whatever a stale view offers anyway, and refuses the whole
// place to anyone whose rights do not open it (`services/api/rules_place.py`).
import { useEffect, useState, type ReactNode } from "react";
import { Tabs } from "../design/primitives";
import { listCases, type AccessLevel } from "../investigation/cases";
import { NO_SUCH_ALERT, type AlertAtAddressState } from "./address";
import { AlertQueue, type AlertEvidence } from "./AlertQueue";
import { AlertSourcesPanel } from "./AlertSourcesPanel";
import type { CanvasOutcome } from "./api";
import { HeldRowsPanel } from "./HeldRowsPanel";
import { ListsPanel } from "./ListsPanel";
import { RuleAuditPanel } from "./RuleAuditPanel";
import { RulesPanel } from "./RulesPanel";
import { HotlistPanel } from "../watches/HotlistPanel";
import { MonitorPanel } from "../watches/MonitorPanel";

export type RulesTab = "alerts" | "raises" | "held" | "changes";

export const RULES_TABS: readonly { id: RulesTab; label: string }[] = [
  { id: "alerts", label: "Alerts" },
  { id: "raises", label: "What raises alerts" },
  { id: "held", label: "Held rows" },
  { id: "changes", label: "Changes" },
];

export interface RulesPlaceProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string | null;
  accountId: string | null;
  isAdministrator: boolean;
  /** ADR-112's `load_screening_lists`: subscribing to and refreshing a screening list. */
  canManageLists?: boolean;
  /** `deploy_rules`: *Make live* is offered only to someone who holds it (ADR-146 decision 3). */
  canMakeLive?: boolean;
  onCanvas: (outcome: CanvasOutcome, nodeIds: string[]) => void;
  /** The alert at the address on screen and the Conduit's answer for it; `null` for no address. */
  address?: { alertId: string; state: AlertAtAddressState } | null;
  /** Gives an alert its address when it is opened here, or leaves it (`null`) when it is closed. */
  onOpenAlert?: (alertId: string | null) => void;
  /** *Open the evidence* (ADR-146 decision 6): resolves to words when it could not be opened. */
  onOpenEvidence?: (evidence: AlertEvidence) => Promise<string | null>;
}

export function RulesPlace(props: RulesPlaceProps) {
  const { apiBaseUrl, bearerToken, investigationId, address } = props;
  const [tab, setTab] = useState<RulesTab>("alerts");
  const [level, setLevel] = useState<AccessLevel | null>(null);

  useEffect(() => {
    if (!investigationId) return;
    let cancelled = false;
    listCases(apiBaseUrl, bearerToken)
      .then((cases) => {
        if (!cancelled) setLevel(cases.find((c) => c.id === investigationId)?.level ?? null);
      })
      .catch(() => !cancelled && setLevel(null));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);
  // An address opens the Alerts tab, whichever tab was open, on that alert.
  const addressedId = address?.alertId ?? null;
  useEffect(() => {
    if (addressedId) setTab("alerts");
  }, [addressedId]);
  const answer = address?.state;

  const heading = (
    <h2 className="value" style={{ margin: 0 }}>
      Rules and Monitoring
    </h2>
  );
  const frame = (body: ReactNode) => (
    <section
      aria-label="Rules and Monitoring"
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", padding: "var(--sp-16)", minHeight: 0, flex: 1, overflowY: "auto" }}
    >
      {heading}
      {body}
    </section>
  );
  const backToTheQueue = (
    <button type="button" className="btn btn--ghost" onClick={() => props.onOpenAlert?.(null)} style={{ alignSelf: "flex-start" }}>
      ← Back to the queue
    </button>
  );
  if (answer?.status === "missing") return frame(<><p role="alert">{NO_SUCH_ALERT}</p>{investigationId && backToTheQueue}</>);
  if (answer?.status === "failed") return frame(<><p role="alert" style={{ color: "var(--error)" }}>{answer.message}</p>{investigationId && backToTheQueue}</>);
  // Another case's alert: the workspace is opening that case on it (`address.ts`).
  const elsewhere = answer?.status === "found" && answer.caseId !== investigationId;
  if (!investigationId || elsewhere) {
    return frame(<p className="label">{address ? "Opening the alert…" : "Open a case to see its alerts and what raises them."}</p>);
  }
  const api = { apiBaseUrl, bearerToken, investigationId };
  const readsAudit = level === "author" || props.isAdministrator;
  const tabs = RULES_TABS.filter(
    (t) => (t.id !== "held" || level === "editor" || level === "author") && (t.id !== "changes" || readsAudit),
  );

  return frame(
    <>
      <Tabs tabs={tabs} activeId={tab} onChange={(id) => setTab(id as RulesTab)} />
      {tab === "alerts" && (
        <AlertQueue
          {...api}
          level={level}
          accountId={props.accountId}
          onCanvas={props.onCanvas}
          openAlertId={addressedId}
          onOpenAlert={props.onOpenAlert}
          onOpenEvidence={props.onOpenEvidence}
        />
      )}
      {tab === "raises" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)" }}>
          <AlertSourcesPanel {...api} />
          <RulesPanel {...api} level={level} isAdministrator={props.isAdministrator} accountId={props.accountId} canMakeLive={props.canMakeLive ?? false} />
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", maxWidth: 640 }}>
            <HotlistPanel {...api} />
            <MonitorPanel {...api} />
          </div>
          <ListsPanel apiBaseUrl={apiBaseUrl} bearerToken={bearerToken} canManage={props.canManageLists ?? false} />
        </div>
      )}
      {tab === "held" && <HeldRowsPanel {...api} level={level} />}
      {tab === "changes" && readsAudit && <RuleAuditPanel {...api} />}
    </>,
  );
}
