// The *Alerts* place on the left rail (`06_DECISIONS.md` ADR-109 ruling 5): the case team's queue
// first, then the rules that raise its alerts, the rows a failing rule held, and the rule audit.
// What each account may do follows its level in the case, read as every other case surface reads
// it (`listCases`); the Conduit refuses whatever a stale view offers anyway.
import { useEffect, useState } from "react";
import { Tabs } from "../design/primitives";
import { listCases, type AccessLevel } from "../investigation/cases";
import { AlertQueue } from "./AlertQueue";
import type { CanvasOutcome } from "./api";
import { HeldRowsPanel } from "./HeldRowsPanel";
import { RuleAuditPanel } from "./RuleAuditPanel";
import { RulesPanel } from "./RulesPanel";

export interface AlertsPlaceProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string | null;
  accountId: string | null;
  isAdministrator: boolean;
  onCanvas: (outcome: CanvasOutcome, nodeIds: string[]) => void;
}

type Tab = "queue" | "rules" | "held" | "audit";

export function AlertsPlace(props: AlertsPlaceProps) {
  const { apiBaseUrl, bearerToken, investigationId } = props;
  const [tab, setTab] = useState<Tab>("queue");
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

  if (!investigationId) return <p className="label">Open a case to see its alerts.</p>;
  const api = { apiBaseUrl, bearerToken, investigationId };
  const readsAudit = level === "author" || props.isAdministrator;
  const tabs = [
    { id: "queue", label: "Queue" },
    { id: "rules", label: "Rules" },
    ...(level === "editor" || level === "author" ? [{ id: "held", label: "Held rows" }] : []),
    ...(readsAudit ? [{ id: "audit", label: "Audit" }] : []),
  ];

  return (
    <section aria-label="Alerts" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", padding: "var(--sp-16)", minHeight: 0, flex: 1, overflowY: "auto" }}>
      <h2 className="value" style={{ margin: 0 }}>Alerts</h2>
      <Tabs tabs={tabs} activeId={tab} onChange={(id) => setTab(id as Tab)} />
      {tab === "queue" && <AlertQueue {...api} level={level} accountId={props.accountId} onCanvas={props.onCanvas} />}
      {tab === "rules" && <RulesPanel {...api} level={level} />}
      {tab === "held" && <HeldRowsPanel {...api} level={level} />}
      {tab === "audit" && readsAudit && <RuleAuditPanel {...api} />}
    </section>
  );
}
